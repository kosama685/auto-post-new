# Streamlit Cloud Deployment Checklist

## Pre-Deployment Steps

Before pushing to Streamlit Cloud, complete this checklist to prevent crashes:

### ✅ Code Quality
- [ ] Run `python check_requirements.py` - all packages installed
- [ ] Run `streamlit run app.py` locally - app loads without errors
- [ ] Test all major features locally (fetch, generate, publish)
- [ ] No `print()` statements - use `st.write()` or logging
- [ ] Error handling in place for external API calls

### ✅ Configuration Files
- [ ] `.env` file exists and is NOT committed to git
- [ ] `.streamlit/config.toml` exists
- [ ] `data/sources.json` exists with valid RSS feeds
- [ ] `logs/` directory exists and is writable
- [ ] `.gitignore` includes `.env`, `*.db`, `logs/`

### ✅ Dependencies
- [ ] `requirements.txt` has exact versions (no floating versions)
- [ ] All custom modules can be imported
- [ ] No system-specific paths in code
- [ ] Python version >= 3.8 specified if needed

### ✅ Database & Storage
- [ ] Database migrations run locally
- [ ] `data/` directory writable
- [ ] Database can be reset safely
- [ ] No hardcoded database paths

### ✅ API Keys & Secrets
- [ ] All sensitive data in `.env` file only
- [ ] `.env` added to `.gitignore`
- [ ] Streamlit Cloud secrets configured for production
- [ ] Never commit `client_secret*.json` files

### ✅ Error Handling
- [ ] Module imports wrapped in try-except
- [ ] External API calls have timeout
- [ ] Database operations wrapped in try-except
- [ ] User-friendly error messages in UI

### ✅ Memory & Performance
- [ ] Large operations use `st.spinner()` for feedback
- [ ] Data loading uses `@st.cache_data` decorator
- [ ] Model loading uses `@st.cache_resource`
- [ ] No infinite loops or blocking calls
- [ ] File uploads capped at reasonable size

### ✅ Logging & Monitoring
- [ ] Logging configured with rotating file handler
- [ ] Important events logged (startup, errors, API calls)
- [ ] No sensitive data in logs
- [ ] Log level set to WARNING for Cloud

### ✅ Git & Deployment
- [ ] All changes committed
- [ ] Branch is up to date with main
- [ ] No uncommitted changes: `git status`
- [ ] Ready to push: `git push origin main`

## Testing Procedure

### Local Testing (Required)
```bash
# 1. Create clean virtual environment
python -m venv test_env
source test_env/bin/activate  # Windows: test_env\Scripts\activate

# 2. Install requirements
pip install -r requirements.txt

# 3. Run requirements check
python check_requirements.py

# 4. Run the app
streamlit run app.py

# 5. Test in browser
# - Open http://localhost:8501
# - Navigate all tabs
# - Try each button
# - Check browser console (F12) for errors

# 6. Cleanup
deactivate
rm -rf test_env
```

### Cloud Testing (After Push)
1. Wait 3-5 minutes for Streamlit Cloud to rebuild
2. Check app health in Streamlit Cloud dashboard
3. Test core functionality
4. Check server logs for errors
5. Monitor for 24 hours for crashes

## If App Crashes on Cloud

### Immediate Actions
1. Check Streamlit Cloud status: https://www.streamlitstatus.com
2. View app logs in Streamlit Cloud dashboard
3. Try debug app: `streamlit run app_debug.py`
4. Check module imports in debug app

### Common Fixes
```bash
# Fix 1: Missing dependencies
pip install -r requirements.txt
git add -A && git commit -m "Update deps" && git push

# Fix 2: Config missing
cp .env.example .env
# Edit .env with proper values
git add .streamlit/ && git commit -m "Add config" && git push

# Fix 3: Import error
# Check app.py imports are wrapped in try-except
# Make sure custom modules exist

# Fix 4: Memory overload
# Reduce batch sizes
# Enable caching with @st.cache_data
# Reduce log verbosity
```

### Debugging Steps
1. **Add print debugging** to see where it fails
2. **Use st.write()** to display variable states
3. **Test imports** using debug app
4. **Check environment** with debug app
5. **Review logs** in Streamlit Cloud

## Rollback Procedure

If deployed version is broken:

```bash
# 1. Find last good commit
git log --oneline

# 2. Revert to good version
git revert HEAD
git push origin main

# 3. Or reset to specific commit
git reset --hard <commit-hash>
git push origin main --force

# Note: --force is last resort only!
```

## Monitoring After Deployment

### Watch For:
- [ ] App crashes (status 5 errors)
- [ ] High memory usage (>500MB)
- [ ] High CPU usage (>90%)
- [ ] Slow page loads (>3 seconds)
- [ ] API timeouts
- [ ] Database locks

### Health Check Commands
```bash
# Check git status
git status

# Check logs
tail -f logs/autoblog.log

# Check requirements are installed
python check_requirements.py

# Test imports
python -c "from autoblog.config import get_settings; print('✅')"
```

## Performance Optimization

### Before Deployment
1. **Profile code** - Find slow functions
2. **Cache expensive ops** - Use @st.cache_data
3. **Lazy load modules** - Import only when needed
4. **Optimize queries** - Limit SQL results
5. **Compress assets** - Minimize images/CSS

### After Deployment
1. **Monitor metrics** - Check Streamlit Cloud dashboard
2. **Analyze logs** - Find error patterns
3. **User feedback** - Track crashes/slowness
4. **Performance alerts** - Set up notifications

## Success Criteria

App is ready for production when:
- ✅ Loads without errors in Cloud
- ✅ All features work as expected
- ✅ No console errors (F12)
- ✅ Responds quickly (<3s)
- ✅ Error messages are helpful
- ✅ Logs show no warnings/errors
- ✅ Status shows as healthy

---

**Last Updated:** May 14, 2026  
**Created By:** Deployment Guide System  
**Status:** Active Use

For questions, check:
- TROUBLESHOOTING.md - Common issues and fixes
- STREAMLIT_FIXES.md - Technical details of fixes
- Streamlit docs - https://docs.streamlit.io
