
# app.py
# Streamlit Procurement Dashboard – AM/NS India
# Author: M365 Copilot
# Description: Upload Excel → map columns → configure settings → interactive dashboard with big KPI tiles

import json
import io
import math
import altair as alt
import pandas as pd
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Procurement Dashboard – AM/NS", layout="wide")

# -----------------------------
# Utility: persistent config
# -----------------------------
DEFAULT_CONFIG = {
    "date_format": "auto",  # auto detect dd-mm-yyyy / yyyy-mm-dd
    "pr_open_statuses": ["Open", "Pending", "In Progress"],
    "po_open_delivery_statuses": ["Open", "Partial", "Delayed"],
    "category_colors": {
        "MRO": "#2F80ED",      # Blue
        "Services": "#20B2AA", # Teal
        "Capex": "#F2994A",    # Orange
        "PCM": "#8E44AD"       # Purple
    },
    "column_mapping": {
        "PRs": {},
        "POs": {}
    },
    "category_mapping": {
        # key_field_value: category (MRO/Services/Capex/PCM)
    }
}

CONFIG_PATH = "config.json"

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        st.warning(f"Could not save config: {e}")

config = load_config()

# -----------------------------
# Page sidebar: navigation + settings
# -----------------------------
st.sidebar.title("📊 Procurement Dashboard")
page = st.sidebar.radio("Navigate", ["Upload & Column Mapper", "Settings", "Dashboard", "Data Health"])

# Settings editor in sidebar
with st.sidebar.expander("Settings", expanded=False):
    date_format = st.selectbox("Date format", ["auto", "dd-mm-yyyy", "yyyy-mm-dd"], index=["auto","dd-mm-yyyy","yyyy-mm-dd"].index(config.get("date_format","auto")))
    pr_open_statuses = st.text_input("PR open statuses (comma separated)", ", ".join(config.get("pr_open_statuses", DEFAULT_CONFIG["pr_open_statuses"])) )
    po_open_delivery_statuses = st.text_input("PO open delivery statuses (comma separated)", ", ".join(config.get("po_open_delivery_statuses", DEFAULT_CONFIG["po_open_delivery_statuses"])) )
    if st.button("💾 Save Settings"):
        config["date_format"] = date_format
        config["pr_open_statuses"] = [s.strip() for s in pr_open_statuses.split(",") if s.strip()]
        config["po_open_delivery_statuses"] = [s.strip() for s in po_open_delivery_statuses.split(",") if s.strip()]
        save_config(config)
        st.success("Settings saved.")

# -----------------------------
# File upload + Excel parsing
# -----------------------------
@st.cache_data(show_spinner=False)
def read_excel(uploaded_file, date_format="auto"):
    """Read Excel with sheets PRs, POs, optional Category_Mapping"""
    if uploaded_file is None:
        return None, None, None
    try:
        xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
        prs = pd.read_excel(xls, sheet_name="PRs") if "PRs" in xls.sheet_names else None
        pos = pd.read_excel(xls, sheet_name="POs") if "POs" in xls.sheet_names else None
        cmap = pd.read_excel(xls, sheet_name="Category_Mapping") if "Category_Mapping" in xls.sheet_names else None
        # normalize column names
        def norm(df):
            if df is None: return None
            df.columns = [str(c).strip() for c in df.columns]
            return df
        return norm(prs), norm(pos), norm(cmap)
    except Exception as e:
        st.error(f"Failed to read Excel: {e}")
        return None, None, None

# -----------------------------
# Column Mapper UI
# -----------------------------
REQUIRED_PRS_FIELDS = ["PR_Number", "PR_Date", "PR_Status"]
OPTIONAL_PRS_FIELDS = ["PR_Amount", "Material_Group", "Cost_Center", "Item_Type", "Category"]
REQUIRED_POS_FIELDS = ["PO_Number", "PO_Date", "PO_Status", "Delivery_Status"]
OPTIONAL_POS_FIELDS = ["Vendor", "PO_Quantity", "GRN_Quantity", "PR_Number", "PR_Line", "Category"]

