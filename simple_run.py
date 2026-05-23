import sys
import os
import traceback

sys.path.insert(0, os.getcwd())

print("🚀 Starting senior housing scraper (Light Mode)...")

try:
    with open("main_scraper.py", "r", encoding="utf-8") as f:
        code = f.read()
    
    # Skip CMS collector to avoid proxy blocks
    code = code.replace("collect_cms_nursing_homes", "# collect_cms_nursing_homes  # Disabled on free tier")
    
    exec(code)
    print("✅ Scraper completed (Light Mode)!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    traceback.print_exc()
