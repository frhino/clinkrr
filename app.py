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
        keyword_clauses = [f"lower(description) like '%{k}%'" for k in keywords]
        where_clause += f" AND ({' OR '.join(keyword_clauses)})"
    elif filter_method == "Both (Recommended)":
        sub_clauses = ["existing_construction_type = '3'"]
        if keywords:
            sub_clauses.extend([f"lower(description) like '%{k}%'" for k in keywords])
        where_clause += f" AND ({' OR '.join(sub_clauses)})"

    permits_soql = (
        f"$select=permit_number,permit_type_definition,status,description,block,lot,filed_date,issued_date,street_number,street_name,street_suffix,existing_construction_type_description,neighborhoods_analysis_boundaries"
        f"&$where={where_clause}"
        f"&$order=filed_date DESC"
        f"&$limit=2000"
    )
    
    try:
        permits_resp = requests.get(f"{permits_url}?{permits_soql}")
        permits_resp.raise_for_status()
        df_permits = pd.DataFrame(permits_resp.json())
    except Exception as e:
        st.error(f"Error fetching permit data: {e}")
        return pd.DataFrame()

    if df_permits.empty:
        return df_permits

    df_permits['address'] = df_permits['street_number'].fillna('') + ' ' + df_permits['street_name'].fillna('') + ' ' + df_permits['street_suffix'].fillna('')
    df_permits['address'] = df_permits['address'].str.strip().str.upper()

    df_permits['join_block'] = df_permits['block'].astype(str).str.strip().str.lstrip('0').str.upper()
    df_permits['join_lot'] = df_permits['lot'].astype(str).str.strip().str.lstrip('0').str.upper()

    unique_blocks = df_permits['block'].dropna().unique().tolist()
    padded_blocks = [str(b).strip().zfill(4) for b in unique_blocks]
    
    if len(padded_blocks) > 400:
        padded_blocks = padded_blocks[:400]
    block_filter = ", ".join(f"'{b}'" for b in padded_blocks)
    
    assessor_url = "https://data.sfgov.org/resource/wv5m-vpq2.json"
    assessor_soql = (
        f"$select=year_property_built,block,lot"
        f"&$where=block IN ({block_filter}) AND year_property_built <= '{max_built_year}'"
        f"&$limit=15000"
    )
    
    try:
        assessor_resp = requests.get(f"{assessor_url}?{assessor_soql}")
        assessor_resp.raise_for_status()
        df_assessor = pd.DataFrame(assessor_resp.json())
    except Exception as e:
        st.error(f"Error fetching assessor data: {e}")
        return pd.DataFrame()

    if df_assessor.empty:
        return pd.DataFrame()

    df_assessor['join_block'] = df_assessor['block'].astype(str).str.strip().str.lstrip('0').str.upper()
    df_assessor['join_lot'] = df_assessor['lot'].astype(str).str.strip().str.lstrip('0').str.upper()

    merged_df = pd.merge(df_permits, df_assessor, on=['join_block', 'join_lot'], how='inner')
    
    if not merged_df.empty:
        if 'block_x' in merged_df.columns:
            merged_df['block'] = merged_df['block_x']
        if 'lot_x' in merged_df.columns:
            merged_df['lot'] = merged_df['lot_x']
            
    return merged_df

# --- MAIN SCREEN DISPLAY ---
if st.sidebar.button("Run Search / Refresh Data"):
    with st.spinner("Scanning complete DataSF catalog..."):
        results_df = fetch_sf_data(selected_statuses, construction_filter, keyword_list, target_year, start_filing_year, end_filing_year, selected_neighborhoods)
        
        if not results_df.empty:
            expected_cols = ['permit_number', 'permit_type_definition', 'status', 'address', 'filed_date', 'issued_date', 'year_property_built', 'existing_construction_type_description', 'description', 'block', 'lot', 'neighborhoods_analysis_boundaries']
            for col in expected_cols:
                if col not in results_df.columns:
                    results_df[col] = None

            try:
                results_df['filed_date'] = pd.to_datetime(results_df['filed_date']).dt.strftime('%Y-%m-%d')
            except:
                pass
            results_df['filed_date'] = results_df['filed_date'].fillna('N/A')

            try:
                results_df['issued_date'] = pd.to_datetime(results_df['issued_date']).dt.strftime('%Y-%m-%d')
            except:
                pass
            results_df['issued_date'] = results_df['issued_date'].fillna('Not Yet Issued')

            results_df = results_df.sort_values(by='filed_date', ascending=False)
            results_df = results_df.drop_duplicates(subset=['address'], keep='first')

            # Generate maps link
            results_df['maps_url'] = results_df['address'].apply(
                lambda addr: f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(f'{addr}, San Francisco, CA')}"
            )

            # Reformat layout columns to cleanly include Neighborhood
            display_df = results_df[[
                'maps_url', 'address', 'neighborhoods_analysis_boundaries', 'year_property_built', 'existing_construction_type_description', 'permit_number', 'permit_type_definition', 'status', 'filed_date', 'issued_date', 'description'
            ]].rename(columns={
                'maps_url': 'Google Maps',
                'address': 'Property Address',
                'neighborhoods_analysis_boundaries': 'Neighborhood',
                'year_property_built': 'Year Built',
                'existing_construction_type_description': 'Frame Class',
                'permit_number': 'Permit #',
                'permit_type_definition': 'Permit Classification',
                'status': 'Status',
                'filed_date': 'Date Filed',
                'issued_date': 'Date Issued',
                'description': 'Permit Description'
            })
            
            # Statistics
            col1, col2 = st.columns(2)
            col1.metric("Unique Properties Identified", len(display_df))
            col2.metric("Target Year Threshold", f"Built ≤ {target_year}")
            
            st.markdown("---")
            
            # Render grid map table
            st.dataframe(
                display_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Google Maps": st.column_config.LinkColumn(
                        label="View Street View",
                        display_text="🌐 Open Maps"
                    )
                }
            )
            
            # Exporter setup
            csv = display_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Neighborhood Results as CSV",
                data=csv,
                file_name="sf_historic_neighborhood_permits.csv",
                mime='text/csv',
            )
        else:
            st.info("No records found matching your specified neighborhood and timeline parameters.")
else:
    st.info("Adjust parameters in the sidebar panel and click **'Run Search / Refresh Data'**.")
