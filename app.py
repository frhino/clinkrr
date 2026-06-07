import streamlit as st
import pandas as pd
import requests
import urllib.parse

# Set up page configuration
st.set_page_config(page_title="SF Historic Building Permit Tracker", layout="wide")

st.title("🏛️ SF Universal Historic Permit Explorer")
st.markdown("Search across all historical permit records. Filter by construction type, timeline, and planning neighborhoods.")

# --- OFFICIAL SF ANALYSIS NEIGHBORHOODS ---
sf_neighborhoods = [
    "Bayview Hunters Point", "Bernal Heights", "Castro/Upper Market", "Chinatown", 
    "Excelsior", "Financial District/South Beach", "Glen Park", "Golden Gate Park", 
    "Haight Ashbury", "Hayes Valley", "Inner Richmond", "Inner Sunset", "Japantown", 
    "Lakeshore", "Lincoln Park", "Lone Mountain/USF", "Marina", "Mission", 
    "Mission Bay", "Nob Hill", "Noe Valley", "North Beach", "Oceanview/Merced/Ingleside", 
    "Outer Mission", "Outer Richmond", "Outer Sunset", "Pacific Heights", "Portola", 
    "Potrero Hill", "Presidio", "Russian Hill", "Seacliff", "South of Market", 
    "Sunset/Parkside", "Tenderloin", "Twin Peaks", "Visitacion Valley", "West of Twin Peaks", 
    "Western Addition"
]

# --- SIDEBAR FILTERS ---
st.sidebar.header("Filter Criteria")

# 1. Building Age Filter (Dynamic based on current year 2026)
current_year = 2026
max_age = st.sidebar.number_input("Minimum Building Age (Years)", min_value=1, max_value=200, value=50)
target_year = current_year - max_age

# 2. Permit Filing Timeline Filter 
start_filing_year, end_filing_year = st.sidebar.slider(
    "Permit Filing Year Range",
    min_value=1980, 
    max_value=2026, 
    value=(2001, 2026)
)

# 3. CRITICAL UPGRADE: Neighborhood Filter
selected_neighborhoods = st.sidebar.multiselect(
    "Target Neighborhoods (Leave blank for ALL)",
    options=sf_neighborhoods,
    default=[]
)

# 4. Structural Construction Type Filter
construction_filter = st.sidebar.radio(
    "Structural Material Filter Method",
    options=["Keyword Text Search Only", "Type 3 Construction Only (Historic Masonry/Brick)", "Both (Recommended)"],
    index=2
)

# 5. Material/Keyword Filter
keywords = st.sidebar.text_input("Material Keywords (used if text search is active)", value="brick, masonry")
keyword_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]

# 6. Permit Status Filter
status_options = ['filed', 'issued', 'approved', 'reinstated', 'cancelled', 'withdrawn', 'completed']
selected_statuses = st.sidebar.multiselect("Permit Statuses", options=status_options, default=['filed', 'issued', 'approved'])

# --- DATA FETCHING & PROCESSING ---
@st.cache_data(ttl=3600)  # Cache data for 1 hour
def fetch_sf_data(statuses, filter_method, keywords, max_built_year, start_yr, end_yr, neighborhoods):
    if not statuses:
        return pd.DataFrame()

    permits_url = "https://data.sfgov.org/resource/i98e-djp9.json"
    status_str = ", ".join(f"'{s}'" for s in statuses)
    
    # Base timeline and status conditions
    where_clause = (
        f"status IN ({status_str}) "
        f"AND filed_date >= '{start_yr}-01-01' "
        f"AND filed_date <= '{end_yr}-12-31T23:59:59'"
    )
    
    # Inject geographic constraints directly into the SoQL where-clause
    if neighborhoods:
        nh_str = ", ".join(f"'{n}'" for n in neighborhoods)
        where_clause += f" AND neighborhoods_analysis_boundaries IN ({nh_str})"
    
    # Material criteria logic
    if filter_method == "Type 3 Construction Only (Historic Masonry/Brick)":
        where_clause += " AND existing_construction_type = '3'"
    elif filter_method == "Keyword Text Search Only" and keywords:
        keyword_clauses =
