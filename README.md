# Chokepoint Dashboard

This folder is a deployment-ready starting point for a Streamlit dashboard that shows:

- choke point locations
- 500 km and 1000 km buffers
- countries of interest that intersect those buffers
- closest-country and proximity tables

## Files

- `app.py`: Streamlit app using `maplibre.streamlit`
- `requirements.txt`: Python dependencies for deployment
- `export_dashboard_data.R`: Regenerates the dashboard data files from `../clean_standardize.R`
- `data/`: GeoJSON and CSV files used by the app

## Local run

```bash
Rscript export_dashboard_data.R
pip install -r requirements.txt
streamlit run app.py
```

## Deployment notes

- The app is designed to be copied into a separate git repo if you want.
- If you update `clean_standardize.R` or `choke_points.csv`, rerun `export_dashboard_data.R` to refresh the dashboard data.
