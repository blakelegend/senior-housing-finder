"""
Streamlit entry point.

Hosts (Streamlit Community Cloud, Heroku, Render, Railway) expect to run
`streamlit run app.py` from the repo root. We delegate to the dashboard
module so the actual UI code stays organized under the package.
"""
from senior_housing_finder.dashboard import main


if __name__ == "__main__":
    main()
else:
    # Streamlit imports the module rather than running __main__, so call here too
    main()
