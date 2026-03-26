import streamlit as st
import xarray as xr
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import geopandas as gpd
import os

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Climate Anomaly Explorer",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# CUSTOM CSS — Light mode with warm orange tint
# ============================================================
BG = "#FFF8F2"
CARD_BG = "#FFFFFF"
BORDER = "#E8DDD4"
TEXT = "#1E293B"
TEXT_MUTED = "#64748B"
ACCENT = "#B91C1C"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    .stApp {{
        background-color: {BG};
        color: {TEXT};
        font-family: 'Inter', sans-serif;
    }}
    h1, h2, h3 {{ font-weight: 600; letter-spacing: -0.02em; color: {TEXT}; }}

    div[data-testid="stMetricValue"] {{
        font-size: 1.85rem;
        font-weight: 700;
        color: {ACCENT};
    }}
    div[data-testid="stMetricLabel"] {{
        color: {TEXT_MUTED};
    }}
    div[data-testid="metric-container"] {{
        background-color: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }}

    [data-testid="stSidebar"] {{
        background-color: #FFF5EB;
        border-right: 1px solid {BORDER};
    }}
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span {{
        color: {TEXT} !important;
    }}

    hr {{ border-color: {BORDER}; }}

    [data-testid="stExpander"] {{
        background-color: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }}
    [data-testid="stExpander"] summary {{
        font-weight: 600;
        color: {TEXT};
    }}