def column_mapper(df, sheet_name, required_fields, optional_fields):
    st.subheader(f"🔧 Column Mapper – {sheet_name}")
    if df is None:
        st.warning(f"Sheet '{sheet_name}' not found.")
        return {}
    present_cols = list(df.columns)
    mapping = config.get("column_mapping", {}).get(sheet_name, {})
    new_mapping = {}
    cols = required_fields + optional_fields
    for field in cols:
        default = mapping.get(field)
        new_mapping[field] = st.selectbox(
            f"Map **{field}** to:", ["— not mapped —"] + present_cols,
            index=( ["— not mapped —"] + present_cols ).index(default) if default in present_cols else 0,
            help=f"Select which column in '{sheet_name}' corresponds to '{field}'."
        )
    # Save mapping
    if st.button(f"💾 Save {sheet_name} Mapping"):
        config.setdefault("column_mapping", {})[sheet_name] = new_mapping
        save_config(config)
        st.success(f"{sheet_name} mapping saved.")
    return new_mapping

# -----------------------------
# Category derivation
# -----------------------------
CATEGORIES = ["MRO", "Services", "Capex", "PCM"]

def derive_category(row, mapping, cfg_mapping):
    # 1) explicit Category column (if mapped)
    cat_col = mapping.get("Category")
    if cat_col and cat_col != "— not mapped —":
        val = str(row.get(cat_col, "")).strip()
        if val in CATEGORIES:
            return val
    # 2) mapping sheet via key fields (Material_Group/Cost_Center/Item_Type)
    for key_field in ["Material_Group", "Cost_Center", "Item_Type"]:
        col = mapping.get(key_field)
        if col and col != "— not mapped —":
            key_val = str(row.get(col, "")).strip()
            if key_val in cfg_mapping:
                mapped_cat = cfg_mapping[key_val]
                if mapped_cat in CATEGORIES:
                    return mapped_cat
    # 3) fallback: Unknown → assign None (flag in Data Health)
    return None

# -----------------------------
# Helper: Big KPI cards
# -----------------------------
def big_number_card(title, value, color="#2F80ED", subtext=None, icon=None):
    """Render a large KPI card with big number and optional subtext/icon."""
    if value is None:
        value = 0
    value_fmt = f"{value:,}" if isinstance(value, (int, float)) else str(value)
    icon_html = f"<span style='font-size:22px;margin-right:8px'>{icon}</span>" if icon else ""
    sub_html = f"<div style='font-size:13px;color:#6c757d;margin-top:6px'>{subtext}</div>" if subtext else ""
    st.markdown(f"""
    <div style='background:{color}15;border:1px solid {color}30;border-radius:14px;padding:16px 18px'>
      <div style='font-size:14px;color:#3a3a3a;font-weight:600'>{icon_html}{title}</div>
      <div style='font-size:36px;font-weight:700;color:{color};line-height:1;margin-top:6px'>{value_fmt}</div>
      {sub_html}
    </div>
    """, unsafe_allow_html=True)

