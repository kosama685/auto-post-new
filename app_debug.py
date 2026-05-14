"""
Minimal debug version of the app for troubleshooting.
Use this if the main app fails to load.
"""
import sys
import os
import traceback

# Set page config FIRST
import streamlit as st

st.set_page_config(
    page_title="Debug Dashboard",
    page_icon="🔧",
    layout="wide",
)

st.title("🔧 Streamlit App Debug Mode")
st.write("If you're seeing this page, there's an issue with the main application.")

# Show environment info
st.subheader("Environment Information")
col1, col2 = st.columns(2)
col1.write(f"**Python Version:** {sys.version}")
col2.write(f"**Streamlit Version:** {st.__version__}")

# Try to import modules one by one
st.subheader("Module Import Status")

modules = [
    "pandas",
    "numpy",
    "requests",
    "feedparser",
    "beautifulsoup4",
    "openai",
    "google.auth",
    "google.oauth2",
    "cloudinary",
]

for module_name in modules:
    try:
        __import__(module_name)
        st.success(f"✅ {module_name}")
    except ImportError as e:
        st.error(f"❌ {module_name}: {str(e)}")

# Try autoblog imports
st.subheader("Autoblog Module Status")
autoblog_modules = [
    "autoblog.config",
    "autoblog.fetcher",
    "autoblog.pipeline",
    "autoblog.publisher_blogger",
    "autoblog.storage",
]

for module_name in autoblog_modules:
    try:
        __import__(module_name)
        st.success(f"✅ {module_name}")
    except Exception as e:
        st.error(f"❌ {module_name}")
        st.code(traceback.format_exc(), language="python")

# Check environment files
st.subheader("Configuration Files")
files_to_check = [
    ".env",
    ".streamlit/config.toml",
    "data/sources.json",
    "requirements.txt",
]

for file_path in files_to_check:
    if os.path.exists(file_path):
        st.success(f"✅ {file_path} exists")
    else:
        st.warning(f"⚠️ {file_path} not found")

st.divider()
st.info(
    """
### How to fix:

1. **Check the terminal logs** - Look for actual error messages
2. **Install dependencies** - Run: `pip install -r requirements.txt`
3. **Create .env file** - Run: `cp .env.example .env`
4. **Check imports** - Review the status above for missing modules
5. **Contact support** - If issues persist, check Streamlit Cloud status
"""
)

# Show recent logs if available
if os.path.exists("logs/autoblog.log"):
    st.subheader("Recent Logs")
    with open("logs/autoblog.log", "r") as f:
        lines = f.readlines()
        st.code("".join(lines[-50:]), language="text")
