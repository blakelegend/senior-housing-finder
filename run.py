import sys
import os

# Fix path issues
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath(".."))

print("Python path set. Starting scraper...")

try:
    from main_scraper import main  # Adjust if your entry point is different
    main()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

ccd /home/blakelegend/senior_housing_finder
python run.py

cd /home/blakelegend/senior_housing_finder

# Remove playwright
pip uninstall playwright -y

# Update requirements.txt to skip it temporarily
sed -i '/playwright/d' requirements.txt

# Reinstall everything else
pip install --force-reinstall -r requirements.txt
cd /home/blakelegend/senior_housing_finder

pip uninstall playwright -y

sed -i '/playwright/d' requirements.txt

pip install --force-reinstall -r requirements.txt
nano run.py
import sys
import os

# Fix path issues
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath(".."))

print("✅ Python path fixed. Starting scraper...")

try:
    import main_scraper
    print("✅ Successfully imported main_scraper")
    
    if hasattr(main_scraper, 'main'):
        print("Running main() function...")
        main_scraper.main()
    elif hasattr(main_scraper, 'run'):
        print("Running run() function...")
        main_scraper.run()
    else:
        print("Running module directly...")
        exec(open("main_scraper.py").read())
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

cd /home/blakelegend/senior_housing_finder

cat > run.py << 'EOF'
import sys
import os

# Fix path issues
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath(".."))

print("✅ Python path fixed. Starting scraper...")

try:
    import main_scraper
    print("✅ Successfully imported main_scraper")
    
    if hasattr(main_scraper, 'main'):
        print("Running main() function...")
        main_scraper.main()
    elif hasattr(main_scraper, 'run'):
        print("Running run() function...")
        main_scraper.run()
    else:
        print("Running module directly...")
        exec(open("main_scraper.py").read())
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
EOF

echo "✅ run.py has been overwritten cleanly."
python run.py
cd /home/blakelegend/senior_housing_finder

cat > run.py << 'EOF'
import sys
import os

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath(".."))

print("✅ Python path fixed. Starting scraper...")

try:
    import main_scraper
    print("✅ Successfully imported main_scraper")
    
    if hasattr(main_scraper, "main"):
        print("Running main() function...")
        main_scraper.main()
    elif hasattr(main_scraper, "run"):
        print("Running run() function...")
        main_scraper.run()
    else:
        print("Running module directly...")
        exec(open("main_scraper.py").read())
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
EOF

echo "✅ run.py overwritten successfully!"
python run.pyc

cd /home/blakelegend/senior_housing_finder

# Completely overwrite run.py with clean code
cat > run.py << 'EOF'
import sys
import os

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath(".."))

print("✅ Python path fixed. Starting scraper...")

try:
    import main_scraper
    print("✅ Successfully imported main_scraper")
    
    if hasattr(main_scraper, "main"):
        print("Running main() function...")
        main_scraper.main()
    elif hasattr(main_scraper, "run"):
        print("Running run() function...")
        main_scraper.run()
    else:
        print("Running module directly...")
        exec(open("main_scraper.py").read())
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
EOF

echo "✅ File cleaned successfully!"
python run.py
cd /home/blakelegend/senior_housing_finder

# Completely reset run.py with clean code
cat > run.py << 'EOD'
import sys
import os
import traceback

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath(".."))

print("✅ Python path fixed. Trying to run scraper...")

try:
    import main_scraper
    print("✅ Imported main_scraper successfully")
    
    if hasattr(main_scraper, "main"):
        print("→ Running main()...")
        main_scraper.main()
    else:
        print("→ Running as script...")
        exec(open("main_scraper.py").read())
        
except Exception as e:
    print(f"❌ Error: {e}")
    traceback.print_exc()
EOD

python run.py
cd /home/blakelegend/senior_housing_finder

# Create a super simple runner
cat > simple_run.py << 'EOF'
import sys
import os
import traceback

# Add current folder to path
sys.path.insert(0, os.getcwd())

print("🚀 Starting senior housing scraper...")

try:
    # Run the main scraper directly
    with open("main_scraper.py", "r") as f:
        code = f.read()
    
    exec(code)
    print("✅ Scraper finished!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    traceback.print_exc()
EOF

echo "✅ Simple runner created!"
python simple_run.py


