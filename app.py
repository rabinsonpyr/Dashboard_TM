"""
Cloud-hosted sales dashboard.
Deploy this on Streamlit Community Cloud (share.streamlit.io) — see README.md.
"""

import io
import logging

import requests
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

import config

st.set_page_config(page_title="Sales Dashboard", layout="wide")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dashboard")


# ---------------------------------------------------------------------------
# Password gate
# ---------------------------------------------------------------------------
def check_password() -> bool:
    if not config.APP_PASSWORD:
        st.error(
            "No APP_PASSWORD configured. Add it under this app's Settings → "
            "Secrets on Streamlit Cloud."
        )
        st.stop()

    if st.session_state.get("authenticated"):
        return True

    st.title("🔒 Sales Dashboard")
    pwd = st.text_input("Password", type="password")
    if st.button("Enter"):
        if pwd == config.APP_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()


# ---------------------------------------------------------------------------
# Data loading — fetch the Excel file from Google Drive and clean it
# ---------------------------------------------------------------------------
@st.cache_data(ttl=config.REFRESH_SECONDS, show_spinner="Fetching latest data...")
def load_data() -> pd.DataFrame:
    if not config.GOOGLE_DRIVE_FILE_ID:
        st.error(
            "No GOOGLE_DRIVE_FILE_ID configured. Add it under this app's "
            "Settings → Secrets on Streamlit Cloud."
        )
        st.stop()

    url = f"https://drive.google.com/uc?export=download&id={config.GOOGLE_DRIVE_FILE_ID}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    try:
        df = pd.read_excel(io.BytesIO(resp.content))
    except Exception:
        st.error(
            "Could not read the Excel file from Google Drive. Make sure the "
            "file is shared as 'Anyone with the link can view' and that the "
            "GOOGLE_DRIVE_FILE_ID secret is correct."
        )
        st.stop()

    required = [
        config.COL_DATE, config.COL_SALES, config.COL_WOLT,
        config.COL_UBEREATS, config.COL_TOTAL, config.COL_TIPS,
        config.COL_PERSON, config.COL_CASH,
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"Missing expected columns in the Excel file: {missing}")
        st.stop()

    df[config.COL_DATE] = pd.to_datetime(df[config.COL_DATE], errors="coerce")
    df[config.COL_PERSON] = df[config.COL_PERSON].astype(str).str.strip()

    num_cols = [config.COL_SALES, config.COL_WOLT, config.COL_UBEREATS,
                config.COL_TOTAL, config.COL_TIPS, config.COL_CASH]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=[config.COL_DATE]).reset_index(drop=True)
    df = df.sort_values(config.COL_DATE).reset_index(drop=True)
    df["Day"] = df[config.COL_DATE].dt.day_name()
    return df


df = load_data()

st.title("📊 Sales Dashboard")

col_title, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()

st.caption(f"Data auto-refreshes at least every {config.REFRESH_SECONDS} seconds.")

with st.expander("🔍 Debug info (click if the dashboard looks empty)"):
    st.write(f"Rows loaded: **{len(df)}**")
    if not df.empty:
        st.write(f"Date range: **{df[config.COL_DATE].min().date()}** to **{df[config.COL_DATE].max().date()}**")
        st.write("Unique values in Person column:", df[config.COL_PERSON].dropna().unique().tolist())

# ---- Sidebar filters ----
st.sidebar.header("Filters")
min_date, max_date = df[config.COL_DATE].min().date(), df[config.COL_DATE].max().date()

if min_date == max_date:
    st.sidebar.info(f"Only one date in the data so far: {min_date}")
    date_range = (min_date, max_date)
else:
    date_range = st.sidebar.date_input(
        "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
    )
    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        date_range = (min_date, max_date)

people = sorted(df[config.COL_PERSON].dropna().unique().tolist())
if st.sidebar.button("Reset filters"):
    st.rerun()
selected_people = st.sidebar.multiselect("Person", options=people, default=people)

start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
df = df[(df[config.COL_DATE].dt.normalize() >= start) & (df[config.COL_DATE].dt.normalize() <= end)]
if selected_people:
    df = df[df[config.COL_PERSON].isin(selected_people)]

if df.empty:
    st.warning(
        "No data for the selected filters. Try clicking **Reset filters** in the "
        "sidebar, or expand the Debug info box above."
    )
    st.stop()

# ---- KPI row ----
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Revenue", f"{df[config.COL_TOTAL].sum():,.0f} {config.CURRENCY}")
c2.metric("Total Tips", f"{df[config.COL_TIPS].sum():,.0f} {config.CURRENCY}")
c3.metric("Total Cash Held", f"{df[config.COL_CASH].sum():,.0f} {config.CURRENCY}")
c4.metric("Days Recorded", f"{df[config.COL_DATE].nunique()}")
c5.metric("Avg Daily Revenue", f"{df[config.COL_TOTAL].mean():,.0f} {config.CURRENCY}")

st.divider()

# ---- Revenue trend over time ----
st.subheader("Revenue Over Time")

CHANNEL_COLORS = {
    config.COL_SALES: "#1f77b4",     # blue
    config.COL_WOLT: "#F5A623",      # orange
    config.COL_UBEREATS: "#06C167",  # green
}

