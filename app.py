import streamlit as st
import pandas as pd
import requests

# Set up page configuration
st.set_page_config(page_title="SF Historic Building Permit Tracker", layout="wide")

st.title("🏛️ SF Historic Building & Material Permit Tracker")
st.markdown("Search and filter San Francisco Open Data for structural changes, alterations, and demolitions of historic structures.")

# --- SIDEBAR FILTERS ---
st.sidebar.header("Filter Criteria")

# 1. Age Filter (Dynamic based on current year 2026)
current_year = 2026
max_age = st.sidebar.number_input("Minimum Building Age (Years)", min_value=1, max_value=200, value=50)
target_year = current_year - max_age

# 2. Material/Keyword Filter
keywords = st.sidebar.text_input("Material Keywords (comma separated)", value="brick, masonry")
keyword_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]

# 3. Permit Type Filter (CRITICAL UPGRADE)
permit_type_options = {
    "Full Demolitions (Type 6)": "demolitions",
    "Major Alterations & Repairs (Type 3)": "additions alterations or repairs",
    "OTC Alterations Permit (Type 8)": "otc alterations permit"
}
selected_types = st.sidebar.multiselect(
    "Permit Classifications", 
    options=list(permit_type_options.keys()), 
    default=list(permit_type_options.keys())
)
selected_type_values = [permit_type_options[t] for t in selected_types]

# 4. Permit Status Filter
status_options = ['filed', 'issued', 'approved', 'reinstated', 'cancelled', 'withdrawn']
selected_statuses = st.sidebar.multiselect("Permit Statuses", options=status_options, default=['filed', 'issued', 'approved'])

# --- DATA FETCHING & PROCESSING ---
@st.cache_data(ttl=3600)  # Cache data for 1 hour
def fetch_sf_data(statuses, permit_types, keywords, max_built_year):
    if not statuses or not permit_types:
        return pd.DataFrame()

    permits_url = "https://data.sfgov.org/resource/i98e-djp9.json"
    status_str = ", ".join(f"'{s}'" for s in statuses)
    type_str = ", ".join(f"'{t}'" for t in permit_types)
    
    # Construct conditions dynamically
    where_clause = f"lower(permit_type_definition) IN ({type_str}) AND status IN ({status_str})"
    if keywords:
        keyword_clauses = [f"lower(description) like '%{k}%'" for k in keywords]
        where_clause += f" AND ({' OR '.join(keyword_clauses)})"

    permits_soql = (
        f"$select=permit_number,permit_type_definition,status,description,block,lot,filed_date,issued_date,street_number,street_name,street_suffix"
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

    # Combine street fields for a cleaner address mapping
    df_permits['address'] = df_permits['street_number'].fillna('') + ' ' + df_permits['street_name'].fillna('') + ' ' + df_permits['street_suffix'].fillna('')
    df_permits['address'] = df_permits['address'].str.strip().str.upper()

    # Normalize tracking IDs to handle string padding variances
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

    # Cross-dataset inner join
    merged_df = pd.merge(df_permits, df_assessor, on=['join_block', 'join_lot'], how='inner')
    
    if not merged_df.empty:
        if 'block_x' in merged_df.columns:
            merged_df['block'] = merged_df['block_x']
        if 'lot_x' in merged_df.columns:
            merged_df['lot'] = merged_df['lot_x']
            
    return merged_df

# --- MAIN SCREEN DISPLAY ---
if st.sidebar.button("Run Search / Refresh Data"):
    with st.spinner("Querying DataSF Open Data APIs..."):
        results_df = fetch_sf_data(selected_statuses, selected_type_values, keyword_list, target_year)
        
        if not results_df.empty:
            # Table scaffolding check
            expected_cols = ['permit_number', 'permit_type_definition', 'status', 'address', 'filed_date', 'issued_date', 'year_property_built', 'description', 'block', 'lot']
            for col in expected_cols:
                if col not in results_df.columns:
                    results_df[col] = None

            # Clean and format date values safely
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

            # Sorting data and deduplicating by address 
            results_df = results_df.sort_values(by='filed_date', ascending=False)
            results_df = results_df.drop_duplicates(subset=['address'], keep='first')

            # Format finalized presentation dataframe
            display_df = results_df[[
                'permit_number', 'permit_type_definition', 'status', 'address', 'filed_date', 'issued_date', 'year_property_built', 'description', 'block', 'lot'
            ]].rename(columns={
                'permit_number': 'Permit #',
                'permit_type_definition': 'Permit Type',
                'status': 'Status',
                'address': 'Property Address',
                'filed_date': 'Date Filed',
                'issued_date': 'Date Issued',
                'year_property_built': 'Year Built',
                'description': 'Permit Description'
            })
            
            # KPI Counters
            col1, col2 = st.columns(2)
            col1.metric("Unique Properties Found", len(display_df))
            col2.metric("Target Year Threshold", f"Built ≤ {target_year}")
            
            st.markdown("---")
            
            # Grid display
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Export payload configuration
            csv = display_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Unique Results as CSV",
                data=csv,
                file_name=f"sf_unique_historic_permits_{target_year}.csv",
                mime='text/csv',
            )
        else:
            st.info("No properties matched your current filter criteria.")
else:
    st.info("Adjust the sidebar filters as needed and click **'Run Search / Refresh Data'** to pull the latest public records.")

