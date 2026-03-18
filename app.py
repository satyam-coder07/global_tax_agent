from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dtaa import INCOME_TYPES, check_treaty, get_all_pairs, summarize_treaty_exposure
from engine import (
    OptimizationReport,
    RegimeResult,
    ScenarioComparison,
    TaxProfile,
    calculate_tax,
    optimize,
    simulate_scenarios,
    whatif_series,
)
from llm_bridge import PROVIDER_MODELS, LLMBridge, LLMConnectionError
from parser import parse_document
from research import get_latest_notifications, scout_gov_source

st.set_page_config(
    page_title="Global Tax Hub",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

DARK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #070710;
    color: #E2E8F0;
}

.stApp {
    background-color: #070710;
}

.block-container {
    padding: 2rem 2.5rem 2rem 2.5rem;
    max-width: 1400px;
}

h1, h2, h3, h4, h5, h6 {
    color: #F1F5F9;
    font-weight: 600;
    letter-spacing: -0.02em;
}

.stButton > button {
    background: linear-gradient(135deg, #0EA5E9 0%, #6366F1 100%);
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.875rem;
    padding: 0.5rem 1.25rem;
    transition: opacity 0.2s ease;
}
.stButton > button:hover {
    opacity: 0.85;
}

.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div,
.stMultiselect > div > div {
    background-color: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 8px;
    color: #E2E8F0;
}

.stSlider > div > div > div > div {
    background: linear-gradient(135deg, #0EA5E9, #6366F1);
}

.stTabs [data-baseweb="tab-list"] {
    background-color: #0F172A;
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    background-color: transparent;
    color: #94A3B8;
    border-radius: 8px;
    font-weight: 500;
    font-size: 0.875rem;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #0EA5E9 0%, #6366F1 100%);
    color: #FFFFFF;
}

.stSidebar {
    background-color: #0B0B1A;
    border-right: 1px solid #1E293B;
}
.stSidebar [data-testid="stSidebarContent"] {
    background-color: #0B0B1A;
}

div[data-testid="metric-container"] {
    background: rgba(15, 23, 42, 0.4);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    border-radius: 12px;
    padding: 1rem;
}
div[data-testid="metric-container"] label {
    color: #64748B;
    font-size: 0.8rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
    color: #38BDF8;
    font-size: 1.5rem;
    font-weight: 700;
}

.card {
    background-color: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
}

.tag-act {
    display: inline-block;
    background-color: #064E3B;
    color: #6EE7B7;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.05em;
}
.tag-bill {
    display: inline-block;
    background-color: #451A03;
    color: #FCD34D;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.05em;
}
.source-link {
    font-size: 0.75rem;
    color: #38BDF8;
    text-decoration: none;
}
.section-divider {
    border: none;
    border-top: 1px solid #1E293B;
    margin: 1.5rem 0;
}
.gap-indicator {
    background: linear-gradient(135deg, #450A0A 0%, #1E0508 100%);
    border: 1px solid #7F1D1D;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
}
.optimization-row {
    background-color: #0A1628;
    border: 1px solid #1E3A5F;
    border-radius: 8px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.5rem;
}
</style>
"""
st.markdown(DARK_CSS, unsafe_allow_html=True)

COUNTRY_CURRENCY = {"india": "INR", "us": "USD", "uk": "GBP"}
COUNTRY_SYMBOL = {"india": "\u20b9", "us": "$", "uk": "\u00a3"}
COUNTRY_LABELS = {"india": "India", "us": "United States", "uk": "United Kingdom"}

PLOTLY_THEME = dict(
    paper_bgcolor="#070710",
    plot_bgcolor="#0F172A",
    font=dict(family="Inter", color="#94A3B8", size=12),
    xaxis=dict(gridcolor="#1E293B", linecolor="#1E293B", zerolinecolor="#1E293B"),
    yaxis=dict(gridcolor="#1E293B", linecolor="#1E293B", zerolinecolor="#1E293B"),
    margin=dict(l=40, r=40, t=50, b=40),
)


def _fmt(value: float, country: str) -> str:
    sym = COUNTRY_SYMBOL.get(country, "")
    return f"{sym}{value:,.0f}"


def _get_bridge() -> Optional[LLMBridge]:
    provider = st.session_state.get("llm_provider")
    api_key = st.session_state.get("llm_api_key", "")
    model = st.session_state.get("llm_model")
    if not provider or not api_key.strip():
        return None
    return LLMBridge(provider=provider, api_key=api_key, model=model)


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown("## Global Tax Hub")
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        st.markdown("#### Model Connection")
        provider = st.selectbox(
            "LLM Provider",
            options=["openai", "anthropic", "google", "groq"],
            format_func=lambda x: {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google Gemini", "groq": "Groq"}.get(x, x),
            key="llm_provider",
        )
        models_for_provider = PROVIDER_MODELS.get(provider, [])
        st.selectbox("Model", options=models_for_provider, key="llm_model")
        st.text_input("API Key", type="password", placeholder="Paste your key here", key="llm_api_key")

        col_ping, col_status = st.columns([1, 1])
        with col_ping:
            if st.button("Test Connection", use_container_width=True):
                bridge = _get_bridge()
                if bridge:
                    with st.spinner("Pinging..."):
                        ok = bridge.ping()
                    st.session_state["llm_connected"] = ok
                else:
                    st.session_state["llm_connected"] = False

        connected = st.session_state.get("llm_connected")
        if connected is True:
            col_status.success("Connected")
        elif connected is False:
            col_status.error("Failed")

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        st.markdown("#### Jurisdiction")
        country = st.selectbox(
            "Tax Jurisdiction",
            options=["india", "us", "uk"],
            format_func=lambda x: COUNTRY_LABELS.get(x, x),
            key="selected_country",
        )

        exa_key = st.text_input("Exa API Key (optional)", type="password", placeholder="For live gov news", key="exa_api_key")

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("#### Latest Tax Notifications")

        with st.spinner("Fetching..."):
            notifications = get_latest_notifications(country, exa_key or None)

        for notif in notifications:
            tag = '<span class="tag-act">PASSED ACT</span>' if notif["status"] == "PASSED_ACT" else '<span class="tag-bill">PROPOSED BILL</span>'
            date_str = notif.get("date", "")
            title = notif.get("title", "")
            url = notif.get("url", "#")
            summary = notif.get("summary", "")
            st.markdown(
                f'<div class="card" style="margin-bottom:0.75rem;padding:0.9rem 1rem;">'
                f'{tag}&nbsp;&nbsp;<span style="font-size:0.7rem;color:#64748B;">{date_str}</span>'
                f'<p style="margin:0.4rem 0 0.3rem;font-size:0.82rem;font-weight:500;color:#E2E8F0;">{title}</p>'
                f'<p style="margin:0;font-size:0.75rem;color:#64748B;">{summary[:120]}...</p>'
                f'<a href="{url}" target="_blank" class="source-link">View Source</a>'
                f'</div>',
                unsafe_allow_html=True,
            )

    return country


def render_tax_calculator(country: str) -> Optional[TaxProfile]:
    st.markdown("### Income Profile")

    c1, c2, c3 = st.columns(3)

    with c1:
        gross_income_raw = st.number_input(
            f"Gross Annual Income ({COUNTRY_SYMBOL[country]})",
            min_value=-1000000.0,
            max_value=100_000_000.0,
            value=1_000_000.0 if country == "india" else (80_000.0 if country == "us" else 50_000.0),
            step=10_000.0 if country == "india" else 1_000.0,
            format="%.0f",
            key="gross_income",
        )
        age_raw = st.number_input("Age", min_value=0, max_value=99, value=30, key="age")

    if gross_income_raw < 0:
        st.warning("Income cannot be negative. Adjusted to 0 for calculations.")
        gross_income = 0.0
    else:
        gross_income = gross_income_raw
        
    if age_raw < 18:
        st.warning("Age under 18. Certain age-related reliefs may not apply.")

    age = age_raw

    with c2:
        if country == "india":
            regime = st.selectbox("Tax Regime", ["new", "old"], format_func=lambda x: x.capitalize() + " Regime", key="regime")
            filing_status = "individual"
            has_hra = st.checkbox("Claim HRA", key="has_hra")
        elif country == "us":
            regime = "federal"
            filing_status = st.selectbox(
                "Filing Status",
                ["single", "married_filing_jointly", "married_filing_separately", "head_of_household"],
                format_func=lambda x: x.replace("_", " ").title(),
                key="filing_status_us",
            )
            has_hra = False
        else:
            regime = "default"
            filing_status = st.selectbox("Region", ["individual", "scotland"], format_func=lambda x: x.capitalize(), key="filing_status_uk")
            has_hra = False

    with c3:
        if country == "india" and has_hra:
            hra_received = st.number_input("HRA Received (INR)", min_value=0.0, value=120_000.0, step=5_000.0, key="hra_received")
            rent_paid = st.number_input("Annual Rent Paid (INR)", min_value=0.0, value=180_000.0, step=5_000.0, key="rent_paid")
            is_metro = st.checkbox("Metro City", value=True, key="is_metro")
        else:
            hra_received = 0.0
            rent_paid = 0.0
            is_metro = False
            st.markdown("")

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("### Deductions")

    tax_law_path = Path(__file__).parent / "tax_laws" / {"india": "india.json", "us": "us.json", "uk": "uk.json"}[country]
    try:
        with open(tax_law_path, "r") as f:
            tax_law = json.load(f)
        deductions_meta = tax_law.get("deductions", {})
    except (FileNotFoundError, json.JSONDecodeError):
        st.error(f"Tax law schema for {COUNTRY_LABELS.get(country, country)} could not be loaded. Please verify the `tax_laws` directory exists. Operating in Standard Mode (Basic Math) if engine permits fallback.")
        deductions_meta = {}

    claimed_deductions: Dict[str, float] = {}

    dcols = st.columns(3)
    col_idx = 0
    for ded_id, ded_info in deductions_meta.items():
        ded_regimes = ded_info.get("regimes", [])
        if ded_regimes and regime not in ded_regimes:
            continue
        limit = ded_info.get("limit")
        if limit is None:
            continue
        with dcols[col_idx % 3]:
            val = st.slider(
                f"{ded_id} — {ded_info['label'][:40]}",
                min_value=0.0,
                max_value=float(limit),
                value=0.0,
                step=max(1.0, float(limit) / 100),
                key=f"ded_{ded_id}",
            )
            claimed_deductions[ded_id] = val
        col_idx += 1

    profile = TaxProfile(
        country=country,
        gross_income=gross_income,
        age=age,
        filing_status=filing_status,
        regime=regime,
        deductions_claimed=claimed_deductions,
        has_hra=has_hra,
        hra_received=hra_received,
        rent_paid=rent_paid,
        is_metro=is_metro,
    )
    return profile


def render_summary_metrics(result: RegimeResult, country: str) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gross Income", _fmt(result.taxable_income + result.total_deductions, country))
    c2.metric("Total Deductions", _fmt(result.total_deductions, country))
    c3.metric("Total Tax Liability", _fmt(result.total_tax, country))
    c4.metric("Effective Tax Rate", f"{result.effective_rate:.1f}%")


def render_bar_chart(current_result: RegimeResult, opt_report: OptimizationReport, country: str) -> None:
    optimized_tax = current_result.total_tax - opt_report.total_recoverable_tax
    categories = ["Current Tax Liability", "Optimized Tax Liability"]
    values = [current_result.total_tax, max(0, optimized_tax)]
    colors = ["#F87171", "#34D399"]

    fig = go.Figure(
        go.Bar(
            x=categories,
            y=values,
            marker_color=colors,
            text=[_fmt(v, country) for v in values],
            textposition="outside",
            textfont=dict(color="#E2E8F0", size=13, family="Inter"),
            width=0.4,
        )
    )
    fig.update_layout(
        title=dict(text="Status Quo vs. AI-Optimized", font=dict(color="#F1F5F9", size=15, family="Inter")),
        yaxis_title=f"Tax ({COUNTRY_CURRENCY[country]})",
        showlegend=False,
        **PLOTLY_THEME,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_whatif_chart(profile: TaxProfile, country: str) -> None:
    tax_law_path = Path(__file__).parent / "tax_laws" / {"india": "india.json", "us": "us.json", "uk": "uk.json"}[country]
    try:
        with open(tax_law_path, "r") as f:
            tax_law = json.load(f)
    except Exception:
        st.info("What-If analysis requires tax law schema JSON, which could not be loaded.")
        return

    deductions_meta = tax_law.get("deductions", {})
    regime = profile.regime or "new"
    eligible = [
        ded_id for ded_id, info in deductions_meta.items()
        if info.get("limit") and (not info.get("regimes") or regime in info.get("regimes", []))
    ]

    if not eligible:
        st.info("No variable deductions available for What-If analysis.")
        return

    selected_ded = st.selectbox(
        "Select Deduction to Simulate",
        options=eligible,
        format_func=lambda x: f"{x} — {deductions_meta[x]['label'][:50]}",
        key="whatif_selection",
    )

    series = whatif_series(profile, selected_ded, steps=30)
    if not series:
        return

    investments = [s["investment"] for s in series]
    taxes = [s["tax"] for s in series]
    take_homes = [s["take_home"] for s in series]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=investments, y=taxes,
        mode="lines+markers",
        name="Tax Liability",
        line=dict(color="#F87171", width=2.5),
        marker=dict(size=4),
    ))
    fig.add_trace(go.Scatter(
        x=investments, y=take_homes,
        mode="lines",
        name="Take-Home",
        line=dict(color="#34D399", width=2, dash="dot"),
    ))
    fig.update_layout(
        title=dict(text=f"What-If: Tax vs {selected_ded} Investment", font=dict(color="#F1F5F9", size=15, family="Inter")),
        xaxis_title=f"Investment Amount ({COUNTRY_SYMBOL[country]})",
        yaxis_title=f"Amount ({COUNTRY_SYMBOL[country]})",
        legend=dict(bgcolor="#0F172A", bordercolor="#1E293B", font=dict(color="#94A3B8")),
        **PLOTLY_THEME,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_gap_indicator(current_result: RegimeResult, opt_report: OptimizationReport, country: str) -> None:
    gap = opt_report.money_left_on_table
    pct = (gap / current_result.total_tax * 100) if current_result.total_tax > 0 else 0

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=gap,
        number=dict(prefix=COUNTRY_SYMBOL[country], valueformat=",.0f", font=dict(color="#F87171", size=32, family="Inter")),
        delta=dict(reference=0, valueformat=",.0f"),
        gauge=dict(
            axis=dict(range=[0, max(gap * 1.5, 1)], tickfont=dict(color="#64748B")),
            bar=dict(color="#F87171"),
            bgcolor="#0F172A",
            bordercolor="#1E293B",
            steps=[
                dict(range=[0, gap * 0.5], color="#1A0A0A"),
                dict(range=[gap * 0.5, gap], color="#2D0A0A"),
            ],
        ),
        title=dict(text="Money Left on the Table", font=dict(color="#94A3B8", size=13, family="Inter")),
    ))
    fig.update_layout(paper_bgcolor="#070710", font=dict(family="Inter"), margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        f'<div class="gap-indicator"><span style="font-size:0.85rem;color:#FCA5A5;">You are leaving <strong>{_fmt(gap, country)}</strong> ({pct:.1f}% of your current tax bill) in recoverable tax savings unused.</span></div>',
        unsafe_allow_html=True,
    )


def render_scenario_tab(profile: TaxProfile, country: str) -> None:
    st.markdown("### Regime Comparison")
    try:
        comparison: ScenarioComparison = simulate_scenarios(profile)
    except Exception as e:
        st.error(str(e))
        return

    rows = []
    for scenario_name, result in comparison.scenarios.items():
        rows.append({
            "Scenario": scenario_name.replace("_", " ").title(),
            "Taxable Income": _fmt(result.taxable_income, country),
            "Deductions": _fmt(result.total_deductions, country),
            "Base Tax": _fmt(result.base_tax, country),
            "Total Tax": _fmt(result.total_tax, country),
            "Effective Rate": f"{result.effective_rate:.2f}%",
            "Take-Home": _fmt(result.take_home, country),
            "Best": "YES" if scenario_name == comparison.best_scenario else "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    scenario_names = list(comparison.scenarios.keys())
    taxes = [comparison.scenarios[s].total_tax for s in scenario_names]
    colors = ["#34D399" if s == comparison.best_scenario else "#60A5FA" for s in scenario_names]
    fig = go.Figure(go.Bar(
        x=[s.replace("_", " ").title() for s in scenario_names],
        y=taxes,
        marker_color=colors,
        text=[_fmt(t, country) for t in taxes],
        textposition="outside",
        textfont=dict(color="#E2E8F0", size=12),
    ))
    fig.update_layout(
        title=dict(text="Tax Liability by Scenario", font=dict(color="#F1F5F9", size=15, family="Inter")),
        yaxis_title=f"Tax ({COUNTRY_SYMBOL[country]})",
        showlegend=False,
        **PLOTLY_THEME,
    )
    st.plotly_chart(fig, use_container_width=True)

    best_result = comparison.scenarios[comparison.best_scenario]
    st.success(f"Recommended: **{comparison.best_scenario.replace('_', ' ').title()}** saves you {_fmt(max(taxes) - min(taxes), country)} vs the worst alternative.")


def render_document_tab(country: str, bridge: Optional[LLMBridge]) -> None:
    st.markdown("### Document Parser")
    st.markdown("Upload a tax document (Form 16, W-2, P60, pay slip, or any income statement) to auto-extract your income and deduction data.")

    uploaded = st.file_uploader(
        "Upload Document",
        type=["pdf", "png", "jpg", "jpeg", "bmp", "tiff"],
        key="doc_upload",
    )

    if uploaded is not None:
        with st.spinner("Extracting data from document..."):
            result = parse_document(uploaded.read(), uploaded.name, country, bridge)

        if "error" in result:
            st.error(result["error"])
            return

        st.markdown("#### Extracted Fields")
        display = {k: v for k, v in result.items() if not k.startswith("_")}
        if display:
            for field, value in display.items():
                st.markdown(
                    f'<div class="optimization-row"><span style="color:#64748B;font-size:0.8rem;">{field.replace("_"," ").upper()}</span>'
                    f'<br><span style="font-size:1rem;font-weight:600;color:#E2E8F0;">{value}</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.warning("No fields could be extracted. Try a higher-quality scan or a text-based PDF.")

        preview = result.get("_raw_text_preview", "")
        if preview:
            with st.expander("Raw Text Preview"):
                st.code(preview, language=None)

        if bridge is None:
            st.info("Awaiting Connection. Connect an LLM in the sidebar to enhance extraction accuracy with AI-assisted field mapping.")


def render_dtaa_tab() -> None:
    st.markdown("### Double Taxation Avoidance Agreement (DTAA) Checker")
    st.markdown("Identify treaty protections for income earned across multiple countries.")

    all_pairs = get_all_pairs()
    pair_labels = [p["pair"] for p in all_pairs]
    urls = {p["pair"]: p["treaty_url"] for p in all_pairs}

    selected_pair = st.selectbox("Select Treaty Pair", pair_labels, key="dtaa_pair")
    countries_in_pair = selected_pair.split(" — ")
    ca, cb = countries_in_pair[0].lower().strip(), countries_in_pair[1].lower().strip()

    st.markdown(
        f'<a href="{urls[selected_pair]}" target="_blank" class="source-link">View Official Treaty PDF</a>',
        unsafe_allow_html=True,
    )

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("#### Add Income Source")

    num_rows = st.number_input("Number of income streams", min_value=1, max_value=10, value=2, step=1, key="dtaa_num_rows")

    incomes = []
    for i in range(int(num_rows)):
        st.markdown(f"**Income Stream {i+1}**")
        rc1, rc2, rc3, rc4 = st.columns(4)
        with rc1:
            src_country = st.selectbox("Source Country", [ca, cb], key=f"dtaa_src_{i}")
        with rc2:
            res_country = ca if src_country == cb else cb
            st.text_input("Residence Country", value=res_country, disabled=True, key=f"dtaa_res_{i}")
        with rc3:
            income_type = st.selectbox("Income Type", INCOME_TYPES, key=f"dtaa_type_{i}")
        with rc4:
            amount = st.number_input("Amount", min_value=0.0, value=10_000.0, step=1_000.0, key=f"dtaa_amt_{i}")
        incomes.append({
            "source_country": src_country,
            "residence_country": res_country,
            "income_type": income_type,
            "amount": amount,
        })

    if st.button("Run DTAA Analysis", key="run_dtaa"):
        results = summarize_treaty_exposure(incomes)
        total_wht = sum(r["wht_amount"] for r in results)

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("#### Treaty Analysis Results")

        for r in results:
            treaty_badge = (
                '<span style="background:#064E3B;color:#6EE7B7;border-radius:5px;padding:2px 7px;font-size:0.7rem;font-weight:600;">TREATY FOUND</span>'
                if r["has_treaty"]
                else '<span style="background:#1E1B4B;color:#A5B4FC;border-radius:5px;padding:2px 7px;font-size:0.7rem;font-weight:600;">NO SPECIFIC TREATY</span>'
            )
            st.markdown(
                f'<div class="card">'
                f'{treaty_badge}'
                f'<p style="margin:0.5rem 0 0.2rem;font-weight:600;font-size:0.95rem;">{r["income_type"].replace("_"," ").title()} — {r["source_country"].title()} to {r["residence_country"].title()}</p>'
                f'<p style="margin:0;color:#64748B;font-size:0.82rem;">Amount: {r["amount"]:,.0f} &nbsp;|&nbsp; WHT: {r["wht_rate"]*100:.0f}% = {r["wht_amount"]:,.0f}</p>'
                f'<p style="margin:0.5rem 0 0.3rem;font-size:0.82rem;color:#CBD5E1;">{r["detail"]}</p>'
                + (f'<a href="{r["source_url"]}" target="_blank" class="source-link">View Treaty Article</a>' if r["source_url"] else "")
                + f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            f'<div class="gap-indicator"><span style="font-size:0.9rem;color:#FCA5A5;">Total Withholding Tax Exposure: <strong>{total_wht:,.2f}</strong></span></div>',
            unsafe_allow_html=True,
        )


def render_ca_reasoning(opt_report: OptimizationReport, profile: TaxProfile, bridge: Optional[LLMBridge]) -> None:
    st.markdown("### CA Intelligence Report")
    if bridge is None:
        st.info("Awaiting Connection. Connect an LLM provider in the sidebar to activate CA Reasoning.")
        return

    if st.button("Generate CA Analysis", key="ca_reason"):
        system = (
            "You are a senior Chartered Accountant with 20 years of experience in international tax law. "
            "Provide a sharp, precise, professional analysis. No filler, no AI-cliche phrases. "
            "Focus on actionable strategies with specific amounts and legal references. "
            "Do not perform arithmetic — the numbers are pre-calculated and provided to you."
        )
        recs_text = "\\n".join(
            f"- {r.label} ({r.deduction_id}): Room = {r.additional_room:,.0f}, Tax Saving = {r.tax_saving:,.0f}, Source: {r.source_url}"
            for r in opt_report.recommendations[:6]
        )
        user = (
            f"Client Profile: Country={profile.country.upper()}, Gross Income={profile.gross_income:,.0f}, Age={profile.age}, "
            f"Regime={profile.regime or 'default'}\\n"
            f"Current Tax: {opt_report.worst_regime_tax:,.0f}\\n"
            f"Optimized Tax (best regime): {opt_report.best_regime_tax:,.0f}\\n"
            f"Money Left on Table: {opt_report.money_left_on_table:,.0f}\\n"
            f"Top Deduction Opportunities:\\n{recs_text}\\n\\n"
            "Provide a concise professional tax optimization briefing, referencing specific sections and amounts."
        )
        with st.spinner("Generating analysis..."):
            try:
                output = bridge.reason(system, user)
                st.markdown(
                    f'<div class="card"><p style="font-size:0.9rem;line-height:1.7;color:#CBD5E1;">{output}</p></div>',
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.error(str(e))


def main() -> None:
    country = render_sidebar()

    st.markdown(
        '<h1 style="font-size:2rem;font-weight:700;letter-spacing:-0.03em;margin-bottom:0.25rem;">Global Agentic Tax Hub</h1>'
        '<p style="color:#64748B;font-size:0.95rem;margin-bottom:1.5rem;">Chartered Accountant-Grade Tax Optimization for India, United States, and United Kingdom</p>',
        unsafe_allow_html=True,
    )

    bridge = _get_bridge()

    profile = render_tax_calculator(country)
    if profile is None:
        return

    tab_calc, tab_scenarios, tab_whatif, tab_docs, tab_dtaa = st.tabs([
        "Tax Calculator",
        "Scenario Comparison",
        "What-If Analysis",
        "Document Parser",
        "DTAA Checker",
    ])

    with tab_calc:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        try:
            result = calculate_tax(profile)
            opt_report = optimize(profile)
        except Exception as e:
            st.error(f"Tax computation error: {e}")
            return

        render_summary_metrics(result, country)

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        cola, colb = st.columns(2)
        with cola:
            render_bar_chart(result, opt_report, country)
        with colb:
            render_gap_indicator(result, opt_report, country)

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("### Optimization Recommendations")

        if not opt_report.recommendations:
            st.success("All available deductions are fully utilized. No further optimization possible.")
        else:
            for rec in opt_report.recommendations:
                if rec.tax_saving <= 0:
                    continue
                st.markdown(
                    f'<div class="optimization-row">'
                    f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                    f'<span style="font-weight:600;font-size:0.9rem;color:#E2E8F0;">{rec.deduction_id} &mdash; {rec.label}</span>'
                    f'<span style="color:#34D399;font-weight:700;font-size:0.9rem;">Save {_fmt(rec.tax_saving, country)}</span>'
                    f'</div>'
                    f'<p style="margin:0.3rem 0 0.2rem;color:#64748B;font-size:0.8rem;">'
                    f'Currently claimed: {_fmt(rec.current_claimed, country)} &nbsp;|&nbsp; Limit: {_fmt(rec.max_allowed, country)} &nbsp;|&nbsp; Unused room: {_fmt(rec.additional_room, country)}'
                    f'</p>'
                    f'<a href="{rec.source_url}" target="_blank" class="source-link">Official Source</a>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        render_ca_reasoning(opt_report, profile, bridge)

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("### Tax Bracket Breakdown")
        if result.bracket_breakdown:
            bd_df = pd.DataFrame([{
                "Band": b.band,
                "Income in Band": _fmt(b.income_in_band, country),
                "Rate": f"{b.rate*100:.0f}%",
                "Tax": _fmt(b.tax, country),
            } for b in result.bracket_breakdown])
            st.dataframe(bd_df, use_container_width=True, hide_index=True)

    with tab_scenarios:
        render_scenario_tab(profile, country)

    with tab_whatif:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        render_whatif_chart(profile, country)

    with tab_docs:
        render_document_tab(country, bridge)

    with tab_dtaa:
        render_dtaa_tab()


if __name__ == "__main__":
    main()
