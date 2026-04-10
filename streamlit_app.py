import streamlit as st
import asyncio
from datetime import datetime

from app.agent.runtime import run_agent

st.set_page_config(page_title="ChemInvest Agent", layout="wide")

st.title("ChemInvest Agent")
st.caption("LangGraph · Multi-Skill · Interpretable Decision")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Configuration")
    use_trace = st.checkbox("Show Decision Trace", value=False)
    st.divider()
    st.markdown("**Available Skills**\n- Financial Analysis\n- Industry Comparison\n- Cross-Skill Fusion")
    st.caption(f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ---------- Session History ----------
if "history" not in st.session_state:
    st.session_state["history"] = []

# ---------- Main Input ----------
query = st.text_input(
    "Query",
    placeholder="e.g., Analyze Wanhua Chemical's financials and industry position",
    value="Analyze Wanhua Chemical's financial condition and industry standing"
)

if st.button("Run Analysis", type="primary", use_container_width=True):
    with st.spinner("Agent is planning and executing skills..."):
        try:
            result = asyncio.run(run_agent(query))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(run_agent(query))
            loop.close()

    # Save to history
    st.session_state["history"].append({
        "query": query,
        "result": result,
        "timestamp": datetime.now().isoformat()
    })

    # ---------- Helper to extract structured data ----------
    skill_results = result.get("skill_results", {})
    financial_data = skill_results.get("financial_analysis", {})
    industry_data = skill_results.get("industry_comparison", {})

    # Extract structured fields (adjust keys based on your actual schema)
    financial_detail = financial_data.get("financial", {})
    quant_detail = financial_data.get("quant", {})
    insight = financial_data.get("insight", "")

    industry_target = industry_data.get("target", {})
    industry_comparison = industry_data.get("comparison", {})
    peers = industry_data.get("peers", [])

    # Fusion result (if returned by run_agent)
    fusion = result.get("fusion", {})
    final_recommendation = fusion.get("reasoning", insight)
    confidence = fusion.get("confidence", None)
    signal_type = fusion.get("signal_type", "")

    # ---------- Structured Report ----------
    st.header("Analysis Report")

    # 1. Summary (use insight or fusion reasoning)
    st.subheader("Executive Summary")
    st.write(insight or final_recommendation or "No summary available.")

    # 2. Financial Analysis
    st.subheader("Financial Health")
    if financial_detail:
        revenue = financial_detail.get("revenue", {})
        net_profit = financial_detail.get("net_profit", {})
        roe = financial_detail.get("roe", {})
        growth_summary = financial_detail.get("growth_summary", "")
        st.markdown("**Key Metrics**")
        if revenue:
            st.write(f"- Revenue: {revenue.get('value')} {revenue.get('unit', '')} (YoY {revenue.get('yoy', 0):.1%})")
        if net_profit:
            st.write(f"- Net Profit: {net_profit.get('value')} {net_profit.get('unit', '')} (YoY {net_profit.get('yoy', 0):.1%})")
        if roe:
            st.write(f"- ROE: {roe.get('value', 0):.1%}")
        if growth_summary:
            st.caption(growth_summary)
    else:
        st.info("Financial data not available.")

    # 3. Industry Position
    st.subheader("Industry Position")
    if industry_target:
        rank_pct = industry_target.get("industry_rank")
        pred_return = industry_target.get("pred_return")
        st.write(f"- Industry rank percentile: {rank_pct:.0%}" if rank_pct else "- Industry rank: N/A")
        st.write(f"- Predicted return (5d): {pred_return:.2%}" if pred_return else "")
    if industry_comparison:
        st.write(f"- Relative strength: {industry_comparison.get('relative_strength', 'N/A')}")
        st.write(f"- Conclusion: {industry_comparison.get('conclusion', '')}")
    if peers:
        st.write("**Top Peers**")
        for p in peers[:3]:
            st.write(f"- {p.get('stock')}: predicted return {p.get('pred_return', 0):.2%}")

    # 4. Final Verdict (强化)
    st.subheader("Final Verdict")
    # Determine color based on signal type
    if signal_type in ["trend_follow", "positive"]:
        st.success(final_recommendation or "Positive outlook based on multi-source fusion.")
    elif signal_type in ["negative", "weak"]:
        st.error(final_recommendation or "Negative outlook. Exercise caution.")
    else:
        st.warning(final_recommendation or "Mixed signals. Further analysis recommended.")

    if confidence is not None:
        st.progress(confidence, text=f"Confidence: {confidence:.0%}")

    # 5. Decision Trace (if enabled)
    if use_trace:
        st.divider()
        st.subheader("Decision Rationale")
        selected_skills = result.get("selected_skills", [])
        st.write("**Activated Skills**")
        for skill in selected_skills:
            st.write(f"- {skill}")
        # Show reasoning if provided by planner (future enhancement)
        st.caption("Skill selection based on keyword matching (upgradeable to LLM planner).")

# ---------- History Sidebar ----------
with st.sidebar:
    st.divider()
    st.subheader("Session History")
    if st.session_state["history"]:
        for i, entry in enumerate(reversed(st.session_state["history"][-5:])):
            with st.expander(f"Q{i+1}: {entry['query'][:30]}..."):
                st.write(entry["result"].get("answer", "")[:200] + "...")
    else:
        st.caption("No queries yet.")