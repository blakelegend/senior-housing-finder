import sys
import os
import traceback

# Force path
os.chdir("/home/blakelegend/senior_housing_finder")
sys.path.insert(0, "/home/blakelegend/senior_housing_finder")

print("🚀 Ultra Simple Scraper Starting...")

try:
    import main_scraper
    print("Imported main_scraper")
    if hasattr(main_scraper, "main"):
        main_scraper.main()
    else:
        exec(open("main_scraper.py").read())
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
