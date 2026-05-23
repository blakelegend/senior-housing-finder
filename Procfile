web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.enableCORS=false --server.enableXsrfProtection=false
worker: python main_scraper.py
release: playwright install --with-deps chromium || true
