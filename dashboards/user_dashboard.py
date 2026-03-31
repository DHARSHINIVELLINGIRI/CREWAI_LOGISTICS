"""
User Tracking Dashboard — shows only the logged-in user's shipments.
Call render_user_dashboard(db, user_id, user_name) from app.py.
"""
import streamlit as st
import streamlit.components.v1 as components
from shipment.crew import eShipzOrchestrator
from shipment.main import run as run_crew
import datetime
import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from services.tracking_service import (
    track_shipment, get_tracking_history,
    predict_shipment_delay, get_route_visualization, generate_ai_insight,
)
from services.map_visualization import build_shipment_map
from services.lifecycle import (
    LIFECYCLE_STAGES, STAGE_CONFIG, format_timeline_event, stage_to_percentage
)
from agents.llm_router import LLMRouter
from auth.auth_service import get_user_shipments
from services.barcode_service import render_barcode_section


def render_user_dashboard(db=None, user_id: int = 0, user_name: str = "User"):
    st.title(f"📦 My Logistics Hub")
    st.caption(f"Welcome, **{user_name}** · Your personal shipment control center")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_track, tab_history, tab_ai = st.tabs([
        "📍 Live Tracking",
        "📋 My Shipments",
        "🤖 AI Assistant",
    ])

    # ═══ Tab 1: Live Tracking ═════════════════════════════════════════════════
    with tab_track:
        st.subheader("📍 Track Your Shipment")

        # Pop relay set by "Quick Track" history buttons (before widget is created)
        _default_tid = st.session_state.pop("_pending_track_id", "")

        col_input, col_btn = st.columns([4, 1])
        with col_input:
            tracking_id = st.text_input(
                "Tracking ID", placeholder="e.g. TKT000001",
                value=_default_tid,
                label_visibility="collapsed", key="user_track_input"
            )
        with col_btn:
            track_btn = st.button("🔍 Track", use_container_width=True, key="user_track_btn")

        # Show last booked hint
        if not tracking_id and st.session_state.get("last_tracking_id"):
            st.caption(f"💡 Your last shipment: **{st.session_state['last_tracking_id']}**")

        # Auto-track when navigated from history, or when button clicked
        if (track_btn or _default_tid) and tracking_id:
            _render_tracking_result(tracking_id.strip().upper(), db)


    # ═══ Tab 2: My Shipment History ═══════════════════════════════════════════
    with tab_history:
        st.subheader("📋 My Shipment History")
        my_ships = get_user_shipments(user_id)

        if not my_ships:
            st.info("You have no shipments yet. Book one on the **New Shipment** page.")
        else:
            import pandas as pd
            rows = []
            for s in my_ships:
                rows.append({
                    "Tracking ID": s.get("tracking_id", ""),
                    "Route":       f"{s.get('source','?')} → {s.get('destination','?')}",
                    "Weight (kg)": s.get("weight", ""),
                    "Priority":    s.get("priority", ""),
                    "Carrier":     s.get("carrier", "—"),
                    "Status":      s.get("status", ""),
                    "Booked At":   str(s.get("created_at", ""))[:16],
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # ── Per-shipment barcode expanders ─────────────────────────────────
            st.markdown("---")
            st.caption("🏷️ Expand a shipment below to view its barcode label and details:")
            for s in my_ships:
                tid     = s.get("tracking_id", "")
                carrier = s.get("carrier", "Pending")
                status  = s.get("status", "")
                route   = f"{s.get('source','?')} → {s.get('destination','?')}"
                carrier_display = carrier if carrier and carrier != "Pending" else "Pending Assignment"
                with st.expander(
                    f"🏷️ {tid}  │  {route}  │  🚚 {carrier_display}  │  {status}",
                    expanded=False
                ):
                    detail_col, barcode_col = st.columns([1, 1])
                    with detail_col:
                        st.markdown("**Shipment Details**")
                        st.markdown(
                            f"- **Tracking ID:** `{tid}`\n"
                            f"- **Origin:** {s.get('source', '—')}\n"
                            f"- **Destination:** {s.get('destination', '—')}\n"
                            f"- **Carrier:** {carrier_display}\n"
                            f"- **Status:** {status or '—'}\n"
                            f"- **Weight:** {s.get('weight', '—')} kg\n"
                            f"- **Priority:** {s.get('priority', '—')}\n"
                            f"- **Booked At:** {str(s.get('created_at', ''))[:16]}"
                        )
                    with barcode_col:
                        st.markdown("**Barcode Label**")
                        barcode_val = s.get("awb") or tid
                        render_barcode_section(
                            st_container  = barcode_col,
                            tracking_id   = barcode_val,
                            show_download = True,
                            compact       = False,
                            key_suffix    = "history",
                        )

            # ── Quick track from history ───────────────────────────────────────
            st.markdown("---")
            st.caption("Click a shipment to track it live:")
            cols = st.columns(min(len(my_ships[:5]), 5))
            selected_tid = st.session_state.get("_hist_selected_tid", "")
            for i, s in enumerate(my_ships[:5]):
                tid = s.get("tracking_id", "")
                with cols[i]:
                    if st.button(f"📍 {tid}", key=f"hist_track_{tid}",
                                 use_container_width=True,
                                 type="primary" if tid == selected_tid else "secondary"):
                        st.session_state["_hist_selected_tid"] = tid

            # If a shipment is selected, show tracking inline
            active_tid = st.session_state.get("_hist_selected_tid", "")
            if active_tid:
                st.markdown(f"#### 🗺️ Live Tracking — `{active_tid}`")
                _render_tracking_result(active_tid, db)


    # ═══ Tab 3: AI Assistant ══════════════════════════════════════════════════
    with tab_ai:
        st.subheader("🤖 AI Tracking Assistant")
        st.caption("Real-time eShipz API · Multi-agent CrewAI · Live checkpoint intelligence")

        from tracking_renderer import render_tracking_output

        col_tid, col_ai_btn = st.columns([4, 1])
        with col_tid:
            ai_track_id = st.text_input(
                "Tracking ID for AI Analysis",
                value="90001605035",
                placeholder="e.g. 90001605035",
                label_visibility="collapsed",
                key="ai_track_input",
            )
        with col_ai_btn:
            _run_crew_btn = st.button("🤖 Analyse", use_container_width=True, key="dash_crew_btn")

        st.markdown("""
        <style>
        .agent-card{background:#12141b;border:1px solid #1e2a45;border-radius:10px;
                    padding:14px 18px;margin-bottom:10px;}
        .agent-card .ac-label{font-size:.68rem;color:#6366f1;font-weight:700;
                              text-transform:uppercase;letter-spacing:.5px;}
        .agent-card .ac-agent{font-size:.78rem;color:#64748b;margin-top:2px;}
        .agent-card .ac-body{font-size:.84rem;color:#cbd5e1;margin-top:8px;
                             line-height:1.55;white-space:pre-wrap;}
        </style>""", unsafe_allow_html=True)

        if _run_crew_btn and ai_track_id.strip():
            with st.status("🤖 AI agents working …", expanded=True) as _ds:
                st.write("🧠 Planner → carrier selection …")
                st.write("📦 Booker → AWB generation …")
                st.write("🛰️ Tracker → calling eShipz V2 API …")
                try:
                    _crew_result = run_crew(tracking_id=ai_track_id.strip())
                    st.session_state["crew_report"] = _crew_result
                    _ds.update(label="✅ Analysis complete", state="complete", expanded=False)
                except Exception as _ce:
                    _ds.update(label="❌ Error", state="error")
                    st.error(f"CrewAI Error: {_ce}")

        if "crew_report" in st.session_state:
            _r = st.session_state["crew_report"]

            # Token metrics
            try:
                _tu = _r.token_usage
                _c1, _c2, _c3, _c4 = st.columns(4)
                _c1.metric("🔢 Total Tokens",      f"{_tu.total_tokens:,}")
                _c2.metric("📤 Prompt Tokens",     f"{_tu.prompt_tokens:,}")
                _c3.metric("📥 Completion Tokens", f"{_tu.completion_tokens:,}")
                _c4.metric("🔄 API Calls",         _tu.successful_requests)
            except Exception:
                pass

            # Agent decision cards (planner + booker only)
            _card_meta = {
                "carrier_selection_task": "🧠 Planner — Carrier Recommendation",
                "booking_task":           "📦 Booker — AWB & Barcode",
            }
            for _to in (_r.tasks_output or []):
                if _to.name not in _card_meta:
                    continue
                _body = (_to.raw or "").strip()
                if len(_body) > 420:
                    _body = _body[:420] + " …"
                st.markdown(
                    f'<div class="agent-card">'
                    f'<div class="ac-label">{_card_meta[_to.name]}</div>'
                    f'<div class="ac-agent">Agent: {(_to.agent or "").strip()}</div>'
                    f'<div class="ac-body">{_body}</div></div>',
                    unsafe_allow_html=True,
                )

            # Full checkpoint table
            st.markdown("---")
            st.subheader("📍 Live Checkpoint Intelligence")
            render_tracking_output(_r)

            if st.button("🗑️ Clear Report", key="dash_clear_crew"):
                del st.session_state["crew_report"]
                st.rerun()

        st.markdown("---")
        # --- EXISTING ROUTER SECTION ---
        st.markdown("#### 💬 General Queries")
        query = st.text_input(
            "Your question",
            placeholder="e.g. 'Where is TKT123456?' or 'Will it be delayed?'",
            key="user_ai_query"
        )
        ask_btn = st.button("💬 Ask", key="user_ask_btn")

        if ask_btn and query:
            router = LLMRouter(db=db)
            result = router.route(query)
            with st.container(border=True):
                st.markdown(f"**🕹️ Routed to:** `{result['agent']}`")
                st.markdown(result["response"])


# ── Internal: full tracking result render ─────────────────────────────────────
def _render_tracking_result(tracking_id: str, db):
    info = track_shipment(tracking_id, db)

    if info.get("error"):
        st.error(info["message"])
        return

    status = info.get("status", "Unknown")
    status_color = {"In Transit": "#00D1FF", "Delivered": "#22C55E",
                    "Pending": "#F59E0B"}.get(status, "#94A3B8")

    st.markdown(
        f"""<div style="background:rgba(22,27,34,0.8);border:1px solid {status_color};
        border-radius:12px;padding:16px;margin-bottom:16px;">
        <span style="color:{status_color};font-size:1.3rem;font-weight:700;">● {status}</span>
        <span style="color:#D1D5DB;font-size:1rem;margin-left:16px;">
        {tracking_id} | {info.get('carrier','—')}</span></div>""",
        unsafe_allow_html=True
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("📍 Current",     info.get("current_city", "—"))
    c2.metric("🏁 Destination", info.get("destination", "—"))
    c3.metric("⏱ ETA",         info.get("eta", "—"))

    # ── Lifecycle stage progress bar ───────────────────────────────────────────
    current_stage = status
    stage_idx = next((i for i, s in enumerate(LIFECYCLE_STAGES) if s == current_stage), 1)
    stage_cols = st.columns(len(LIFECYCLE_STAGES))
    for i, stage in enumerate(LIFECYCLE_STAGES):
        cfg = STAGE_CONFIG.get(stage, {})
        is_done    = i < stage_idx
        is_current = i == stage_idx
        opacity = "1" if (is_done or is_current) else "0.3"
        border  = f"2px solid {cfg.get('color','#555')}"
        bg      = cfg.get("color", "#333") if is_done else ("#1e293b" if not is_current else "#1e293b")
        stage_cols[i].markdown(
            f"<div style='text-align:center;border:{border};border-radius:10px;"
            f"padding:8px 4px;opacity:{opacity};background:{bg}10;'>"
            f"<div style='font-size:1.4rem'>{cfg.get('icon','📍')}</div>"
            f"<div style='font-size:0.65rem;color:#D1D5DB;margin-top:2px'>{stage}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    st.markdown("&nbsp;", unsafe_allow_html=True)

    # Map
    st.subheader("🗺️ Live Route Map")
    viz = get_route_visualization(tracking_id, db)
    if not viz.get("error"):
        map_html = build_shipment_map(
            route_coords=viz.get("route_coords", []),
            current_lat=viz.get("current_lat") or info.get("lat"),
            current_lon=viz.get("current_lon") or info.get("lon"),
            height=420,
        )
        components.html(map_html, height=430, scrolling=False)
    else:
        # Minimal map showing just current position
        cur_lat = info.get("lat", 20.5)
        cur_lon = info.get("lon", 78.0)
        src  = info.get("source", "")
        dst  = info.get("destination", "")
        if src and dst:
            from services.india_network import bfs_route, INDIA_CITIES
            route = bfs_route(src, dst)
            route_coords = [
                {"city": c, "lat": INDIA_CITIES[c]["lat"], "lon": INDIA_CITIES[c]["lon"]}
                for c in route if c in INDIA_CITIES
            ]
            map_html = build_shipment_map(
                route_coords=route_coords,
                current_lat=cur_lat, current_lon=cur_lon,
                height=420,
            )
            components.html(map_html, height=430, scrolling=False)
        else:
            st.info("📍 Route map unavailable — shipment data not in live simulation.")


    col_ins, col_del = st.columns(2)
    with col_ins:
        st.subheader("🧠 AI Insight")
        with st.container(border=True):
            st.markdown(generate_ai_insight(tracking_id, db))

    with col_del:
        st.subheader("⚠️ Delay Prediction")
        delay = predict_shipment_delay(tracking_id, db)
        if not delay.get("error"):
            d1, d2 = st.columns(2)
            d1.metric("Probability", delay.get("delay_probability_pct", "—"))
            d2.metric("Extra Time",  f"{delay.get('predicted_delay_minutes', 0)} min")
            st.caption(f"Risk: **{delay.get('risk_level','—')}** — {delay.get('reason','—')}")

    # Timeline
    st.subheader("📅 Shipment Timeline")
    history = get_tracking_history(tracking_id, db)
    events  = history.get("past_events", [])
    if events:
        for ev in reversed(events[-10:]):
            rich = format_timeline_event(
                ev.get("event", "").replace("📍 Arrived at ", "In Transit").replace("📦 Delivered at ", "Delivered").replace("⚠️ Delay recorded near ", "Delayed"),
                ev.get("location", "—"),
                ev.get("timestamp", ""),
            )
            color = rich["color"]
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:10px;"
                f"padding:8px 12px;border-left:3px solid {color};"
                f"margin-bottom:6px;border-radius:0 8px 8px 0;"
                f"background:{color}11;'>"
                f"<span style='font-size:1.2rem'>{rich['icon']}</span>"
                f"<div><b style='color:{color}'>{rich['status']}</b>"
                f"<span style='color:#94A3B8;font-size:0.8rem;margin-left:8px'>{rich['timestamp']}</span><br>"
                f"<span style='color:#D1D5DB;font-size:0.85rem'>{rich['label']}</span></div>"
                f"</div>",
                unsafe_allow_html=True
            )
    else:
        st.info("No timeline events yet — check back in a few seconds.")

    # ── Barcode label ──────────────────────────────────────────────────────────
    with st.expander("🏷️ Shipment Barcode Label", expanded=False):
        bc_col, _ = st.columns([1, 1])
        with bc_col:
            render_barcode_section(
                st_container  = st,
                tracking_id   = tracking_id,
                source        = info.get("source", ""),
                destination   = info.get("destination", ""),
                carrier       = info.get("carrier", "Pending Assignment"),
                status        = info.get("status", ""),
                show_download = True,
                compact       = False,
                key_suffix    = "track",
            )
def handle_tracking_request(tracking_id):
    # Initialize your crew
    orchestrator = eShipzOrchestrator().crew()
    
    # Kickoff with the tracking ID as an input variable
    # This matches the {tracking_id} in your tasks.yaml
    result = orchestrator.kickoff(inputs={'tracking_id': tracking_id})
    
    return result
def run_eshipz_tracking(id_to_track):
    # 1. Initialize the Crew class
    # 2. Call .crew() to get the actual Crew object
    # 3. Pass the 'tracking_id' variable into inputs
    
    inputs = {
        'tracking_id': id_to_track # This will be "90001605035"
    }
    
    result = eShipzOrchestrator().crew().kickoff(inputs=inputs)
    return result