# -----------------------------
# Compute KPIs and filtered data
# -----------------------------
@st.cache_data(show_spinner=False)
def compute_metrics(prs_df, pos_df, pr_map, po_map, cfg):
    if prs_df is None and pos_df is None:
        return {}, pd.DataFrame(), pd.DataFrame()

    # Copy for safe operations
    prs = prs_df.copy() if prs_df is not None else pd.DataFrame()
    pos = pos_df.copy() if pos_df is not None else pd.DataFrame()

    # Parse dates according to setting
    def parse_date(s):
        if pd.isna(s):
            return pd.NaT
        if cfg.get("date_format") == "dd-mm-yyyy":
            try:
                return pd.to_datetime(s, dayfirst=True, errors='coerce')
            except:
                return pd.to_datetime(s, errors='coerce')
        elif cfg.get("date_format") == "yyyy-mm-dd":
            try:
                return pd.to_datetime(s, errors='coerce')
            except:
                return pd.to_datetime(s, errors='coerce')
        else:
            return pd.to_datetime(s, errors='coerce', dayfirst=True)

    # Rename mapped fields to unified names
    def unify(df, mapping, required, optional):
        if df.empty:
            return df
        m = {mapping[k]: k for k in (required + optional) if mapping.get(k) and mapping[k] != "— not mapped —"}
        df = df.rename(columns=m)
        # Dates
        if "PR_Date" in df.columns:
            df["PR_Date"] = df["PR_Date"].apply(parse_date)
        if "PO_Date" in df.columns:
            df["PO_Date"] = df["PO_Date"].apply(parse_date)
        return df

    prs = unify(prs, pr_map, REQUIRED_PRS_FIELDS, OPTIONAL_PRS_FIELDS)
    pos = unify(pos, po_map, REQUIRED_POS_FIELDS, OPTIONAL_POS_FIELDS)

    # Derive Category where missing
    cfg_map = config.get("category_mapping", {})
    if "Category" not in prs.columns and not prs.empty:
        prs["Category"] = prs.apply(lambda r: derive_category(r, pr_map, cfg_map), axis=1)
    if "Category" not in pos.columns and not pos.empty:
        pos["Category"] = pos.apply(lambda r: derive_category(r, po_map, cfg_map), axis=1)

    # Link PR→PO via PR_Number if available
    linked_prs = set()
    if "PR_Number" in pos.columns:
        linked_vals = pos["PR_Number"].dropna().astype(str).str.strip()
        linked_prs = set(linked_vals)

    # Open PR logic
    pr_open_statuses = [s.lower() for s in config.get("pr_open_statuses", [])]
    def is_pr_open(row):
        status = str(row.get("PR_Status", "")).lower()
        pr_no = str(row.get("PR_Number", "")).strip()
        linked = pr_no in linked_prs
        return (status != "closed") or (not linked) or (status in pr_open_statuses)

    prs["Is_Open_PR"] = prs.apply(is_pr_open, axis=1)

    # Open Delivery PO logic
    po_open_statuses = [s.lower() for s in config.get("po_open_delivery_statuses", [])]
    def is_po_open_delivery(row):
        status = str(row.get("Delivery_Status", "")).lower()
        qty = row.get("PO_Quantity") if "PO_Quantity" in row else None
        grn = row.get("GRN_Quantity") if "GRN_Quantity" in row else None
        outstanding = False
        try:
            if pd.notna(qty) and pd.notna(grn):
                outstanding = (float(qty) - float(grn)) > 0
        except:
            outstanding = False
        return outstanding or (status in po_open_statuses) or (status == "open")

    if not pos.empty:
        pos["Is_Open_Delivery_PO"] = pos.apply(is_po_open_delivery, axis=1)

    # KPIs
    total_prs = int(len(prs)) if not prs.empty else 0
    total_pos = int(len(pos)) if not pos.empty else 0
    open_prs = int(prs["Is_Open_PR"].sum()) if "Is_Open_PR" in prs.columns else 0
    open_delivery_pos = int(pos["Is_Open_Delivery_PO"].sum()) if "Is_Open_Delivery_PO" in pos.columns else 0

    metrics = {
        "Total PRs": total_prs,
        "Total POs": total_pos,
        "Open PRs": open_prs,
        "Open Delivery POs": open_delivery_pos
    }

    return metrics, prs, pos

# -----------------------------
# Charts
# -----------------------------
def category_grouped_bar(prs, pos):
    # Count per category for PRs and POs
    cat_pr = prs.groupby('Category', dropna=False).size().reset_index(name='PRs') if not prs.empty else pd.DataFrame(columns=['Category','PRs'])
    cat_po = pos.groupby('Category', dropna=False).size().reset_index(name='POs') if not pos.empty else pd.DataFrame(columns=['Category','POs'])
    cat = pd.merge(cat_pr, cat_po, on='Category', how='outer').fillna(0)
    cat = cat[cat['Category'].isin(CATEGORIES)]
    cat_long = cat.melt(id_vars=['Category'], value_vars=['PRs','POs'], var_name='Type', value_name='Count')
    color_scale = alt.Scale(domain=CATEGORIES, range=[config['category_colors'][c] for c in CATEGORIES])
    chart = alt.Chart(cat_long).mark_bar().encode(
        x=alt.X('Type:N', title=''),
        y=alt.Y('Count:Q', title='Count'),
        column=alt.Column('Category:N', title='Category'),
        color=alt.Color('Category:N', scale=color_scale),
        tooltip=['Category', 'Type', 'Count']
    ).properties(height=280).configure_view(strokeOpacity=0)
    return chart, cat

