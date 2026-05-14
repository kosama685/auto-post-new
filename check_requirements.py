#!/usr/bin/env python3
"""
Requirements verification script - checks if all dependencies are properly installed.
Run this before deploying to Streamlit Cloud.
"""
import sys
import subprocess

print("=" * 60)
print("REQUIREMENTS VERIFICATION SCRIPT")
print("=" * 60)

# Read requirements.txt
try:
    with open("requirements.txt", "r") as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]
except FileNotFoundError:
    print("❌ requirements.txt not found!")
    sys.exit(1)

print(f"\nChecking {len(requirements)} packages...\n")

missing = []
outdated = []
ok = []

for req in requirements:
    # Parse requirement string
    if "==" in req:
        pkg, version = req.split("==")
        pkg = pkg.strip()
        version = version.strip()
    elif ">=" in req:
        pkg = req.split(">=")[0].strip()
        version = None
    else:
        pkg = req.strip()
        version = None
    
    try:
        __import__(pkg.replace("-", "_"))
        ok.append(pkg)
        print(f"✅ {pkg}")
    except ImportError:
        missing.append(pkg)
        print(f"❌ {pkg} NOT INSTALLED")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"✅ OK: {len(ok)}")
print(f"❌ Missing: {len(missing)}")

if missing:
    print(f"\n⚠️  Missing packages: {', '.join(missing)}")
    print("\nFix with:")
    print("  pip install -r requirements.txt")
    sys.exit(1)
else:
    print("\n✅ All dependencies installed!")
    sys.exit(0)
