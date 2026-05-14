from autoblog.utils import clean_text, make_slug, truncate_words


def test_clean_text_removes_html():
    assert clean_text("<p>مرحبا&nbsp;بك</p>") == "مرحبا بك"


def test_slug_not_empty():
    assert make_slug("الصحة والأعشاب: اختبار")


def test_truncate():
    assert len(truncate_words("كلمة " * 100, 30)) <= 30
