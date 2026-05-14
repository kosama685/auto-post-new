# Streamlit Cloud Deployment - Troubleshooting Guide

## Current Issues and Resolutions

### Issue: App Status 5 (Crashed)

The `status: 5` indicates the app has crashed during initialization or runtime. This is typically caused by:

1. **Module Import Failures** - Dependencies missing or incompatible
2. **Configuration Errors** - Missing .env or config files
3. **Initialization Errors** - Database, storage, or authentication setup failure
4. **Memory Issues** - Large processes or unoptimized code

## Solutions Applied

### 1. **Lazy Loading & Error Handling**
- ✅ Imports are now wrapped in try-except blocks
- ✅ Initialization code runs in session state to prevent repeated failures
- ✅ All dashboard code wrapped in try-except for graceful degradation

### 2. **Streamlit Configuration**
- ✅ Created `.streamlit/config.toml` with Cloud-optimized settings
- ✅ Disabled verbose logging to reduce memory
- ✅ Disabled error detail popups to prevent UI crashes
- ✅ Set toolbar to minimal mode for faster loads

### 3. **Page Configuration**
- ✅ Moved `st.set_page_config()` to first line of code
- ✅ Set `initial_sidebar_state="expanded"` to prevent layout shifts
- ✅ Added CSS stabilization rules

### 4. **Browser Issues**
- ✅ Added `font-display: swap` for fonts
- ✅ Added `overflow-x: hidden` to prevent layout jank
- ✅ Added minimum heights to prevent element collapse

## How to Verify Fixes

### Option 1: Check Main App
Visit your app URL and look for:
- ❌ **App loads but shows error message** → Configuration issue
- ✅ **App shows "App initializing... Please refresh"** → Normal first load
- ✅ **App fully loads** → Fixes are working!

### Option 2: Check Debug App
Visit `/app_debug` to see:
- Which modules are missing
- Environment file status
- Recent error logs

## Next Steps

### If app still shows status 5:

1. **Check Streamlit Cloud Logs**
   - Open your app in Streamlit Cloud
   - Click "Manage app" → "View logs"
   - Look for Python stack trace errors

2. **Common Causes:**
   - Missing dependency in `requirements.txt`
   - Database file permissions issue
   - API key configuration problem
   - Memory overload (reduce batch sizes)

3. **Fix Steps:**
   ```bash
   # 1. Verify requirements
   pip install -r requirements.txt
   
   # 2. Create config
   cp .env.example .env
   
   # 3. Test locally first
   streamlit run app.py
   
   # 4. If works locally, push to Cloud
   git push origin main
   ```

### If app loads but features fail:

1. **Settings Tab Issues** → Check `.env` file and API keys
2. **Fetch Articles Fails** → Check RSS feed URLs in `data/sources.json`
3. **Publishing Fails** → Check Google OAuth configuration
4. **Image Generation Fails** → Check Cloudinary API setup

## Streamlit Cloud Best Practices

### Memory Management
- Avoid large dataframe operations
- Cache expensive computations: `@st.cache_data`
- Limit file uploads to <200MB
- Stream logs instead of loading full files

### Performance
- Use `st.spinner()` for long operations
- Cache model loads with `@st.cache_resource`
- Lazy load heavy modules
- Use session state for expensive computations

### Error Handling
```python
try:
    # Your code
except Exception as e:
    st.error(f"Error: {str(e)}")
    st.stop()
```

### Logging
- Use logging module, not print()
- Set log level to ERROR in Cloud
- Write to `logs/` directory for persistence

## Testing Locally Before Deploy

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create config
cp .env.example .env
# Edit .env with test values

# 4. Run app
streamlit run app.py

# 5. Test all features
# - Navigate all tabs
# - Try each button
# - Check console (F12) for errors

# 6. If works, commit and push
git add .
git commit -m "Test passed, ready for Cloud"
git push origin main
```

## When All Else Fails

### Use Debug App
```bash
streamlit run app_debug.py
```
This shows which modules are missing and current environment status.

### Check Requirements Format
```txt
# Each package on its own line
package1==version1
package2==version2
```

### Minimize App Initially
```python
# Start with just this
import streamlit as st
st.write("Hello from Streamlit Cloud!")

# Gradually add features and test
```

### Monitor Cloud Resources
- Check Streamlit Cloud dashboard for memory/CPU usage
- Reduce `maxUploadSize` if files are large
- Reduce `maxMessageSize` if lots of data transfer
- Use `st.write()` instead of `print()`

## Contact Support

If issues persist after trying all solutions:

1. **Streamlit Status** → https://www.streamlitstatus.com
2. **Cloud Docs** → https://docs.streamlit.io/deploy/streamlit-cloud
3. **Community Forum** → https://discuss.streamlit.io

---

**Last Updated:** May 14, 2026  
**App Version:** 1.39.0 (Streamlit)  
**Status:** Monitoring
