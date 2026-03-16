"""
Admin Monitoring Dashboard — with User Management, Shipment Control, and Analytics.
Call render_admin_dashboard(db) from app.py.
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import datetime
import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from services.simulation_engine import get_simulator
from services.carrier_analytics import get_analytics
from services.map_visualization import build_india_map
from services.delay_prediction import predict_delay
from services.india_network import INDIA_CITIES
from services.lifecycle import (
    LIFECYCLE_STAGES, STAGE_CONFIG, get_stage_icon, get_stage_color,
    STAGE_DELIVERED, STAGE_DELAYED,
)
from auth.auth_service import (
    get_all_users, search_users, get_all_shipments,
    update_shipment_status, get_shipment_stats, get_user_count
)
from services.barcode_service import render_barcode_section


def render_admin_dashboard(db=None):
    st.title("🛰️ Admin Command Center")
    st.caption(f"Logged in as Administrator · {datetime.datetime.now().strftime('%d %b %Y, %H:%M IST')}")

    sim       = get_simulator(db=db)
    analytics = get_analytics(db=db)
    active    = sim.get_all_active()
    status_counts = sim.get_status_counts()

    # ── KPI Strip ─────────────────────────────────────────────────────────────
    stats       = get_shipment_stats()
    user_count  = get_user_count()
    total_active= status_counts.get("In Transit", 0)
    total_delayed = status_counts.get("Delayed", 0)
    perf_rows   = analytics.summary_table()
    avg_rel     = round(
        sum(r["Reliability Score"] for r in perf_rows) / max(len(perf_rows), 1), 2
    ) if perf_rows else 0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("👥 Users",          user_count)
    k2.metric("📦 DB Shipments",   stats.get("total", 0))
    k3.metric("🚚 In Transit",     total_active)
    k4.metric("⚠️ Delayed",        total_delayed)
    k5.metric("📊 Avg Reliability", f"{avg_rel*100:.1f}%")
    k6.metric("🏙️ City Hubs",      len(INDIA_CITIES))

    st.markdown("---")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_map, tab_shipments, tab_users, tab_analytics = st.tabs([
        "🗺️ India Live Map",
        "📋 All Shipments",
        "👥 User Management",
        "📈 Carrier Analytics"
    ])

    # ═══ Tab 1: India Live Map ════════════════════════════════════════════════
    with tab_map:
        st.subheader("🗺️ Real-Time India Fleet Map")
        st.caption("All active shipments across India · 24 city hubs · Filter and search below ↓")

        # Filter selector (outside map for Streamlit control)
        col_f, col_s, col_b = st.columns([2, 3, 1])
        with col_f:
            map_filter = st.selectbox("Filter shipments",
                ["All", "In Transit", "Delayed", "Delivered"], key="admin_map_filter")
        with col_s:
            search_highlight = st.text_input("🔍 Highlight TKT ID on map",
                placeholder="e.g. TKT000001", key="admin_map_search")

        # Apply filter
        ships_to_show = active
        if map_filter != "All":
            ships_to_show = [s for s in active if s.get("status") == map_filter]

        map_html = build_india_map(
            shipments    = ships_to_show,
            city_nodes   = INDIA_CITIES,
            height       = 520,
            highlight_tid= search_highlight.strip().upper() or None,
        )
        components.html(map_html, height=530, scrolling=False)

        # Live status summary
        sc = sim.get_status_counts()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🟦 In Transit", sc.get("In Transit", 0))
        m2.metric("🟡 Delayed",    sc.get("Delayed", 0))
        m3.metric("🟢 Delivered",  sc.get("Delivered", 0))
        m4.metric("⬜ Other",      sc.get("Pending", 0) + sc.get("Booked", 0))


    # ═══ Tab 2: All Shipments ═════════════════════════════════════════════════
    with tab_shipments:
        st.subheader("📋 All Shipments")

        col_filter, col_status = st.columns([3, 1])
        with col_filter:
            search_term = st.text_input("🔍 Search by tracking ID, user, or route",
                                        key="admin_ship_search")
        with col_status:
            status_filter = st.selectbox(
                "Filter by Status",
                ["All"] + LIFECYCLE_STAGES + ["Delayed", "Cancelled"],
                key="admin_status_filter"
            )

        all_ships = get_all_shipments()

        if search_term:
            q = search_term.lower()
            all_ships = [s for s in all_ships if
                         q in s.get("tracking_id", "").lower() or
                         q in (s.get("user_name") or "").lower() or
                         q in (s.get("source") or "").lower() or
                         q in (s.get("destination") or "").lower()]
        if status_filter != "All":
            all_ships = [s for s in all_ships if s.get("status") == status_filter]

        if all_ships:
            df_rows = []
            for s in all_ships:
                df_rows.append({
                    "Tracking ID":  s.get("tracking_id", ""),
                    "User":         s.get("user_name", "—"),
                    "Email":        s.get("user_email", "—"),
                    "Route":        f"{s.get('source','?')} → {s.get('destination','?')}",
                    "Weight (kg)":  s.get("weight", ""),
                    "Priority":     s.get("priority", ""),
                    "Carrier":      s.get("carrier", "—"),
                    "Status":       s.get("status", ""),
                    "Booked At":    str(s.get("created_at", ""))[:16],
                })
            df = pd.DataFrame(df_rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Status update
            st.markdown("#### ✏️ Update Shipment Status")
            up_col1, up_col2, up_col3 = st.columns([2, 2, 1])
            with up_col1:
                tid_to_update = st.text_input("Tracking ID to update", key="admin_update_tid")
            with up_col2:
                new_status = st.selectbox(
                    "New Status",
                    LIFECYCLE_STAGES + ["Delayed", "Cancelled"],
                    key="admin_new_status"
                )
            with up_col3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ Update", key="admin_update_btn"):
                    if tid_to_update:
                        ok = update_shipment_status(tid_to_update, new_status)
                        st.success(f"Updated {tid_to_update} → {new_status}") if ok else st.error("Tracking ID not found.")
                    else:
                        st.warning("Enter a Tracking ID.")
        else:
            st.info("No shipments found matching filters.")

        # ── Per-shipment barcode expanders (admin view) ────────────────────────
        if all_ships:
            st.markdown("---")
            st.caption("🏷️ Expand a shipment to view / download its barcode:")
            for s in all_ships:
                tid     = s.get("tracking_id", "")
                carrier = s.get("carrier", "Pending")
                carrier_display = carrier if carrier and carrier != "Pending" else "Pending Assignment"
                status  = s.get("status", "")
                route   = f"{s.get('source','?')} → {s.get('destination','?')}"
                with st.expander(
                    f"🏷️ {tid}  │  {route}  │  🚚 {carrier_display}  │  {status}",
                    expanded=False
                ):
                    info_col, barcode_col = st.columns([1, 1])
                    with info_col:
                        st.markdown("**Shipment Details**")
                        st.markdown(
                            f"- **Tracking ID:** `{tid}`\n"
                            f"- **User:** {s.get('user_name', '—')}  ({s.get('user_email', '—')})\n"
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
                        )

        st.markdown("---")
        st.subheader("⚡ Live Simulation Shipments")
        st.caption("These shipments are actively moving in the simulation. Use action buttons to control them.")
        if active:
            for s in active:
                eta_str = "—"
                try:
                    eta_dt = datetime.datetime.fromisoformat(s["eta"])
                    hrs = max(0.0, (eta_dt - datetime.datetime.now()).total_seconds() / 3600)
                    eta_str = f"{hrs:.1f} h"
                except Exception:
                    pass

                status   = s.get("status", "")
                s_color  = get_stage_color(status)
                s_icon   = get_stage_icon(status)
                tid      = s.get("tracking_id", "")

                with st.container(border=True):
                    hdr_col, act_col = st.columns([3, 2])
                    with hdr_col:
                        st.markdown(
                            f"<b style='color:{s_color}'>{s_icon} {status}</b> │ "
                            f"<b>{tid}</b> │ "
                            f"{s.get('source', '?')} → {s.get('destination', '?')} │ "
                            f"{s.get('carrier', '?')} │ ⏱ ETA {eta_str}",
                            unsafe_allow_html=True
                        )
                    with act_col:
                        btn_col1, btn_col2, btn_col3 = st.columns(3)
                        with btn_col1:
                            if status != STAGE_DELIVERED:
                                if st.button("✅ Deliver", key=f"deliver_{tid}",
                                             use_container_width=True):
                                    sim.mark_delivered(tid)
                                    update_shipment_status(tid, STAGE_DELIVERED)
                                    st.success(f"{tid} marked Delivered")
                                    st.rerun()
                        with btn_col2:
                            if status != STAGE_DELAYED and status != STAGE_DELIVERED:
                                if st.button("⚠️ Delay", key=f"delay_{tid}",
                                             use_container_width=True):
                                    sim.force_delay(tid, minutes=30)
                                    st.warning(f"{tid} delayed +30 min")
                        with btn_col3:
                            if st.button("📍 Track", key=f"admin_track_{tid}",
                                         use_container_width=True):
                                st.session_state["admin_track_open"] = tid

            # Inline tracking + barcode panel for selected shipment
            if st.session_state.get("admin_track_open"):
                _tid = st.session_state["admin_track_open"]
                st.markdown(f"#### 🗺 Tracking: `{_tid}`")
                import streamlit.components.v1 as _comp
                from services.tracking_service import get_route_visualization, track_shipment
                from services.map_visualization import build_shipment_map
                viz = get_route_visualization(_tid, db)
                if not viz.get("error"):
                    _comp.html(build_shipment_map(
                        route_coords=viz.get("route_coords", []),
                        current_lat=viz.get("current_lat"),
                        current_lon=viz.get("current_lon"),
                        height=380,
                    ), height=390, scrolling=False)

                # ── Barcode for the tracked shipment ────────────────────────────
                with st.expander("🏷️ Barcode Label", expanded=True):
                    _info = track_shipment(_tid, db)
                    _bc_col, _ = st.columns([1, 1])
                    with _bc_col:
                        render_barcode_section(
                            st_container  = _bc_col,
                            tracking_id   = _tid,
                            show_download = True,
                            compact       = False,
                        )
        else:
            st.info("No active live shipments.")

    # ═══ Tab 3: User Management ═══════════════════════════════════════════════
    with tab_users:
        st.subheader("👥 Registered Users")
        st.caption("All accounts in the Eshipz platform database.")

        user_search = st.text_input("🔍 Search by name or email", key="admin_user_search")
        users = search_users(user_search) if user_search else get_all_users()
        role_filter = st.selectbox("Filter by Role", ["All", "user", "admin"],
                                   key="admin_role_filter")
        if role_filter != "All":
            users = [u for u in users if u.get("role") == role_filter]

        if users:
            u_rows = []
            for u in users:
                u_rows.append({
                    "User ID":         u.get("id"),
                    "Name":            u.get("name"),
                    "Email":           u.get("email"),
                    "Role":            u.get("role", "user").upper(),
                    "Registered":      str(u.get("created_at", ""))[:16],
                })
            df_users = pd.DataFrame(u_rows)
            st.dataframe(df_users, use_container_width=True, hide_index=True)
            st.caption(f"Total: {len(users)} user(s) shown")
        else:
            st.info("No users found.")

        # Summary stats
        st.markdown("---")
        ua, ub = st.columns(2)
        all_u = get_all_users()
        admins = [u for u in all_u if u.get("role") == "admin"]
        regular= [u for u in all_u if u.get("role") == "user"]
        ua.metric("👑 Admin Accounts", len(admins))
        ub.metric("👤 User Accounts",  len(regular))

    # ═══ Tab 4: Carrier Analytics ═════════════════════════════════════════════
    with tab_analytics:
        st.subheader("📈 Carrier Performance Analytics")

        if perf_rows:
            df_perf = pd.DataFrame(perf_rows)
            col_left, col_right = st.columns(2)
            carriers   = [r["Carrier"]          for r in perf_rows]
            on_times   = [r["On-Time Rate (%)"]  for r in perf_rows]
            avg_delays = [r["Avg Delay (min)"]   for r in perf_rows]

            with col_left:
                st.caption("📊 On-Time Delivery Rate (%)")
                st.bar_chart(pd.DataFrame({"Carrier": carriers, "On-Time %": on_times})
                             .set_index("Carrier"))
            with col_right:
                st.caption("⏱ Average Delay (minutes)")
                st.bar_chart(pd.DataFrame({"Carrier": carriers, "Avg Delay": avg_delays})
                             .set_index("Carrier"))

            st.caption("Full Carrier Performance Table")
            st.dataframe(df_perf, use_container_width=True, hide_index=True)

            # Delay risk for live shipments
            st.markdown("---")
            st.subheader("⚠️ Delay Risk — Live Shipments")
            if active:
                drisk = []
                for s in active:
                    dp = predict_delay(
                        tracking_id  = s.get("tracking_id", ""),
                        distance_km  = s.get("total_distance_km", 200),
                        speed_kmph   = s.get("speed_kmph", 60),
                        carrier      = s.get("carrier", "Unknown"),
                        destination  = s.get("destination", "Chennai"),
                        priority     = s.get("priority", "Medium"),
                    )
                    drisk.append({
                        "Tracking ID": s.get("tracking_id"),
                        "Risk":        dp["risk_level"],
                        "Prob":        dp["delay_probability_pct"],
                        "+Min":        dp["predicted_delay_minutes"],
                        "Confidence":  f"{dp['confidence_score']*100:.0f}%",
                        "Reason":      dp["reason"][:55],
                    })
                st.dataframe(pd.DataFrame(drisk), use_container_width=True, hide_index=True)
        else:
            st.info("No carrier analytics available yet.")

    st.markdown("---")
    st.caption("💡 Live simulation updates every 5 seconds. Refresh page for latest positions.")