def category_donut(prs, pos, which='PRs'):
    if which == 'PRs':
        base = prs
    else:
        base = pos
    if base.empty:
        return alt.Chart(pd.DataFrame({'Category':[], 'Count':[]})).mark_arc(), pd.DataFrame()
    cat = base.groupby('Category', dropna=False).size().reset_index(name='Count')
    cat = cat[cat['Category'].isin(CATEGORIES)]
    color_scale = alt.Scale(domain=CATEGORIES, range=[config['category_colors'][c] for c in CATEGORIES])
    chart = alt.Chart(cat).mark_arc(innerRadius=60).encode(
        theta='Count:Q',
        color=alt.Color('Category:N', scale=color_scale),
        tooltip=['Category', 'Count']
    ).properties(height=300)
    return chart, cat

def monthly_trend(df, date_col, title):
    if df.empty or date_col not in df.columns:
        return alt.Chart(pd.DataFrame({'Month':[], 'Count':[]})).mark_line(), pd.DataFrame()
    tmp = df.dropna(subset=[date_col]).copy()
    tmp['Month'] = tmp[date_col].dt.to_period('M').astype(str)
    trend = tmp.groupby(['Month','Category']).size().reset_index(name='Count')
    color_scale = alt.Scale(domain=CATEGORIES, range=[config['category_colors'][c] for c in CATEGORIES])
    chart = alt.Chart(trend).mark_line(point=True).encode(
        x=alt.X('Month:N', sort=None),
        y=alt.Y('Count:Q'),
        color=alt.Color('Category:N', scale=color_scale),
        tooltip=['Month','Category','Count']
    ).properties(height=280, title=title).configure_view(strokeOpacity=0)
    return chart, trend

# -----------------------------
# Upload & Column Mapper Page
# -----------------------------
if page == "Upload & Column Mapper":
    st.title("📥 Upload & Column Mapper")
    uploaded = st.file_uploader("Upload Excel (with sheets: PRs, POs, optional Category_Mapping)", type=["xlsx"])
    prs_df, pos_df, cat_map_df = read_excel(uploaded, date_format=config.get("date_format","auto"))

    if uploaded and cat_map_df is not None and not cat_map_df.empty:
        # Load mapping from sheet
        try:
            # Expect columns: Key_Field, Category
            for _, r in cat_map_df.iterrows():
                key = str(r.get('Key_Field', '')).strip()
                cat = str(r.get('Category', '')).strip()
                if key and cat in CATEGORIES:
                    config.setdefault('category_mapping', {})[key] = cat
            save_config(config)
            st.success("Category mapping loaded from Excel.")
        except Exception as e:
            st.warning(f"Could not parse Category_Mapping sheet: {e}")

    st.markdown("---")
    pr_map = column_mapper(prs_df, "PRs", REQUIRED_PRS_FIELDS, OPTIONAL_PRS_FIELDS)
    st.markdown("---")
    po_map = column_mapper(pos_df, "POs", REQUIRED_POS_FIELDS, OPTIONAL_POS_FIELDS)

    # In-app category mapping editor
    st.markdown("---")
    st.subheader("🗂️ Category Mapping Editor")
    st.caption("Map your Material_Group / Cost_Center / Item_Type values to one of: MRO, Services, Capex, PCM")
    cfg_map_items = sorted(config.get('category_mapping', {}).items())
    map_df = pd.DataFrame(cfg_map_items, columns=['Key_Field','Category']) if cfg_map_items else pd.DataFrame(columns=['Key_Field','Category'])
    edited = st.data_editor(map_df, num_rows="dynamic", use_container_width=True)
    if st.button("💾 Save Category Mapping"):
        new_map = {}
        for _, r in edited.iterrows():
            key = str(r.get('Key_Field','')).strip()
            cat = str(r.get('Category','')).strip()
            if key and cat in CATEGORIES:
                new_map[key] = cat
        config['category_mapping'] = new_map
        save_config(config)
        st.success("Category mapping saved.")
    # Export mapping to Excel
    if st.button("⬇️ Export Mapping to Excel"):
        out = pd.DataFrame(sorted(config.get('category_mapping', {}).items()), columns=['Key_Field','Category'])
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            out.to_excel(writer, index=False, sheet_name='Category_Mapping')
        st.download_button("Download Category_Mapping.xlsx", data=buf.getvalue(), file_name="Category_Mapping.xlsx")