</style>
""", unsafe_allow_html=True)


# ============================================================
# DATA LOADING
# ============================================================
SHAPEFILE_PATH = os.path.join(os.path.dirname(__file__), "shapefiles", "ne_110m_admin_0_countries.shp")

@st.cache_resource(show_spinner="Loading and optimizing 11 years of atmospheric data…")
def load_and_optimize_data():
    ds = xr.open_mfdataset("air.sig995.*.nc", parallel=True, chunks={"time": 100})
    if "air" in ds.variables:
        ds["air"] = ds["air"] - 273.15
    ds_monthly = ds.resample(time="1MS").mean(dim="time").compute()
    ds_monthly.coords["lon"] = (ds_monthly.coords["lon"] + 180) % 360 - 180
    ds_monthly = ds_monthly.sortby(ds_monthly.lon)
    return ds_monthly

@st.cache_resource
def load_world():
    return gpd.read_file(SHAPEFILE_PATH)

@st.cache_data
def extract_borders(_world):
    """Extract all country border line coordinates as a single optimized pair of lists."""
    border_lons = []
    border_lats = []
    for _, row in _world.iterrows():
        geom = row.geometry
        polys = []
        if geom.geom_type == 'Polygon':
            polys = [geom]
        elif geom.geom_type == 'MultiPolygon':
            polys = list(geom.geoms)
        for poly in polys:
            coords = list(poly.exterior.coords)
            lons, lats = zip(*coords)
            border_lons.extend(lons)
            border_lats.extend(lats)
            border_lons.append(None)
            border_lats.append(None)
    return border_lons, border_lats

try:
    ds = load_and_optimize_data()
    world = load_world()
    border_lons, border_lats = extract_borders(world)
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()


# ============================================================
# PLOTLY COLORSCALE — Climate Pulse
# ============================================================
climate_pulse_colorscale = [
    [0.0,   "#053061"],
    [0.07,  "#2166ac"],
    [0.14,  "#4393c3"],
    [0.21,  "#92c5de"],
    [0.35,  "#d1e5f0"],
    [0.5,   "#f7f7f7"],
    [0.65,  "#fddbc7"],
    [0.79,  "#f4a582"],
    [0.86,  "#d6604d"],
    [0.93,  "#b2182b"],
    [1.0,   "#67001f"],
]


# ============================================================
# SIDEBAR CONTROLS
# ============================================================
# st.sidebar.markdown("### ⚙️ Analytical Controls")

years_available = sorted(np.unique(ds["time"].dt.year.values))
month_names = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

st.sidebar.markdown("**1. Temporal Target**")
target_year = st.sidebar.select_slider(
    "Target Year", options=years_available, value=int(years_available[-1])
)
target_month_idx = st.sidebar.select_slider(
    "Target Month", options=list(range(1, 13)), value=1,
    format_func=lambda x: month_names[x - 1],
)

st.sidebar.markdown("**2. Baseline Period**")
baseline_start = st.sidebar.selectbox("Start", options=years_available, index=0)
baseline_end   = st.sidebar.selectbox("End",   options=years_available, index=len(years_available) - 1)

if baseline_start > baseline_end:
    st.sidebar.error("Start year must be ≤ End year.")
    st.stop()


# ============================================================
# CORE COMPUTATION
# ============================================================
baseline_ds  = ds.sel(time=slice(f"{baseline_start}-01-01", f"{baseline_end}-12-31"))
climatology  = baseline_ds.groupby("time.month").mean("time")

target_date  = f"{target_year}-{target_month_idx:02d}"
try:
    target_data = ds.sel(time=target_date)
except KeyError:
    st.error("Selected period is outside the dataset range.")
    st.stop()

anomaly = (target_data["air"] - climatology["air"].sel(month=target_month_idx)).squeeze()


# ============================================================
# HEADER + KPI METRICS
# ============================================================
st.title("Climate Anomaly Explorer")
st.markdown(
    "Monitoring global temperature anomalies from "
    "NOAA NCEP/NCAR Reanalysis 1 (2015–2025)."
)

anom_vals = anomaly.values
max_anom  = float(np.nanmax(anom_vals))
min_anom  = float(np.nanmin(anom_vals))
avg_anom  = float(np.nanmean(anom_vals))

col1, col2, col3 = st.columns(3)
col1.metric("🌍 Global Average Anomaly",  f"{avg_anom:+.2f} °C")
col2.metric("🔥 Max Hotspot",             f"{max_anom:+.2f} °C")
col3.metric("❄️ Max Coldspot",            f"{min_anom:+.2f} °C")

st.markdown("")


# ============================================================
# SECTION 1 — INTERACTIVE ANOMALY MAP (Plotly WebGL)
# ============================================================
with st.expander(
    f"Surface Air Temperature Anomaly — {month_names[target_month_idx-1]} {target_year}  (baseline {baseline_start}–{baseline_end})",
    expanded=True
):
    fig_map = go.Figure()

    # 1. Filled contour layer — renders as WebGL vector, supports zoom & hover natively
    fig_map.add_trace(go.Contour(
        z=anomaly.values,
        x=anomaly.lon.values,
        y=anomaly.lat.values,
        colorscale=climate_pulse_colorscale,
        zmin=-7,
        zmax=7,
        contours=dict(
            coloring="heatmap",
            showlines=False,
        ),
        line=dict(width=0),
        colorbar=dict(
            title=dict(text="°C", side="right"),
            thickness=15,
            len=0.9,
            tickvals=[-7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7],
            tickfont=dict(size=11, color="#333"),
            outlinewidth=0,
        ),
        hovertemplate=(
            "<b>Lat:</b> %{y:.1f}°<br>"
            "<b>Lon:</b> %{x:.1f}°<br>"
            "<b>Anomaly:</b> %{z:+.2f} °C"
            "<extra></extra>"
        ),
    ))

    # 2. Country borders as a single vector trace (always crisp at any zoom)
    fig_map.add_trace(go.Scattergl(
        x=border_lons,
        y=border_lats,
        mode="lines",
        line=dict(color="#5a5a5a", width=0.8),
        hoverinfo="skip",
        showlegend=False,
    ))

    fig_map.update_layout(
        xaxis=dict(
            range=[-180, 180],
            showgrid=False,
            zeroline=False,
            visible=False,
            constrain="domain",
        ),
        yaxis=dict(
            range=[-90, 90],
            showgrid=False,
            zeroline=False,
            visible=False,
            scaleanchor="x",
            scaleratio=1,
        ),
        plot_bgcolor=BG,
        paper_bgcolor=BG,
        margin=dict(l=0, r=0, t=0, b=0),
        height=550,
    )

    st.plotly_chart(fig_map, use_container_width=True, config={
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToAdd": ["zoom2d", "pan2d", "resetScale2d"],
    })


# ============================================================
# SECTION 2 — INTERACTIVE ANNUAL TEMPERATURE TRENDS (Plotly)
# ============================================================
with st.expander("Global Surface Air Temperature", expanded=True):
    global_monthly = ds.mean(dim=["lat", "lon"])
    df_global = global_monthly["air"].to_dataframe(name="Temperature").reset_index()
    df_global["year"]  = df_global["time"].dt.year
    df_global["month"] = df_global["time"].dt.month

    all_years = sorted(df_global["year"].unique())
    baseline_monthly = df_global.groupby("month")["Temperature"].mean()

    fig_ts = go.Figure()

    highlight_years = all_years[-3:]
    highlight_colors = ["#F59E0B", "#EF4444", "#A855F7"]

    # Historical years as thin, light lines
    for yr in all_years:
        if yr not in highlight_years:
            yr_data = df_global[df_global["year"] == yr].sort_values("month")
            yr_months = [month_names[m-1] for m in yr_data["month"]]
            fig_ts.add_trace(go.Scatter(
                x=yr_data["month"],
                y=yr_data["Temperature"],
                mode="lines",
                line=dict(color="#CCBBAA", width=0.8),
                opacity=0.5,
                showlegend=False,
                text=yr_months,
                hovertemplate=f"<b>{yr}</b> – %{{text}}<br>Temperature: <b>%{{y:.2f}}°C</b><extra></extra>",
            ))

    # Baseline average (dashed)
    bl_months = [month_names[m-1] for m in baseline_monthly.index]
    fig_ts.add_trace(go.Scatter(
        x=list(baseline_monthly.index),
        y=list(baseline_monthly.values),
        mode="lines",
        line=dict(color="#64748B", width=2, dash="dash"),
        name=f"{all_years[0]}–{all_years[-1]} avg",
        text=bl_months,
        hovertemplate=f"{all_years[0]}–{all_years[-1]} average – %{{text}}<br>Temperature: <b>%{{y:.2f}}°C</b><extra></extra>",
    ))

    # Highlighted recent years
    for i, yr in enumerate(highlight_years):
        yr_data = df_global[df_global["year"] == yr].sort_values("month")
        yr_months = [month_names[m-1] for m in yr_data["month"]]
        fig_ts.add_trace(go.Scatter(
            x=yr_data["month"],
            y=yr_data["Temperature"],
            mode="lines",
            line=dict(color=highlight_colors[i], width=2.5),
            name=str(yr),
            text=yr_months,
            hovertemplate=f"<b>{yr}</b> – %{{text}}<br>Temperature: <b>%{{y:.2f}}°C</b><extra></extra>",
        ))

    fig_ts.update_layout(
        xaxis=dict(
            tickmode="array",
            tickvals=list(range(1, 13)),
            ticktext=month_names,
            showgrid=True,
            gridcolor="#E8DDD4",
            gridwidth=0.5,
            zeroline=False,
        ),
        yaxis=dict(
            title="Temperature (°C)",
            showgrid=True,
            gridcolor="#E8DDD4",
            gridwidth=0.5,
            zeroline=False,
        ),
        plot_bgcolor=BG,
        paper_bgcolor=BG,
        hovermode="closest",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
            font=dict(size=11, color="#333"),
        ),
        margin=dict(l=50, r=20, t=20, b=60),
        height=450,
    )

    st.plotly_chart(fig_ts, use_container_width=True)


st.markdown("---")
st.caption(
    "Built with Python · Xarray · Dask · Plotly · GeoPandas  ·  "
    "Data: NOAA NCEP/NCAR Reanalysis 1"
)