daily_channel = (
    df.groupby(config.COL_DATE)[[config.COL_SALES, config.COL_WOLT, config.COL_UBEREATS]]
    .sum()
    .reset_index()
)
melted = daily_channel.melt(
    id_vars=[config.COL_DATE],
    value_vars=[config.COL_SALES, config.COL_WOLT, config.COL_UBEREATS],
    var_name="Channel", value_name="Revenue",
)

fig1 = px.area(
    melted, x=config.COL_DATE, y="Revenue", color="Channel",
    color_discrete_map=CHANNEL_COLORS,
    labels={config.COL_DATE: "Date", "Revenue": f"Revenue ({config.CURRENCY})"},
    text="Revenue",
)
fig1.update_xaxes(tickformat="%Y-%m-%d", dtick="D1", hoverformat="%Y-%m-%d (%A)")
fig1.update_traces(
    textposition="top center", texttemplate=f"%{{y:,.0f}} {config.CURRENCY}",
    hovertemplate=f"%{{fullData.name}}: %{{y:,.0f}} {config.CURRENCY}<extra></extra>",
)
fig1.update_layout(hovermode="x unified")
st.plotly_chart(fig1, use_container_width=True)

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.subheader("Revenue Share by Channel")
    totals = {
        config.COL_SALES: df[config.COL_SALES].sum(),
        config.COL_WOLT: df[config.COL_WOLT].sum(),
        config.COL_UBEREATS: df[config.COL_UBEREATS].sum(),
    }
    fig2 = px.pie(
        names=list(totals.keys()), values=list(totals.values()), hole=0.4,
        color=list(totals.keys()),
        color_discrete_map=CHANNEL_COLORS,
    )
    fig2.update_traces(hovertemplate=f"%{{label}}: %{{value:,.0f}} {config.CURRENCY} (%{{percent}})<extra></extra>")
    st.plotly_chart(fig2, use_container_width=True)

PERSON_COLORS = {"Rabinson": "#FF6B35", "Sapana": "#0074D9"}

with col_b:
    st.subheader("Tips by Person")
    tips_by_person = (
        df.groupby(config.COL_PERSON)[config.COL_TIPS]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    fig3 = px.bar(
        tips_by_person, x=config.COL_PERSON, y=config.COL_TIPS, color=config.COL_PERSON,
        color_discrete_map=PERSON_COLORS,
        labels={config.COL_PERSON: "Person", config.COL_TIPS: f"Tips ({config.CURRENCY})"},
        text=config.COL_TIPS,
    )
    fig3.update_traces(texttemplate=f"%{{y:,.0f}} {config.CURRENCY}", textposition="outside")
    fig3.update_layout(showlegend=False)
    st.plotly_chart(fig3, use_container_width=True)

with col_c:
    st.subheader("Cash Held by Person")
    cash_by_person = (
        df.groupby(config.COL_PERSON)[config.COL_CASH]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    fig5 = px.bar(
        cash_by_person, x=config.COL_PERSON, y=config.COL_CASH, color=config.COL_PERSON,
        color_discrete_map=PERSON_COLORS,
        labels={config.COL_PERSON: "Person", config.COL_CASH: f"Cash ({config.CURRENCY})"},
        text=config.COL_CASH,
    )
    fig5.update_traces(texttemplate=f"%{{y:,.0f}} {config.CURRENCY}", textposition="outside")
    fig5.update_layout(showlegend=False)
    st.plotly_chart(fig5, use_container_width=True)

st.subheader("Total Sales per Day")

daily_channel["Computed Total"] = (
    daily_channel[config.COL_SALES] + daily_channel[config.COL_WOLT] + daily_channel[config.COL_UBEREATS]
)

fig4 = px.bar(
    melted, x=config.COL_DATE, y="Revenue", color="Channel",
    color_discrete_map=CHANNEL_COLORS,
    labels={config.COL_DATE: "Date", "Revenue": f"Revenue ({config.CURRENCY})"},
    barmode="stack",
)
fig4.update_xaxes(tickformat="%Y-%m-%d", dtick="D1", hoverformat="%Y-%m-%d (%A)")
fig4.update_traces(hovertemplate=f"%{{fullData.name}}: %{{y:,.0f}} {config.CURRENCY}<extra></extra>")

fig4.add_trace(go.Scatter(
    x=daily_channel[config.COL_DATE],
    y=daily_channel["Computed Total"],
    mode="text",
    text=[f"{v:,.0f} {config.CURRENCY}" for v in daily_channel["Computed Total"]],
    textposition="top center",
    textfont=dict(size=13, color="black"),
    showlegend=False,
    hoverinfo="skip",
))
st.plotly_chart(fig4, use_container_width=True)

st.subheader("Raw Data")
display_cols = [config.COL_DATE, "Day", config.COL_PERSON, config.COL_SALES,
                 config.COL_WOLT, config.COL_UBEREATS, config.COL_TOTAL,
                 config.COL_TIPS, config.COL_CASH]
display_cols = [c for c in display_cols if c in df.columns]
money_cols = [c for c in [config.COL_SALES, config.COL_WOLT, config.COL_UBEREATS,
                          config.COL_TOTAL, config.COL_TIPS, config.COL_CASH] if c in display_cols]
table_df = df[display_cols].sort_values(config.COL_DATE, ascending=False).copy()
table_df[config.COL_DATE] = table_df[config.COL_DATE].dt.strftime("%Y-%m-%d")
st.dataframe(
    table_df.style.format({c: f"{{:,.0f}} {config.CURRENCY}" for c in money_cols}),
    use_container_width=True,
    hide_index=True,
)