# -----------------------------
# Dashboard Page
# -----------------------------
elif page == "Dashboard":
    st.title("📈 Dashboard")
    uploaded = st.file_uploader("Upload Excel (with sheets: PRs, POs, optional Category_Mapping)", type=["xlsx"], key="dash_upload")
    prs_df, pos_df, _ = read_excel(uploaded, date_format=config.get("date_format","auto"))

    pr_map = config.get("column_mapping", {}).get("PRs", {})
    po_map = config.get("column_mapping", {}).get("POs", {})

    metrics, prs, pos = compute_metrics(prs_df, pos_df, pr_map, po_map, config)

    # Filters panel
    with st.expander("🔎 Filters", expanded=True):
        # Date range filters
        pr_min_date = pd.to_datetime(prs['PR_Date']).min() if ('PR_Date' in prs.columns and not prs.empty) else None
        pr_max_date = pd.to_datetime(prs['PR_Date']).max() if ('PR_Date' in prs.columns and not prs.empty) else None
        po_min_date = pd.to_datetime(pos['PO_Date']).min() if ('PO_Date' in pos.columns and not pos.empty) else None
        po_max_date = pd.to_datetime(pos['PO_Date']).max() if ('PO_Date' in pos.columns and not pos.empty) else None

        colA, colB = st.columns(2)
        with colA:
            pr_date_rng = st.date_input("PR Date Range", value=(pr_min_date, pr_max_date) if pr_min_date and pr_max_date else None)
        with colB:
            po_date_rng = st.date_input("PO Date Range", value=(po_min_date, po_max_date) if po_min_date and po_max_date else None)

        categories_filter = st.multiselect("Category", CATEGORIES, default=CATEGORIES)
        vendor_filter = st.multiselect("Vendor (if present)", sorted(pos['Vendor'].dropna().unique()) if 'Vendor' in pos.columns else [])
        buyer_filter = st.multiselect("Buyer (if present)", sorted(prs['Buyer'].dropna().unique()) if 'Buyer' in prs.columns else [])
        status_filter_pr = st.multiselect("PR Status", sorted(prs['PR_Status'].dropna().unique()) if 'PR_Status' in prs.columns else [])
        status_filter_po = st.multiselect("PO Status", sorted(pos['PO_Status'].dropna().unique()) if 'PO_Status' in pos.columns else [])

    # Apply filters
    def within_date(df, col, rng):
        if df.empty or col not in df.columns or not rng or len(rng) != 2:
            return df
        start, end = pd.to_datetime(rng[0]), pd.to_datetime(rng[1])
        return df[(df[col] >= start) & (df[col] <= end)]

    prs_f = within_date(prs, 'PR_Date', pr_date_rng)
    pos_f = within_date(pos, 'PO_Date', po_date_rng)
    if categories_filter:
        prs_f = prs_f[prs_f['Category'].isin(categories_filter)] if 'Category' in prs_f.columns else prs_f
        pos_f = pos_f[pos_f['Category'].isin(categories_filter)] if 'Category' in pos_f.columns else pos_f
    if vendor_filter and 'Vendor' in pos_f.columns:
        pos_f = pos_f[pos_f['Vendor'].isin(vendor_filter)]
    if buyer_filter and 'Buyer' in prs_f.columns:
        prs_f = prs_f[prs_f['Buyer'].isin(buyer_filter)]
    if status_filter_pr and 'PR_Status' in prs_f.columns:
        prs_f = prs_f[prs_f['PR_Status'].isin(status_filter_pr)]
    if status_filter_po and 'PO_Status' in pos_f.columns:
        pos_f = pos_f[pos_f['PO_Status'].isin(status_filter_po)]

    # Recompute metrics after filters
    metrics_f, _, _ = compute_metrics(prs_f, pos_f, pr_map, po_map, config)

    # Big KPI tiles (updated per your request: "total values big size & category value")
    st.markdown("### Key KPIs")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        big_number_card("Total PRs", metrics_f.get("Total PRs",0), color="#2F80ED", icon="📄")
    with k2:
        big_number_card("Total POs", metrics_f.get("Total POs",0), color="#20B2AA", icon="🧾")
    with k3:
        big_number_card("Open PRs", metrics_f.get("Open PRs",0), color="#F2994A", icon="⏳")
    with k4:
        big_number_card("Open Delivery POs", metrics_f.get("Open Delivery POs",0), color="#8E44AD", icon="🚚")

    st.markdown("### Category Snapshot (Counts)")
    # Category cards showing PR & PO counts per category
    cat_bar, cat_counts = category_grouped_bar(prs_f, pos_f)
    # Build cards from cat_counts
    cols = st.columns(4)
    for idx, cat in enumerate(CATEGORIES):
        with cols[idx]:
            row = cat_counts[cat_counts['Category']==cat]
            pr_c = int(row['PRs'].iloc[0]) if not row.empty else 0
            po_c = int(row['POs'].iloc[0]) if not row.empty else 0
            big_number_card(f"{cat}", f"PRs: {pr_c} | POs: {po_c}", color=config['category_colors'][cat])

    st.markdown("### Category-wise Grouped Bars")
    st.altair_chart(cat_bar, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        donut_pr, _ = category_donut(prs_f, pos_f, which='PRs')
        st.altair_chart(donut_pr.properties(title='PRs Category Share'), use_container_width=True)
    with c2:
        donut_po, _ = category_donut(prs_f, pos_f, which='POs')
        st.altair_chart(donut_po.properties(title='POs Category Share'), use_container_width=True)

    t1, t2 = st.columns(2)
    with t1:
        tr_pr, _ = monthly_trend(prs_f, 'PR_Date', 'Monthly PR Trend by Category')
        st.altair_chart(tr_pr, use_container_width=True)
    with t2:
        tr_po, _ = monthly_trend(pos_f, 'PO_Date', 'Monthly PO Trend by Category')
        st.altair_chart(tr_po, use_container_width=True)

    st.markdown("### Detailed Tables")
    tab1, tab2 = st.tabs(["PRs", "POs"])
    with tab1:
        st.dataframe(prs_f, use_container_width=True)
        # Export filtered PRs
        buf_pr = io.BytesIO()
        with pd.ExcelWriter(buf_pr, engine='openpyxl') as writer:
            prs_f.to_excel(writer, index=False, sheet_name='PRs')
        st.download_button("⬇️ Export PRs (filtered)", buf_pr.getvalue(), file_name="PRs_filtered.xlsx")
    with tab2:
        st.dataframe(pos_f, use_container_width=True)
        buf_po = io.BytesIO()
        with pd.ExcelWriter(buf_po, engine='openpyxl') as writer:
            pos_f.to_excel(writer, index=False, sheet_name='POs')
        st.download_button("⬇️ Export POs (filtered)", buf_po.getvalue(), file_name="POs_filtered.xlsx")

    st.caption("Tip: Use the Filters to focus on specific Categories like MRO/Services/Capex/PCM.")

# -----------------------------
# Data Health Page
# -----------------------------
else:
    if page == "Data Health":
        st.title("🩺 Data Health")
        uploaded = st.file_uploader("Upload Excel to inspect", type=["xlsx"], key="health_upload")
        prs_df, pos_df, cat_map_df = read_excel(uploaded, date_format=config.get("date_format","auto"))
        pr_map = config.get("column_mapping", {}).get("PRs", {})
        po_map = config.get("column_mapping", {}).get("POs", {})

        missing_pr = [f for f in REQUIRED_PRS_FIELDS if pr_map.get(f) in (None, "— not mapped —")]
        missing_po = [f for f in REQUIRED_POS_FIELDS if po_map.get(f) in (None, "— not mapped —")]

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Required Fields – PRs")
            st.write(REQUIRED_PRS_FIELDS)
            st.warning(f"Missing mappings: {missing_pr}")
        with col2:
            st.subheader("Required Fields – POs")
            st.write(REQUIRED_POS_FIELDS)
            st.warning(f"Missing mappings: {missing_po}")

        if cat_map_df is not None and not cat_map_df.empty:
            st.subheader("Category_Mapping sheet preview")
            st.dataframe(cat_map_df.head(20), use_container_width=True)
        else:
            st.info("No Category_Mapping sheet found – you can create mapping in the Upload & Column Mapper page.")

        st.subheader("Column Presence in Uploaded Sheets")
        if prs_df is not None:
            st.write({c: str(prs_df[c].dtype) for c in prs_df.columns})
        if pos_df is not None:
            st.write({c: str(pos_df[c].dtype) for c in pos_df.columns})

        st.caption("Check that dates parse correctly and mapping covers all key_field values.")
