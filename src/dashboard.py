"""Fantasy Football Analytics Dashboard — Streamlit app."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path for Streamlit's runner
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.config import SleeperConfig, ESPNConfig
from src.normalize import load_all_data, load_draft_data
from src import analytics


st.set_page_config(page_title="FFB Analytics", page_icon="🏈", layout="wide")

# =============================================================================
# DESIGN SYSTEM — Custom CSS for dark fintech/sports analytics look
# =============================================================================

# Color palette
COLORS = {
    "bg_primary": "#0B0E14",
    "bg_secondary": "#111621",
    "bg_card": "#161B28",
    "bg_card_hover": "#1C2235",
    "border": "#1E2538",
    "border_accent": "#2A3350",
    "text_primary": "#E8ECF4",
    "text_secondary": "#8A94A8",
    "text_muted": "#5A6378",
    "accent_cyan": "#00D4AA",
    "accent_blue": "#3B82F6",
    "accent_purple": "#8B5CF6",
    "accent_orange": "#F59E0B",
    "accent_red": "#EF4444",
    "accent_green": "#10B981",
    "positive": "#10B981",
    "negative": "#EF4444",
}

# Chart color sequence for plotly
CHART_COLORS = [
    "#00D4AA", "#3B82F6", "#8B5CF6", "#F59E0B", "#EF4444",
    "#10B981", "#EC4899", "#06B6D4", "#F97316", "#6366F1",
    "#14B8A6", "#E879F9", "#22D3EE", "#FB923C", "#818CF8",
]

# Plotly layout template for all charts
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(
        family="Inter, -apple-system, BlinkMacSystemFont, sans-serif",
        color=COLORS["text_secondary"],
        size=12,
    ),
    title_font=dict(color=COLORS["text_primary"], size=16),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["text_secondary"], size=11),
    ),
    xaxis=dict(
        gridcolor=COLORS["border"],
        zerolinecolor=COLORS["border"],
        tickfont=dict(color=COLORS["text_muted"]),
    ),
    yaxis=dict(
        gridcolor=COLORS["border"],
        zerolinecolor=COLORS["border"],
        tickfont=dict(color=COLORS["text_muted"]),
    ),
    hoverlabel=dict(
        bgcolor=COLORS["bg_card"],
        bordercolor=COLORS["border_accent"],
        font=dict(color=COLORS["text_primary"], size=12),
    ),
    margin=dict(l=40, r=20, t=40, b=40),
    colorway=CHART_COLORS,
)


def apply_chart_style(fig, height=500):
    """Apply consistent dark theme styling to a plotly figure."""
    fig.update_layout(**PLOTLY_LAYOUT, height=height, title="")
    return fig


CUSTOM_CSS = f"""
<style>
    /* Import Inter font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* Root & global overrides */
    .stApp {{
        background-color: {COLORS["bg_primary"]};
        color: {COLORS["text_primary"]};
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}

    /* Main content area */
    .main .block-container {{
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }}

    /* Headers */
    h1 {{
        color: {COLORS["text_primary"]} !important;
        font-weight: 700 !important;
        font-size: 1.8rem !important;
        letter-spacing: -0.02em !important;
        margin-bottom: 0.25rem !important;
    }}

    h2 {{
        color: {COLORS["text_primary"]} !important;
        font-weight: 600 !important;
        font-size: 1.3rem !important;
        letter-spacing: -0.01em !important;
        margin-top: 1.5rem !important;
    }}

    h3 {{
        color: {COLORS["text_primary"]} !important;
        font-weight: 600 !important;
        font-size: 1.1rem !important;
    }}

    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background-color: {COLORS["bg_secondary"]} !important;
        border-right: 1px solid {COLORS["border"]} !important;
    }}

    section[data-testid="stSidebar"] .block-container {{
        padding-top: 2rem;
    }}

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{
        color: {COLORS["text_primary"]} !important;
    }}

    section[data-testid="stSidebar"] label {{
        color: {COLORS["text_secondary"]} !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
    }}

    /* Sidebar multiselect / input styling */
    section[data-testid="stSidebar"] .stMultiSelect,
    section[data-testid="stSidebar"] .stSelectbox {{
        background-color: {COLORS["bg_card"]} !important;
        border-radius: 8px !important;
    }}

    /* Tab bar */
    .stTabs [data-baseweb="tab-list"] {{
        background-color: {COLORS["bg_secondary"]};
        border-radius: 12px;
        padding: 4px;
        gap: 4px;
        border: 1px solid {COLORS["border"]};
    }}

    .stTabs [data-baseweb="tab"] {{
        background-color: transparent;
        color: {COLORS["text_muted"]};
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 500;
        font-size: 0.85rem;
        border: none;
        transition: all 0.2s ease;
    }}

    .stTabs [data-baseweb="tab"]:hover {{
        color: {COLORS["text_primary"]};
        background-color: {COLORS["bg_card"]};
    }}

    .stTabs [aria-selected="true"] {{
        background-color: {COLORS["bg_card"]} !important;
        color: {COLORS["accent_cyan"]} !important;
        border: 1px solid {COLORS["border_accent"]} !important;
        font-weight: 600;
    }}

    /* Hide default tab underline */
    .stTabs [data-baseweb="tab-highlight"] {{
        display: none;
    }}

    .stTabs [data-baseweb="tab-border"] {{
        display: none;
    }}

    /* Metric cards (default st.metric) */
    [data-testid="stMetric"] {{
        background-color: {COLORS["bg_card"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 12px;
        padding: 1rem 1.25rem;
        transition: border-color 0.2s ease;
    }}

    [data-testid="stMetric"]:hover {{
        border-color: {COLORS["border_accent"]};
    }}

    [data-testid="stMetric"] label {{
        color: {COLORS["text_muted"]} !important;
        font-size: 0.75rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
    }}

    [data-testid="stMetric"] [data-testid="stMetricValue"] {{
        color: {COLORS["text_primary"]} !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }}

    [data-testid="stMetric"] [data-testid="stMetricDelta"] {{
        font-size: 0.85rem !important;
        font-weight: 500 !important;
    }}

    /* Dataframe / table styling */
    [data-testid="stDataFrame"] {{
        background-color: {COLORS["bg_card"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 12px;
        overflow: hidden;
    }}

    /* Plotly chart containers */
    [data-testid="stPlotlyChart"] {{
        background-color: {COLORS["bg_card"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 12px;
        padding: 1rem;
    }}

    /* Selectbox styling */
    .stSelectbox > div > div {{
        background-color: {COLORS["bg_card"]} !important;
        border-color: {COLORS["border"]} !important;
        color: {COLORS["text_primary"]} !important;
        border-radius: 8px !important;
    }}

    /* Multiselect */
    .stMultiSelect > div > div {{
        background-color: {COLORS["bg_card"]} !important;
        border-color: {COLORS["border"]} !important;
        border-radius: 8px !important;
    }}

    /* Checkbox */
    .stCheckbox label {{
        color: {COLORS["text_secondary"]} !important;
    }}

    /* Info/Warning/Error boxes */
    .stAlert {{
        background-color: {COLORS["bg_card"]} !important;
        border: 1px solid {COLORS["border"]} !important;
        border-radius: 10px !important;
        color: {COLORS["text_secondary"]} !important;
    }}

    /* Captions */
    .stCaption, [data-testid="stCaptionContainer"] {{
        color: {COLORS["text_muted"]} !important;
        font-size: 0.82rem !important;
    }}

    /* Dividers */
    hr {{
        border-color: {COLORS["border"]} !important;
        opacity: 0.5;
    }}

    /* Scrollbar */
    ::-webkit-scrollbar {{
        width: 6px;
        height: 6px;
    }}
    ::-webkit-scrollbar-track {{
        background: {COLORS["bg_primary"]};
    }}
    ::-webkit-scrollbar-thumb {{
        background: {COLORS["border_accent"]};
        border-radius: 3px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: {COLORS["text_muted"]};
    }}

    /* Custom card component class */
    .metric-card {{
        background: {COLORS["bg_card"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 0.5rem;
        transition: border-color 0.2s ease, transform 0.15s ease;
    }}
    .metric-card:hover {{
        border-color: {COLORS["border_accent"]};
    }}
    .metric-card .metric-label {{
        color: {COLORS["text_muted"]};
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 0.35rem;
    }}
    .metric-card .metric-value {{
        color: {COLORS["text_primary"]};
        font-size: 1.6rem;
        font-weight: 700;
        line-height: 1.2;
    }}
    .metric-card .metric-sub {{
        color: {COLORS["text_secondary"]};
        font-size: 0.82rem;
        margin-top: 0.25rem;
        font-weight: 500;
    }}

    /* Section header with accent line */
    .section-header {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.25rem;
    }}
    .section-header .accent-bar {{
        width: 3px;
        height: 24px;
        background: {COLORS["accent_cyan"]};
        border-radius: 2px;
    }}
    .section-header h2 {{
        margin: 0 !important;
        padding: 0 !important;
    }}

    /* Badge / tag style */
    .badge {{
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    .badge-cyan {{
        background: rgba(0, 212, 170, 0.12);
        color: {COLORS["accent_cyan"]};
        border: 1px solid rgba(0, 212, 170, 0.25);
    }}

    /* Logo / brand header */
    .brand-header {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 1.75rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid {COLORS["border"]};
    }}
    .brand-header .brand-icon {{
        font-size: 1.5rem;
    }}
    .brand-header .brand-text {{
        font-size: 1.05rem;
        font-weight: 700;
        color: {COLORS["text_primary"]};
        letter-spacing: -0.01em;
    }}
    .brand-header .brand-sub {{
        font-size: 0.7rem;
        color: {COLORS["text_muted"]};
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }}

    /* Filter section in sidebar */
    .sidebar-section {{
        background: {COLORS["bg_card"]};
        border: 1px solid {COLORS["border"]};
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
    }}
    .sidebar-section-title {{
        color: {COLORS["text_muted"]};
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 0.75rem;
    }}
</style>
"""


def metric_card(label, value, sub=None, accent_color=None):
    """Render a styled metric card using HTML."""
    accent = f'border-left: 3px solid {accent_color};' if accent_color else ''
    sub_html = f'<div class="metric-sub">{sub}</div>' if sub else ''
    return f"""
    <div class="metric-card" style="{accent}">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {sub_html}
    </div>
    """


def section_header(title, description=None):
    """Render a section header with accent bar."""
    desc = f'<p style="color: {COLORS["text_muted"]}; font-size: 0.82rem; margin-top: 0.25rem; margin-bottom: 1rem;">{description}</p>' if description else ''
    st.markdown(f"""
    <div class="section-header">
        <div class="accent-bar"></div>
        <h2 style="margin: 0 !important;">{title}</h2>
    </div>
    {desc}
    """, unsafe_allow_html=True)


# =============================================================================
# DATA LOADING
# =============================================================================

@st.cache_data(ttl=3600, show_spinner="Fetching league data...")
def get_data():
    sleeper = SleeperConfig()
    espn = ESPNConfig()
    return load_all_data(sleeper, espn)


@st.cache_data(ttl=3600, show_spinner="Fetching draft data...")
def get_draft_data():
    sleeper = SleeperConfig()
    espn = ESPNConfig()
    return load_draft_data(sleeper, espn)


# =============================================================================
# MAIN APP
# =============================================================================

def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # --- Title Area ---
    st.markdown(f"""
    <div style="margin-bottom: 1.5rem;">
        <h1 style="margin-bottom: 0.15rem !important; font-size: 2rem !important;">
            Fantasy Football Analytics
        </h1>
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span class="badge badge-cyan">LIVE DATA</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    weekly_df, slots_df, summaries_df = get_data()

    if weekly_df.empty:
        st.error("No data loaded. Check your .env configuration.")
        st.stop()

    managers = sorted(weekly_df["manager"].unique())
    seasons = sorted(weekly_df["season"].unique())

    # --- Sidebar ---
    with st.sidebar:
        st.markdown(f"""
        <div class="brand-header">
            <span class="brand-icon">🏈</span>
            <div>
                <div class="brand-text">FFB Analytics</div>
                <div class="brand-sub">Dashboard</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sidebar-section-title">Filters</div>', unsafe_allow_html=True)

        selected_seasons = st.multiselect(
            "Seasons", seasons, default=seasons
        )
        exclude_playoffs = st.checkbox("Exclude playoff weeks", value=True)

        st.markdown("---")
        st.markdown(f"""
        <div style="padding: 0.5rem 0;">
            <div style="color: {COLORS['text_muted']}; font-size: 0.7rem; font-weight: 600;
                        text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.5rem;">
                Quick Stats
            </div>
            <div style="color: {COLORS['text_secondary']}; font-size: 0.82rem; line-height: 1.8;">
                <span style="color: {COLORS['text_primary']}; font-weight: 600;">{len(managers)}</span> managers<br>
                <span style="color: {COLORS['text_primary']}; font-weight: 600;">{len(seasons)}</span> seasons<br>
                <span style="color: {COLORS['text_primary']}; font-weight: 600;">{len(weekly_df):,}</span> matchups
            </div>
        </div>
        """, unsafe_allow_html=True)

    # --- Filter data ---
    w = weekly_df[weekly_df["season"].isin(selected_seasons)].copy()
    s = slots_df[slots_df["season"].isin(selected_seasons)].copy() if not slots_df.empty else slots_df

    if exclude_playoffs and "is_playoff" in w.columns:
        w = w[~w["is_playoff"]]
        if not s.empty and "is_playoff" in s.columns:
            s = s[~s["is_playoff"]]

    filtered_managers = sorted(w["manager"].unique())

    # --- Tabs ---
    tabs = st.tabs([
        "Leaderboard", "Championships", "Cumulative Points", "Boom / Bust",
        "Positional Breakdown", "Lucky / Unlucky", "Head to Head",
        "Season Trends", "Advanced Metrics", "Draft Analysis",
    ])

    # ================================================================
    # TAB 0: Leaderboard
    # ================================================================
    with tabs[0]:
        section_header("All-Time Leaderboard", "Career stats across all selected seasons")

        stats = analytics.manager_weekly_stats(w)
        if not stats.empty:
            # Superlatives row
            cols = st.columns(4, gap="medium")
            with cols[0]:
                top = stats.iloc[0]
                st.markdown(metric_card(
                    "Highest Average", top["manager"],
                    f"{top['avg_pts']} ppg",
                    COLORS["accent_cyan"]
                ), unsafe_allow_html=True)
            with cols[1]:
                low_cv = stats.sort_values("cv").iloc[0]
                st.markdown(metric_card(
                    "Mr. Consistent", low_cv["manager"],
                    f"CV: {low_cv['cv']}%",
                    COLORS["accent_blue"]
                ), unsafe_allow_html=True)
            with cols[2]:
                high_cv = stats.sort_values("cv", ascending=False).iloc[0]
                st.markdown(metric_card(
                    "Boom or Bust", high_cv["manager"],
                    f"CV: {high_cv['cv']}%",
                    COLORS["accent_orange"]
                ), unsafe_allow_html=True)
            with cols[3]:
                best_wp = stats.sort_values("win_pct", ascending=False).iloc[0]
                st.markdown(metric_card(
                    "Best Record", best_wp["manager"],
                    f"{best_wp['win_pct']}%",
                    COLORS["accent_green"]
                ), unsafe_allow_html=True)

            st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

            # Leaderboard table
            display = stats.copy()
            display = display.rename(columns={
                "manager": "Manager", "games": "GP", "wins": "W", "losses": "L",
                "win_pct": "Win%", "avg_pts": "Avg", "median_pts": "Med",
                "std_pts": "StdDev", "min_pts": "Min", "max_pts": "Max",
                "cv": "CV%", "avg_pts_against": "Avg PA",
                "lucky_wins": "Lucky W", "unlucky_losses": "Unlucky L",
            })
            st.dataframe(
                display[["Manager", "GP", "W", "L", "Win%", "Avg", "Med",
                          "StdDev", "CV%", "Min", "Max", "Avg PA",
                          "Lucky W", "Unlucky L"]],
                hide_index=True,
                use_container_width=True,
            )

    # ================================================================
    # TAB 1: Championships & Sackos
    # ================================================================
    with tabs[1]:
        section_header("Championships & Sackos", "Final playoff standings across all seasons")

        champ_data = analytics.championships_and_sackos(summaries_df)
        if not champ_data.empty:
            # Filter to selected seasons
            filtered_summaries = summaries_df[summaries_df["season"].isin(selected_seasons)]
            champ_data = analytics.championships_and_sackos(filtered_summaries)

            # Trophy / toilet metrics
            cols = st.columns(4)
            with cols[0]:
                if not champ_data.empty and champ_data["championships"].max() > 0:
                    most_champs = champ_data.sort_values("championships", ascending=False).iloc[0]
                    st.metric("Most Championships", most_champs["manager"],
                              f"{int(most_champs['championships'])} titles")
            with cols[1]:
                if not champ_data.empty and champ_data["sackos"].max() > 0:
                    most_sackos = champ_data.sort_values("sackos", ascending=False).iloc[0]
                    st.metric("Most Sackos", most_sackos["manager"],
                              f"{int(most_sackos['sackos'])} last-place finishes")
            with cols[2]:
                if not champ_data.empty:
                    best_avg = champ_data.sort_values("avg_finish").iloc[0]
                    st.metric("Best Avg Finish", best_avg["manager"],
                              f"#{best_avg['avg_finish']}")
            with cols[3]:
                if not champ_data.empty:
                    worst_avg = champ_data.sort_values("avg_finish", ascending=False).iloc[0]
                    st.metric("Worst Avg Finish", worst_avg["manager"],
                              f"#{worst_avg['avg_finish']}")

            st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

            display = champ_data.rename(columns={
                "manager": "Manager", "championships": "Champs",
                "sackos": "Sackos", "seasons_played": "Seasons",
                "best_finish": "Best", "worst_finish": "Worst",
                "avg_finish": "Avg Finish",
            })
            st.dataframe(
                display[["Manager", "Champs", "Sackos", "Seasons",
                          "Best", "Worst", "Avg Finish"]],
                hide_index=True, use_container_width=True,
            )

            # Finish distribution chart
            st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
            section_header("Finish Distribution", "Where each manager ends up in the standings")
            finish_data = filtered_summaries[["manager", "season", "finish"]].copy()
            fig = px.histogram(
                finish_data, x="finish", color="manager",
                barmode="group", nbins=10,
                labels={"finish": "Final Standing", "manager": "Manager", "count": "Times"},
                color_discrete_sequence=CHART_COLORS,
            )
            apply_chart_style(fig, height=420)
            st.plotly_chart(fig, use_container_width=True)

    # ================================================================
    # TAB 2: Cumulative Points
    # ================================================================
    with tabs[2]:
        section_header(
            "Cumulative Points Race",
            "Running total of points scored across all seasons."
        )

        cum = analytics.cumulative_points(w)
        if not cum.empty:
            fig = px.line(
                cum, x="week_label", y="cumulative_points", color="manager",
                labels={"week_label": "Week", "cumulative_points": "Cumulative Points",
                        "manager": "Manager"},
                hover_data={"points": ":.1f"},
                color_discrete_sequence=CHART_COLORS,
            )
            apply_chart_style(fig, height=580)
            fig.update_traces(line=dict(width=2.5))
            fig.update_layout(xaxis=dict(tickmode="auto", nticks=30))

            # Season boundary lines
            season_starts = cum.groupby("season")["week_label"].first().tolist()
            for label in season_starts[1:]:
                fig.add_vline(
                    x=label, line_dash="dot",
                    line_color=COLORS["border_accent"], opacity=0.4
                )

            st.plotly_chart(fig, use_container_width=True)

            # Rankings table
            st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
            final = cum.groupby("manager")["cumulative_points"].last().reset_index()
            final = final.sort_values("cumulative_points", ascending=False).reset_index(drop=True)
            final.columns = ["Manager", "Total Points"]
            final["Total Points"] = final["Total Points"].round(1)
            final.index = final.index + 1
            final.index.name = "Rank"
            st.dataframe(final, use_container_width=True)

    # ================================================================
    # TAB 3: Boom / Bust
    # ================================================================
    with tabs[3]:
        section_header(
            "Boom / Bust Analysis",
            "High average + low std dev = consistent beast. High std dev = unpredictable."
        )

        bb = analytics.boom_bust_data(w)
        if not bb.empty:
            fig = px.scatter(
                bb, x="avg_pts", y="std_pts", text="manager",
                color="win_pct",
                color_continuous_scale=[
                    [0, COLORS["accent_red"]],
                    [0.5, COLORS["accent_orange"]],
                    [1, COLORS["accent_green"]],
                ],
                size_max=15,
                labels={"avg_pts": "Avg Points/Week", "std_pts": "Std Dev",
                        "win_pct": "Win %"},
            )
            fig.update_traces(
                textposition="top center",
                marker=dict(size=14, line=dict(width=1, color=COLORS["border_accent"])),
                textfont=dict(color=COLORS["text_secondary"], size=11),
            )
            apply_chart_style(fig, height=520)
            fig.update_layout(
                coloraxis_colorbar=dict(
                    title=dict(text="Win %", font=dict(color=COLORS["text_muted"])),
                    tickfont=dict(color=COLORS["text_muted"]),
                    bgcolor="rgba(0,0,0,0)",
                    bordercolor=COLORS["border"],
                )
            )

            fig.add_hline(
                y=bb["std_pts"].median(), line_dash="dash",
                line_color=COLORS["text_muted"], opacity=0.35
            )
            fig.add_vline(
                x=bb["avg_pts"].median(), line_dash="dash",
                line_color=COLORS["text_muted"], opacity=0.35
            )

            st.plotly_chart(fig, use_container_width=True)

            # Score distributions
            st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
            section_header("Score Distributions")

            fig2 = px.box(
                w, x="manager", y="points",
                labels={"manager": "Manager", "points": "Points"},
                color="manager",
                color_discrete_sequence=CHART_COLORS,
            )
            fig2.update_traces(
                marker=dict(outliercolor=COLORS["accent_orange"], size=4),
                line=dict(color=COLORS["text_muted"]),
            )
            apply_chart_style(fig2, height=420)
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

    # ================================================================
    # TAB 4: Positional Breakdown
    # ================================================================
    with tabs[4]:
        section_header(
            "Positional Strength / Weakness",
            "Performance vs league average at each position (2019+ for ESPN, all years for Sleeper)"
        )

        heatmap = analytics.positional_heatmap_data(s)
        if not heatmap.empty:
            fig = go.Figure(data=go.Heatmap(
                z=heatmap.values,
                x=heatmap.columns.tolist(),
                y=heatmap.index.tolist(),
                colorscale=[
                    [0, COLORS["accent_red"]],
                    [0.5, COLORS["bg_card"]],
                    [1, COLORS["accent_green"]],
                ],
                zmid=0,
                text=heatmap.values.round(1),
                texttemplate="%{text}",
                textfont=dict(size=12, color=COLORS["text_primary"]),
                hovertemplate="Manager: %{y}<br>Position: %{x}<br>vs Avg: %{z:.1f}<extra></extra>",
                colorbar=dict(
                    title=dict(text="vs Avg", font=dict(color=COLORS["text_muted"])),
                    tickfont=dict(color=COLORS["text_muted"]),
                    bgcolor="rgba(0,0,0,0)",
                    bordercolor=COLORS["border"],
                ),
            ))
            apply_chart_style(fig, height=max(400, len(heatmap) * 40))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
            section_header("Raw Positional Averages")

            pos_avg = analytics.positional_averages(s)
            if not pos_avg.empty:
                pivot = pos_avg.pivot(index="manager", columns="slot", values="points")
                col_order = [c for c in ["QB", "RB1", "RB2", "WR1", "WR2", "FLEX", "FLEX2", "TE", "K", "DST"]
                             if c in pivot.columns]
                st.dataframe(pivot[col_order], use_container_width=True)
        else:
            st.info("No positional data available for selected seasons.")

    # ================================================================
    # TAB 5: Lucky / Unlucky
    # ================================================================
    with tabs[5]:
        section_header(
            "Luck Factor",
            "Expected wins (based on weekly scoring rank) vs actual wins. Positive = lucky schedule."
        )

        luck = analytics.lucky_unlucky(w)
        if not luck.empty:
            # Color bars based on positive/negative
            colors = [COLORS["accent_green"] if v >= 0 else COLORS["accent_red"]
                      for v in luck["luck_factor"]]

            fig = go.Figure(data=go.Bar(
                x=luck["manager"],
                y=luck["luck_factor"],
                marker=dict(
                    color=colors,
                    line=dict(width=0),
                    cornerradius=4,
                ),
                hovertemplate="<b>%{x}</b><br>Luck Factor: %{y:.1f}%<extra></extra>",
            ))
            apply_chart_style(fig, height=420)
            fig.update_layout(
                xaxis_title="Manager",
                yaxis_title="Luck Factor (Win% diff)",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)

            display = luck[["manager", "actual_wins", "expected_wins", "games",
                            "actual_win_pct", "expected_win_pct", "luck_factor"]].rename(columns={
                "manager": "Manager", "actual_wins": "Actual W",
                "expected_wins": "Expected W", "games": "GP",
                "actual_win_pct": "Actual Win%", "expected_win_pct": "Expected Win%",
                "luck_factor": "Luck",
            })
            st.dataframe(display, hide_index=True, use_container_width=True)

    # ================================================================
    # TAB 6: Head to Head
    # ================================================================
    with tabs[6]:
        section_header("Head to Head Comparison")

        col1, col2 = st.columns(2, gap="medium")
        with col1:
            mgr_a = st.selectbox("Manager A", filtered_managers, index=0)
        with col2:
            mgr_b = st.selectbox("Manager B", filtered_managers,
                                  index=min(1, len(filtered_managers) - 1))

        if mgr_a != mgr_b:
            h2h = analytics.head_to_head(w, mgr_a, mgr_b)
            if h2h and h2h["weeks_compared"] > 0:
                st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)

                cols = st.columns(5, gap="medium")
                with cols[0]:
                    st.markdown(metric_card(
                        "Weeks Compared", h2h["weeks_compared"],
                        accent_color=COLORS["accent_purple"]
                    ), unsafe_allow_html=True)
                with cols[1]:
                    st.markdown(metric_card(
                        f"{mgr_a} Avg", h2h["a_avg"],
                        accent_color=COLORS["accent_cyan"]
                    ), unsafe_allow_html=True)
                with cols[2]:
                    st.markdown(metric_card(
                        f"{mgr_b} Avg", h2h["b_avg"],
                        accent_color=COLORS["accent_blue"]
                    ), unsafe_allow_html=True)
                with cols[3]:
                    st.markdown(metric_card(
                        f"{mgr_a} Higher", f"{h2h['a_higher']}x",
                        accent_color=COLORS["accent_green"]
                    ), unsafe_allow_html=True)
                with cols[4]:
                    st.markdown(metric_card(
                        f"{mgr_b} Higher", f"{h2h['b_higher']}x",
                        accent_color=COLORS["accent_orange"]
                    ), unsafe_allow_html=True)

                st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

                a_data = w[w["manager"] == mgr_a][["season", "week", "points"]].copy()
                b_data = w[w["manager"] == mgr_b][["season", "week", "points"]].copy()
                a_data["manager"] = mgr_a
                b_data["manager"] = mgr_b
                combined = pd.concat([a_data, b_data])
                combined["week_label"] = combined["season"].astype(str) + " W" + combined["week"].astype(str)

                fig = px.line(
                    combined, x="week_label", y="points", color="manager",
                    labels={"week_label": "Week", "points": "Points"},
                    color_discrete_sequence=[COLORS["accent_cyan"], COLORS["accent_blue"]],
                )
                fig.update_traces(line=dict(width=2))
                apply_chart_style(fig, height=420)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Select two different managers to compare.")

    # ================================================================
    # TAB 7: Season Trends
    # ================================================================
    with tabs[7]:
        section_header("Season-over-Season Trends")

        season_stats = analytics.manager_season_stats(w)
        if not season_stats.empty:
            # Avg points trend
            section_header("Average Points per Week")
            fig = px.line(
                season_stats, x="season", y="avg_pts", color="manager",
                markers=True,
                labels={"season": "Season", "avg_pts": "Avg Pts/Week", "manager": "Manager"},
                color_discrete_sequence=CHART_COLORS,
            )
            fig.update_traces(line=dict(width=2.5), marker=dict(size=8))
            apply_chart_style(fig, height=420)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

            # Win % by season
            section_header("Win Rate by Season")
            fig2 = px.bar(
                season_stats, x="season", y="win_pct", color="manager",
                barmode="group",
                labels={"season": "Season", "win_pct": "Win %", "manager": "Manager"},
                color_discrete_sequence=CHART_COLORS,
            )
            fig2.update_traces(marker_line_width=0)
            apply_chart_style(fig2, height=420)
            st.plotly_chart(fig2, use_container_width=True)

            st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

            # Consistency trend
            section_header("Consistency by Season", "Lower CV = more consistent performance")
            fig3 = px.line(
                season_stats, x="season", y="cv", color="manager",
                markers=True,
                labels={"season": "Season", "cv": "CV% (Boom/Bust)", "manager": "Manager"},
                color_discrete_sequence=CHART_COLORS,
            )
            fig3.update_traces(line=dict(width=2.5), marker=dict(size=8))
            apply_chart_style(fig3, height=420)
            st.plotly_chart(fig3, use_container_width=True)


    # ================================================================
    # TAB 8: Advanced Metrics
    # ================================================================
    with tabs[8]:
        section_header("Advanced Metrics", "Deep-dive analytics beyond basic stats")

        adv_subtabs = st.tabs([
            "Schedule-Adjusted", "Dominance", "Close Games",
            "Elo Ratings", "Surge / Fade", "Rolling Power",
        ])

        # --- Schedule-Adjusted Win Rate ---
        with adv_subtabs[0]:
            section_header(
                "Schedule-Adjusted Win Rate",
                "Each week, simulate every manager vs every other manager. Removes schedule luck entirely."
            )
            saw = analytics.schedule_adjusted_win_rate(w)
            if not saw.empty:
                cols = st.columns(3, gap="medium")
                with cols[0]:
                    top = saw.iloc[0]
                    st.markdown(metric_card(
                        "True Best", top["manager"],
                        f"{top['simulated_win_pct']}% sim win rate",
                        COLORS["accent_cyan"]
                    ), unsafe_allow_html=True)
                with cols[1]:
                    luckiest = saw.sort_values("schedule_effect", ascending=False).iloc[0]
                    st.markdown(metric_card(
                        "Luckiest Schedule", luckiest["manager"],
                        f"+{luckiest['schedule_effect']}% above true rate",
                        COLORS["accent_green"]
                    ), unsafe_allow_html=True)
                with cols[2]:
                    unluckiest = saw.sort_values("schedule_effect").iloc[0]
                    st.markdown(metric_card(
                        "Unluckiest Schedule", unluckiest["manager"],
                        f"{unluckiest['schedule_effect']}% below true rate",
                        COLORS["accent_red"]
                    ), unsafe_allow_html=True)

                st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=saw["manager"], y=saw["simulated_win_pct"],
                    name="Simulated Win%", marker_color=COLORS["accent_cyan"],
                    marker_cornerradius=4,
                ))
                fig.add_trace(go.Bar(
                    x=saw["manager"], y=saw["actual_win_pct"],
                    name="Actual Win%", marker_color=COLORS["accent_blue"],
                    marker_cornerradius=4,
                ))
                fig.update_layout(barmode="group")
                apply_chart_style(fig, height=420)
                st.plotly_chart(fig, use_container_width=True)

                display = saw[["manager", "simulated_win_pct", "actual_win_pct", "schedule_effect"]].rename(columns={
                    "manager": "Manager", "simulated_win_pct": "Sim Win%",
                    "actual_win_pct": "Actual Win%", "schedule_effect": "Schedule Effect",
                })
                st.dataframe(display, hide_index=True, use_container_width=True)

        # --- Dominance Score ---
        with adv_subtabs[1]:
            section_header(
                "Dominance Score",
                "Margin of victory vs margin of defeat. High dominance = wins big, loses small."
            )
            dom = analytics.dominance_score(w)
            if not dom.empty:
                colors_dom = [COLORS["accent_green"] if v >= 0 else COLORS["accent_red"]
                              for v in dom["dominance"]]
                fig = go.Figure(data=go.Bar(
                    x=dom["manager"], y=dom["dominance"],
                    marker=dict(color=colors_dom, cornerradius=4),
                    hovertemplate="<b>%{x}</b><br>Dominance: %{y:.1f}<extra></extra>",
                ))
                apply_chart_style(fig, height=420)
                fig.update_layout(yaxis_title="Dominance Score")
                st.plotly_chart(fig, use_container_width=True)

                display = dom[["manager", "dominance", "avg_mov", "avg_mod",
                               "blowout_wins", "close_wins", "close_losses", "blowout_losses"]].rename(columns={
                    "manager": "Manager", "dominance": "Dominance", "avg_mov": "Avg MOV",
                    "avg_mod": "Avg MOD", "blowout_wins": "Blowout W", "close_wins": "Close W",
                    "close_losses": "Close L", "blowout_losses": "Blowout L",
                })
                st.dataframe(display, hide_index=True, use_container_width=True)

        # --- Close Games ---
        with adv_subtabs[2]:
            section_header(
                "Close Game Record",
                "Win rate in games decided by fewer than 10 points. Clutch factor."
            )
            cgr = analytics.close_game_record(w)
            if not cgr.empty:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=cgr["manager"], y=cgr["close_wins"],
                    name="Close Wins", marker_color=COLORS["accent_green"],
                    marker_cornerradius=4,
                ))
                fig.add_trace(go.Bar(
                    x=cgr["manager"], y=cgr["close_losses"],
                    name="Close Losses", marker_color=COLORS["accent_red"],
                    marker_cornerradius=4,
                ))
                fig.update_layout(barmode="stack")
                apply_chart_style(fig, height=420)
                fig.update_layout(yaxis_title="Close Games (<10 pts)")
                st.plotly_chart(fig, use_container_width=True)

                display = cgr[["manager", "close_games", "close_wins", "close_losses",
                               "close_win_pct", "close_game_pct"]].rename(columns={
                    "manager": "Manager", "close_games": "Close GP", "close_wins": "Close W",
                    "close_losses": "Close L", "close_win_pct": "Close Win%",
                    "close_game_pct": "% Games Close",
                })
                st.dataframe(display, hide_index=True, use_container_width=True)

        # --- Elo Ratings ---
        with adv_subtabs[3]:
            section_header(
                "Elo Ratings",
                "Chess-style rating system. Beat strong opponents = big gains. Lose to weak ones = big drops."
            )
            elo_final, elo_hist = analytics.elo_ratings(w)
            if not elo_final.empty:
                cols = st.columns(3, gap="medium")
                with cols[0]:
                    top_elo = elo_final.iloc[0]
                    st.markdown(metric_card(
                        "Current #1", top_elo["manager"],
                        f"Elo: {top_elo['elo']:.0f}",
                        COLORS["accent_cyan"]
                    ), unsafe_allow_html=True)
                with cols[1]:
                    peak_row = elo_final.sort_values("peak_elo", ascending=False).iloc[0]
                    st.markdown(metric_card(
                        "Highest Peak", peak_row["manager"],
                        f"Peak: {peak_row['peak_elo']:.0f}",
                        COLORS["accent_green"]
                    ), unsafe_allow_html=True)
                with cols[2]:
                    low_row = elo_final.sort_values("low_elo").iloc[0]
                    st.markdown(metric_card(
                        "Lowest Valley", low_row["manager"],
                        f"Low: {low_row['low_elo']:.0f}",
                        COLORS["accent_red"]
                    ), unsafe_allow_html=True)

                st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

                if not elo_hist.empty:
                    fig = px.line(
                        elo_hist, x="week_label", y="elo", color="manager",
                        labels={"week_label": "Week", "elo": "Elo Rating", "manager": "Manager"},
                        color_discrete_sequence=CHART_COLORS,
                    )
                    fig.update_traces(line=dict(width=2))
                    apply_chart_style(fig, height=520)
                    fig.update_layout(xaxis=dict(tickmode="auto", nticks=30))

                    # Season boundaries
                    season_starts = elo_hist.groupby("season")["week_label"].first().tolist()
                    for label in season_starts[1:]:
                        fig.add_vline(x=label, line_dash="dot",
                                      line_color=COLORS["border_accent"], opacity=0.4)

                    fig.add_hline(y=1500, line_dash="dash",
                                  line_color=COLORS["text_muted"], opacity=0.3,
                                  annotation_text="Starting Elo")

                    st.plotly_chart(fig, use_container_width=True)

                display = elo_final.rename(columns={
                    "manager": "Manager", "elo": "Current Elo",
                    "peak_elo": "Peak", "low_elo": "Low",
                })
                st.dataframe(display, hide_index=True, use_container_width=True)

        # --- Surge / Fade ---
        with adv_subtabs[4]:
            section_header(
                "Second-Half Surge / Fade",
                "Who gets better as the season goes on, and who falls off?"
            )
            surge = analytics.second_half_surge(w)
            if not surge.empty:
                colors_s = [COLORS["accent_green"] if v >= 0 else COLORS["accent_red"]
                            for v in surge["avg_surge"]]
                fig = go.Figure(data=go.Bar(
                    x=surge["manager"], y=surge["avg_surge"],
                    marker=dict(color=colors_s, cornerradius=4),
                    hovertemplate="<b>%{x}</b><br>Avg Surge: %{y:.1f} pts<extra></extra>",
                ))
                apply_chart_style(fig, height=420)
                fig.update_layout(yaxis_title="Avg 2nd Half - 1st Half (pts/week)")
                st.plotly_chart(fig, use_container_width=True)

                display = surge.rename(columns={
                    "manager": "Manager", "avg_first_half": "1st Half Avg",
                    "avg_second_half": "2nd Half Avg", "avg_surge": "Avg Surge",
                    "surge_seasons": "Surge Seasons", "fade_seasons": "Fade Seasons",
                })
                st.dataframe(display, hide_index=True, use_container_width=True)

        # --- Rolling Power Rating ---
        with adv_subtabs[5]:
            section_header(
                "Rolling Power Rating",
                "6-week rolling average of points scored. Shows momentum and hot/cold streaks."
            )
            rolling = analytics.rolling_power_rating(w)
            if not rolling.empty:
                fig = px.line(
                    rolling, x="week_label", y="rolling_avg", color="manager",
                    labels={"week_label": "Week", "rolling_avg": "6-Week Rolling Avg",
                            "manager": "Manager"},
                    color_discrete_sequence=CHART_COLORS,
                )
                fig.update_traces(line=dict(width=2))
                apply_chart_style(fig, height=520)
                fig.update_layout(xaxis=dict(tickmode="auto", nticks=30))

                season_starts = rolling.groupby("season")["week_label"].first().tolist()
                for label in season_starts[1:]:
                    fig.add_vline(x=label, line_dash="dot",
                                  line_color=COLORS["border_accent"], opacity=0.4)

                st.plotly_chart(fig, use_container_width=True)

    # ================================================================
    # TAB 9: Draft Analysis
    # ================================================================
    with tabs[9]:
        section_header("Draft Analysis", "16 years of draft strategy and tendencies")

        drafts_df = get_draft_data()
        if drafts_df.empty:
            st.info("No draft data available.")
        else:
            draft_subtabs = st.tabs([
                "Overview", "Position Tendencies", "Draft Capital", "Round Strategy",
            ])

            # --- Draft Overview ---
            with draft_subtabs[0]:
                section_header("Draft Overview", "Aggregate draft stats per manager")
                overview = analytics.draft_overview(drafts_df, w)
                if not overview.empty:
                    # Show position columns if they exist
                    pos_cols = [c for c in ["QB", "RB", "WR", "TE", "K", "DST"] if c in overview.columns]
                    display_cols = ["manager", "total_picks", "seasons_drafted", "avg_round"] + pos_cols
                    display = overview[display_cols].rename(columns={
                        "manager": "Manager", "total_picks": "Total Picks",
                        "seasons_drafted": "Seasons", "avg_round": "Avg Round",
                    })
                    st.dataframe(display, hide_index=True, use_container_width=True)

            # --- Position Tendencies ---
            with draft_subtabs[1]:
                section_header(
                    "Draft Position Tendencies",
                    "What positions each manager prioritizes in the draft"
                )
                tendencies = analytics.draft_position_tendencies(drafts_df)
                if not tendencies.empty:
                    main_pos = ["QB", "RB", "WR", "TE"]
                    t_filtered = tendencies[tendencies["position"].isin(main_pos)]
                    if not t_filtered.empty:
                        fig = px.bar(
                            t_filtered, x="manager", y="pct_of_picks", color="position",
                            barmode="group",
                            labels={"manager": "Manager", "pct_of_picks": "% of Picks",
                                    "position": "Position"},
                            color_discrete_map={
                                "QB": COLORS["accent_cyan"], "RB": COLORS["accent_green"],
                                "WR": COLORS["accent_blue"], "TE": COLORS["accent_orange"],
                            },
                        )
                        apply_chart_style(fig, height=420)
                        st.plotly_chart(fig, use_container_width=True)

            # --- Draft Capital ---
            with draft_subtabs[2]:
                section_header(
                    "Draft Capital by Position",
                    "Average pick number spent on each position. Lower = more draft capital invested."
                )
                capital = analytics.draft_capital_by_position(drafts_df)
                if not capital.empty:
                    fig = go.Figure(data=go.Heatmap(
                        z=capital.values,
                        x=capital.columns.tolist(),
                        y=capital.index.tolist(),
                        colorscale=[
                            [0, COLORS["accent_green"]],
                            [0.5, COLORS["bg_card"]],
                            [1, COLORS["accent_red"]],
                        ],
                        text=capital.values.round(0).astype(int),
                        texttemplate="%{text}",
                        textfont=dict(size=12, color=COLORS["text_primary"]),
                        hovertemplate="Manager: %{y}<br>Position: %{x}<br>Avg Pick: %{z:.0f}<extra></extra>",
                        colorbar=dict(
                            title=dict(text="Avg Pick", font=dict(color=COLORS["text_muted"])),
                            tickfont=dict(color=COLORS["text_muted"]),
                        ),
                        reversescale=True,
                    ))
                    apply_chart_style(fig, height=max(400, len(capital) * 40))
                    st.plotly_chart(fig, use_container_width=True)

                    st.caption("Green = higher draft capital (earlier picks), Red = lower draft capital (later picks)")

            # --- Round Strategy ---
            with draft_subtabs[3]:
                section_header(
                    "Round-by-Round Strategy",
                    "Most-drafted position in each round across all seasons"
                )
                round_strat = analytics.draft_round_analysis(drafts_df)
                if not round_strat.empty:
                    st.dataframe(round_strat, use_container_width=True)


if __name__ == "__main__":
    main()
