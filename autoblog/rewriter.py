from __future__ import annotations

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
import httpx

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    GEMINI_AVAILABLE = False

from .config import get_settings, load_sources
from .logger_setup import logger
from .models import SourceArticle
from .utils import clean_text, domain_from_url, html_escape

SYSTEM_PROMPT = """أنت محرر عربي متخصص في محتوى الصحة العامة والسيو.
اكتب بأسلوب عربي واضح ومهني ومناسب للقارئ في السعودية.
التزم بالسلامة الطبية: لا تقدم تشخيصاً، لا تعد بالشفاء، لا تستخدم عبارات مطلقة مثل علاج مضمون أو شفاء نهائي.
أعد الصياغة بالكامل ولا تنسخ النص الأصلي. اذكر أن المعلومات عامة ولا تغني عن الطبيب.
أخرج HTML نظيفاً فقط بدون Markdown."""

USER_TEMPLATE = """أعد كتابة المادة التالية في مقال عربي أصلي ومرتب وجاهز للنشر في Blogger.

المتطلبات:
- مقدمة تبدأ بمعنى: في هذا المقال نستعرض...
- عناوين H2 و H3 منظمة.
- فقرة للسلامة والمحاذير.
- خاتمة قصيرة.
- 3 أسئلة شائعة بصيغة FAQ.
- لا تنسخ من المصدر ولا تقدم ادعاءات طبية مطلقة.
- استخدم الكلمات المفتاحية بشكل طبيعي: {keywords}
- اجعل المحتوى في حدود 700 إلى 1000 كلمة إذا كانت المادة المصدرية كافية.

العنوان الأصلي: {title}
المصدر: {source_name}
رابط المصدر: {source_url}
النص المصدر:
{text}
"""


def fallback_rewrite(article: SourceArticle) -> str:
    title = html_escape(article.title)
    body = html_escape(clean_text(article.body_text))
    source = html_escape(article.source_name or domain_from_url(article.source_url))
    if not body:
        body = "تتناول هذه المادة موضوعاً صحياً عاماً يحتاج إلى قراءة متأنية ومراجعة المصادر الطبية الموثوقة."
    return f"""
<p>في هذا المقال نستعرض أبرز المعلومات المرتبطة بموضوع <strong>{title}</strong> بطريقة مبسطة وآمنة للقارئ العربي.</p>
<h2>ملخص الموضوع</h2>
<p>{body}</p>
<h2>كيف يمكن فهم هذه المعلومات؟</h2>
<p>ينبغي التعامل مع المعلومات الصحية باعتبارها معرفة عامة تساعد على زيادة الوعي، وليست بديلاً عن التشخيص أو العلاج الطبي. تختلف الحالات الصحية من شخص لآخر، لذلك قد لا تناسب النصائح العامة الجميع.</p>
<h2>محاذير مهمة</h2>
<ul>
<li>استشر الطبيب عند وجود أعراض مستمرة أو شديدة.</li>
<li>لا توقف أي دواء موصوف دون الرجوع إلى مختص.</li>
<li>قد تتداخل بعض الأعشاب أو المكملات مع الأدوية.</li>
</ul>
<h2>أسئلة شائعة</h2>
<h3>هل يمكن الاعتماد على الأعشاب وحدها؟</h3>
<p>لا، يجب التعامل معها كمعلومات عامة أو ممارسات مساندة بعد استشارة مختص، خصوصاً عند وجود مرض مزمن أو حمل أو استخدام أدوية.</p>
<h3>هل هذه المعلومات مناسبة للجميع؟</h3>
<p>ليست بالضرورة، فالحالة الصحية والعمر والأدوية والحساسية عوامل مهمة يجب مراعاتها.</p>
<h3>ما أفضل خطوة قبل تجربة أي وصفة طبيعية؟</h3>
<p>التحقق من المصدر واستشارة طبيب أو صيدلي، خصوصاً عند وجود أمراض مزمنة.</p>
<h2>الخلاصة</h2>
<p>المعلومات المنشورة عن {source} مفيدة للتثقيف الصحي، لكنها تحتاج إلى قراءة واعية ومراجعة طبية عند الحاجة.</p>
""".strip()


class Rewriter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.openai_client = None
        self.gemini_model = None
        if self.settings.openai_api_key:
            self.openai_client = self._make_openai_client()
        if GEMINI_AVAILABLE and self.settings.gemini_api_key:
            genai.configure(api_key=self.settings.gemini_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-1.5-flash')

    def _make_openai_client(self) -> OpenAI:
        """Create an OpenAI client while avoiding the httpx>=0.28 proxies keyword issue."""
        try:
            return OpenAI(api_key=self.settings.openai_api_key)
        except TypeError as exc:
            if "proxies" not in str(exc):
                raise
            logger.warning("OpenAI/httpx proxy compatibility issue detected; using explicit httpx client.")
            return OpenAI(
                api_key=self.settings.openai_api_key,
                http_client=httpx.Client(timeout=60.0),
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=12))
    def rewrite(self, article: SourceArticle, ai_model: str = "openai") -> str:
        if not self.settings.enable_ai_rewrite:
            logger.warning("AI rewrite disabled; using fallback rewrite.")
            return fallback_rewrite(article)

        text = clean_text(article.body_text)
        if len(text) < 100:
            logger.warning("Source text short; fallback rewrite for %s", article.source_url)
            return fallback_rewrite(article)

        keywords = ", ".join(load_sources().get("keywords", [])[:8])

        if ai_model == "gemini" and self.gemini_model:
            return self._rewrite_with_gemini(article, keywords, text)
        elif ai_model == "openai" and self.openai_client:
            return self._rewrite_with_openai(article, keywords, text)
        else:
            logger.warning("AI model %s not available; using fallback rewrite.", ai_model)
            return fallback_rewrite(article)

    def _rewrite_with_openai(self, article: SourceArticle, keywords: str, text: str) -> str:
        prompt = USER_TEMPLATE.format(
            keywords=keywords,
            title=article.title,
            source_name=article.source_name,
            source_url=article.source_url,
            text=text[:7000],
        )
        response = self.openai_client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.45,
        )
        html = response.choices[0].message.content or ""
        if not html.strip():
            return fallback_rewrite(article)
        return html.strip()

    def _rewrite_with_gemini(self, article: SourceArticle, keywords: str, text: str) -> str:
        prompt = f"""Rewrite this health news article in a clear, engaging style for a general audience. Keep the facts accurate. Output in Arabic.

Requirements:
- Start with an introduction like: في هذا المقال نستعرض...
- Organize with H2 and H3 headings.
- Include a safety and precautions section.
- End with a short conclusion.
- Add 3 common questions in FAQ format.
- Use keywords naturally: {keywords}
- Keep content around 700-1000 words if source allows.
- Do not copy the original text verbatim. Rewrite completely.
- Ensure medical safety: no absolute claims, consult doctor disclaimer.

Title: {article.title}
Source: {article.source_name}
Source URL: {article.source_url}
Content:
{text[:7000]}
"""
        try:
            response = self.gemini_model.generate_content(prompt)
            html = response.text.strip()
            if not html:
                return fallback_rewrite(article)
            return html
        except Exception as exc:
            logger.warning("Gemini rewrite failed: %s", exc)
            return fallback_rewrite(article)
