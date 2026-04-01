import sys
import os
import certifi
import re
import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
src_path = os.path.join(os.path.dirname(__file__), 'src')
if src_path not in sys.path:
    sys.path.append(src_path)
   
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# ── Core imports ──────────────────────────────────────────────────────────────
import streamlit as st
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from tracking_renderer import render_tracking_output
from src.utils import apply_custom_css, load_lottie_file
from streamlit_lottie import st_lottie
from streamlit_option_menu import option_menu

load_dotenv()

# MUST be first Streamlit call
st.set_page_config(page_title="eShipz AI", layout="wide")

# Apply existing professional CSS (unchanged)
apply_custom_css()

# Animations
lottie_truck = load_lottie_file("assets/animations/truck.json")

# ── MongoDB ───────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    try:
        client = MongoClient(
            os.getenv("MONGODB_URI"),
            tls=True,
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000
        )
        client.admin.command('ping')
        return client.shipment_db
    except Exception:
        return None

db = get_db()

# ── Bootstrap simulation engine (starts background thread once) ───────────────
@st.cache_resource
def _init_simulator(_db):
    from services.simulation_engine import get_simulator
    return get_simulator(db=_db)

sim = _init_simulator(db)

# ── Initialise auth database ──────────────────────────────────────────────────
from auth.database import init_db
init_db()

# ═════════════════════════════════════════════════════════════════════════════
# AUTH GATE — Show login page if not authenticated
# ═════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("authenticated"):
    from auth.login_page import render_auth_page
    render_auth_page()
    st.stop()   # Stop here — nothing below renders until logged in

# ── Logged-in user context ────────────────────────────────────────────────────
_user_role  = st.session_state.get("user_role",  "user")
_user_name  = st.session_state.get("user_name",  "User")
_user_id    = st.session_state.get("user_id",    0)
_user_email = st.session_state.get("user_email", "")

# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st_lottie(lottie_truck, height=120)

    # ── Role-based navigation ─────────────────────────────────────────────────
    if _user_role == "admin":
        nav_options = [
            "Dashboard",
            "New Shipment",
            "History & Tracking",
            "Agent Insights",
            "AI Assistant",
            "Shipment Intelligence",
            "Live Tracking",
            "Admin Dashboard",
        ]
        nav_icons = [
            "grid-1x2", "plus-circle", "clock-history", "cpu",
            "robot", "shield-check", "geo-alt", "display",
        ]
    else:
        # Regular users don't see Admin Dashboard
        nav_options = [
            "Dashboard",
            "New Shipment",
            "History & Tracking",
            "Agent Insights",
            "AI Assistant",
            "Shipment Intelligence",
            "Live Tracking",
        ]
        nav_icons = [
            "grid-1x2", "plus-circle", "clock-history", "cpu",
            "robot", "shield-check", "geo-alt",
        ]

    page = option_menu(
        menu_title="Logistics Command",
        options=nav_options,
        icons=nav_icons,
        menu_icon="cast",
        default_index=0,
        styles={
            "container":         {"padding": "5!important", "background-color": "#16181D"},
            "icon":              {"color": "#625DF5", "font-size": "18px"},
            "nav-link":          {"font-size": "14px", "text-align": "left",
                                  "margin": "5px", "--hover-color": "#2B2E36"},
            "nav-link-selected": {"background-color": "#625DF5"},
        }
    )

    # ── Admin: Pending Assignment Notifications ───────────────────────────────
    if _user_role == "admin":
        from services.notifications import (
            get_admin_pending_count, get_all_admin_notifications,
            mark_admin_notifications_read, assign_carrier, CARRIERS
        )
        pending = get_admin_pending_count()
        badge   = f" ({pending}) 🔴" if pending > 0 else ""

        with st.expander(f"📦 Pending Assignments{badge}", expanded=(pending > 0)):
            if pending > 0:
                if st.button("✔️ Mark all read", key="admin_mark_all_read",
                             use_container_width=True):
                    mark_admin_notifications_read()
                    st.rerun()

            all_notifs = get_all_admin_notifications(limit=10)
            if all_notifs:
                for n in all_notifs:
                    is_pending = not n["is_assigned"]
                    color      = "#625DF5" if is_pending else "#22C55E"
                    ts         = str(n.get("created_at", ""))[:16]
                    dot        = "•" if is_pending else "✓"
                    p_colors   = {"High": "#EF4444", "Medium": "#F59E0B", "Low": "#22C55E"}
                    p_color    = p_colors.get(n["priority"], "#94A3B8")

                    st.markdown(
                        f"<div style='border-left:3px solid {color};"
                        f"padding:6px 10px;margin-bottom:4px;"
                        f"border-radius:0 6px 6px 0;background:{color}18;'>"
                        f"<span style='color:{color};font-weight:700;font-size:0.8rem'>"
                        f"{dot} {n['tracking_id']}</span>"
                        f"<span style='color:#6B7280;font-size:0.7rem;float:right'>{ts}</span><br>"
                        f"<span style='color:#D1D5DB;font-size:0.75rem'>"
                        f"👤 {n['user_name']} │ {n['source']} → {n['destination']}<br>"
                        f"{n['weight']} kg │ <span style='color:{p_color}'>{n['priority']}</span>"
                        + (f" │ 🚚 {n['carrier_assigned']}" if n["carrier_assigned"] else "") +
                        f"</span></div>",
                        unsafe_allow_html=True
                    )

                    if is_pending:
                        col_sel, col_btn = st.columns([3, 1])
                        with col_sel:
                            chosen = st.selectbox(
                                "Partner",
                                CARRIERS,
                                key=f"carrier_sel_{n['id']}",
                                label_visibility="collapsed"
                            )
                        with col_btn:
                            if st.button("✔ Assign",
                                         key=f"assign_btn_{n['id']}",
                                         use_container_width=True):
                                ok = assign_carrier(
                                    notif_id    = n["id"],
                                    tracking_id = n["tracking_id"],
                                    carrier     = chosen,
                                )
                                if ok:
                                    st.success(f"✅ {chosen} → {n['tracking_id']}")
                                    st.rerun()
            else:
                st.caption("📢 No new shipments to assign.")

    # ── User: Status Notification Bell ────────────────────────────────────────
    if _user_role == "user" and _user_id:
        from services.notifications import (
            get_unread_count, get_all_notifications,
            mark_all_read, get_status_color
        )
        unread = get_unread_count(_user_id)
        badge  = f" ({unread}) 🔴" if unread > 0 else ""

        with st.expander(f"🔔 Notifications{badge}", expanded=(unread > 0)):
            notifs = get_all_notifications(_user_id, limit=8)
            if notifs:
                if unread > 0:
                    if st.button("✔️ Mark all read", key="mark_all_read_btn",
                                 use_container_width=True):
                        mark_all_read(_user_id)
                        st.rerun()
                for n in notifs:
                    color   = get_status_color(n["new_status"])
                    opacity = "1" if not n["is_read"] else "0.55"
                    ts      = str(n.get("created_at", ""))[:16]
                    dot     = "•" if not n["is_read"] else ""
                    st.markdown(
                        f"<div style='border-left:3px solid {color};"
                        f"padding:6px 10px;margin-bottom:6px;"
                        f"border-radius:0 6px 6px 0;"
                        f"background:{color}18;opacity:{opacity};'>"
                        f"<span style='color:{color};font-weight:700;font-size:0.8rem'>"
                        f"{dot} {n['new_status']}</span>"
                        f"<span style='color:#6B7280;font-size:0.7rem;float:right'>{ts}</span>"
                        f"<br><span style='color:#D1D5DB;font-size:0.78rem'>"
                        f"{n['message'].replace('**','')}</span></div>",
                        unsafe_allow_html=True
                    )
            else:
                st.caption("📢 No notifications yet.")

    # ── User identity + logout ────────────────────────────────────────────────
    st.markdown("---")
    role_badge = "👑 Admin" if _user_role == "admin" else "👤 User"
    st.markdown(
        f"<div style='color:#94A3B8;font-size:0.8rem;padding:4px 8px;'>"
        f"{role_badge} · <b style='color:#D1D5DB'>{_user_name}</b></div>",
        unsafe_allow_html=True
    )
    if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
        for k in ["authenticated", "user_id", "user_name", "user_email", "user_role"]:
            st.session_state.pop(k, None)
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 1: DASHBOARD  (unchanged visual; add user-specific context)
# ═════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    st.title("Logistics Command Center")

    from auth.auth_service import get_user_shipments, get_shipment_stats, get_user_count
    total_count = 0

    if db is not None:
        try:
            total_count = db.history.count_documents({})
        except Exception:
            total_count = "Error"
    else:
        total_count = "Offline"

    active_sim = len([s for s in sim.get_all_active() if s.get("status") != "Delivered"])

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("Total Shipments", total_count)
    with col_b:
        st.metric("Active Agents", "5")
    with col_c:
        st.metric("🚚 Live Tracking", active_sim)
    with col_d:
        st.metric("System Status",
                  "Ready" if db is not None else "Offline",
                  delta="Healthy" if db is not None else "SSL Issue",
                  delta_color="normal" if db is not None else "inverse")

    st.markdown("---")

    if _user_role == "admin":
        # Admin sees platform-wide stats
        stats = get_shipment_stats()
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("📦 DB Shipments",    stats.get("total", 0))
        col_s2.metric("👥 Registered Users", get_user_count())
        col_s3.metric("🚚 Active Simulations", active_sim)
        st.caption("👑 Admin view — showing platform-wide data")
    else:
        # User sees their own shipments
        my_ships = get_user_shipments(_user_id)
        if my_ships:
            st.subheader("📦 My Recent Shipments")
            rows = [{"Route": f"{s.get('source','?')} → {s.get('destination','?')}",
                     "Status": s.get("status",""),
                     "Tracking ID": s.get("tracking_id",""),
                     "Booked At": str(s.get("created_at",""))[:16]} for s in my_ships[:5]]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("You haven't booked any shipments yet. Go to **New Shipment** to get started!")

    st.subheader("Recent Platform Activity")
    if db is not None:
        try:
            recent_data = list(db.history.find().sort("timestamp", -1).limit(5))
            if recent_data:
                df = pd.DataFrame([
                    {"Time":   r['timestamp'].strftime("%H:%M:%S"),
                     "Route":  f"{r['details']['source']} ➔ {r['details']['destination']}",
                     "Status": r['status']} for r in recent_data
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No recent shipments found.")
        except Exception as e:
            st.error(f"Could not load activity: {e}")
    else:
        st.warning("Database is offline. Please check your MongoDB connection.")

# ═════════════════════════════════════════════════════════════════════════════
# PAGE 2: NEW SHIPMENT
# ═════════════════════════════════════════════════════════════════════════════
elif page == "New Shipment":
    from auth.auth_service import save_user_shipment

    st.title("AI-Powered Shipment Booking")
    st.write("Enter details to trigger the Multi-Agent orchestration.")

    with st.container(border=True):
        col_a, col_b = st.columns(2)
        with col_a:
            source = st.text_input("Source City", placeholder="e.g. Delhi", key="ns_source")
            dest   = st.text_input("Destination City", placeholder="e.g. Mumbai", key="ns_dest")
        with col_b:
            weight   = st.number_input("Weight (kg)", min_value=0.1, step=0.1)
            priority = st.selectbox("Priority Level", ["Low", "Medium", "High"])

        process_btn = st.button("🔥 Process Shipment", use_container_width=True)


    if process_btn:
        source = source.strip()
        dest   = dest.strip()
        if not source or not dest:
            st.warning("Please enter both Source and Destination cities.")
        elif source.lower() == dest.lower():
            st.warning("Source and Destination cannot be the same city.")
        else:
            with st.status("⚡ Processing shipment...", expanded=True) as status:
                try:
                    from services.single_shot_processor import process_shipment_single_shot
                    from auth.auth_service import save_user_shipment

                    st.write("📊 Analyzing carrier performance...")
                    st.write("🗺️ Computing optimal India route...")
                    st.write("📦 Generating AWB & barcode...")

                    result = process_shipment_single_shot(
                        source=source,
                        destination=dest,
                        weight=weight,
                        priority=priority,
                        user_id=_user_id,
                        db=db,
                    )

                    awb         = result["awb"]
                    tracking_id = result["tracking_id"]

                    # ── Save to MongoDB ────────────────────────────────────────
                    if db is not None:
                        try:
                            db.history.insert_one({
                                "timestamp":    datetime.datetime.utcnow(),
                                "details": {
                                    "source":      source,
                                    "destination": dest,
                                    "weight":      weight,
                                    "priority":    priority,
                                    "carrier":     "Pending",
                                },
                                "user_id":      _user_id,
                                "user_name":    _user_name,
                                "agent_output": result["report"][:500],
                                "status":       "Pending",
                            })
                            st.toast("✅ Saved to MongoDB Atlas")
                        except Exception:
                            pass

                    # ── Save to SQLite user shipments ──────────────────────────
                    save_user_shipment(
                        tracking_id  = tracking_id,
                        user_id      = _user_id,
                        source       = source,
                        destination  = dest,
                        weight       = weight,
                        priority     = priority,
                        carrier      = "Pending",
                        agent_output = result["report"][:500],
                        user_name    = _user_name,
                        awb          = result.get("awb", ""),
                    )

                    # ── Notify user: shipment booked, awaiting carrier ─────────
                    try:
                        from services.notifications import (
                            create_notification, create_admin_notification
                        )
                        create_notification(
                            user_id     = _user_id,
                            tracking_id = tracking_id,
                            new_status  = "Created",
                            old_status  = "",
                        )
                        create_admin_notification(
                            tracking_id = tracking_id,
                            user_id     = _user_id,
                            user_name   = _user_name,
                            source      = source,
                            destination = dest,
                            weight      = weight,
                            priority    = priority,
                        )
                    except Exception:
                        pass

                    st.session_state["last_tracking_id"] = tracking_id
                    status.update(
                        label="✅ Shipment Booked — Awaiting Carrier Assignment",
                        state="complete"
                    )

                    # ── Display results ────────────────────────────────────────
                    st.success("🎉 Shipment Booked Successfully!")

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("🚚 Carrier",     "Pending Assignment")
                    c2.metric("📋 AWB",         awb)
                    c3.metric("📍 Tracking ID", tracking_id)
                    c4.metric("🗺️ Route km",    f"{result['dist_km']:.0f} km")

                    st.warning(
                        "📦 **Delivery Partner:** Awaiting assignment by Admin. "
                        "You will be notified once a carrier is assigned to your shipment."
                    )

                    st.markdown(result["report"])
                    st.caption(result["barcode_msg"])
                    st.info(
                        f"📡 Your live tracking ID: **{tracking_id}** — "
                        f"go to **Live Tracking** and enter it to see your shipment on the India map."
                    )
                    api_badge = "1 API call" if result["used_api"] else "0 API calls (rule-based)"
                    st.caption(f"💡 Processing used: **{api_badge}** — quota efficient ✅")

                except Exception as e:
                    status.update(label="❌ Error occurred", state="error")
                    st.error(f"Processing failed: {e}")

# ═════════════════════════════════════════════════════════════════════════════
# PAGE 3: HISTORY & TRACKING
# Drop-in replacement for the existing elif page == "History & Tracking": block
# ═════════════════════════════════════════════════════════════════════════════
elif page == "History & Tracking":
    import json

    st.markdown("""
    <style>
    .track-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
        border-radius: 14px; padding: 24px 30px; margin-bottom: 22px; color: white;
    }
    .track-header h2 { margin:0; font-size:1.6rem; font-weight:700; }
    .track-header p  { margin:4px 0 0; opacity:.7; font-size:.9rem; }
    .info-grid {
        display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
        gap:12px; margin:16px 0;
    }
    .info-cell {
        background:#fff; border:1px solid #e8edf5; border-radius:10px;
        padding:12px 16px;
    }
    .info-cell .lbl { font-size:.7rem; color:#888; text-transform:uppercase; letter-spacing:.5px; }
    .info-cell .val { font-size:.95rem; font-weight:600; color:#1a1a2e; margin-top:3px; }
    .badge-exception { background:#fff0f0;color:#c0392b;border:1px solid #f5c6c6; border-radius:20px; padding:3px 12px; font-size:.8rem; font-weight:600; }
    .badge-delivered { background:#f0fff4;color:#27ae60;border:1px solid #b2e5c4; border-radius:20px; padding:3px 12px; font-size:.8rem; font-weight:600; }
    .badge-transit   { background:#fffbf0;color:#e67e22;border:1px solid #f5e6b2; border-radius:20px; padding:3px 12px; font-size:.8rem; font-weight:600; }
    .badge-default   { background:#f5f5f5;color:#555;border:1px solid #ddd;       border-radius:20px; padding:3px 12px; font-size:.8rem; font-weight:600; }
    .chk-table { width:100%; border-collapse:collapse; font-size:.85rem; margin-top:8px; }
    .chk-table th { background:#1a1a2e; color:#fff; padding:9px 14px; text-align:left; font-weight:600; }
    .chk-table td { padding:8px 14px; border-bottom:1px solid #f0f2f7; vertical-align:top; }
    .chk-table tr:nth-child(even) td { background:#f8faff; }
    .chk-table tr:hover td { background:#eef2ff; }
    .dot-ex  { color:#c0392b; font-weight:700; margin-right:4px; }
    .dot-ok  { color:#27ae60; font-weight:700; margin-right:4px; }
    .dot-neu { color:#aaa;    font-weight:700; margin-right:4px; }
    .sample-chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
    .chip { background:#1a1a2e; color:#ccc; border-radius:6px; padding:3px 10px; font-size:.78rem; font-family:monospace; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="track-header">
      <h2>📦 History &amp; Tracking</h2>
      <p>Live eShipz V2 search · real-time checkpoints · database ledger</p>
    </div>
    """, unsafe_allow_html=True)

    # ── LIVE API SEARCH BAR ───────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 🛰️ Live API Search")
        col_inp, col_btn = st.columns([5, 1])
        with col_inp:
            live_track_id = st.text_input(
                "Tracking ID",
                placeholder="e.g. 90001605035  ·  SRSC7181962693  ·  233109462  ·  80970274836",
                label_visibility="collapsed",
                key="ht_live_input",
            )
        with col_btn:
            search_trigger = st.button(
                "🛰️ Search", use_container_width=True, key="ht_search_btn"
            )

        st.markdown("""
        <div class="sample-chips">
          <span class="chip">90001605035</span>
          <span class="chip">SRSC7181962693</span>
          <span class="chip">233109462</span>
          <span class="chip">80970274836</span>
        </div>
        """, unsafe_allow_html=True)

    # ── HELPER: badge + dot ───────────────────────────────────────────────────
    def _badge(status: str) -> str:
        s = (status or "").lower()
        if any(x in s for x in ("exception", "failed", "undeliver", "rto")):
            return f'<span class="badge-exception">⚠ {status}</span>'
        if "delivered" in s:
            return f'<span class="badge-delivered">✓ {status}</span>'
        if any(x in s for x in ("transit", "pickup", "out for", "dispatch")):
            return f'<span class="badge-transit">→ {status}</span>'
        return f'<span class="badge-default">{status}</span>'

    def _dot(status: str) -> str:
        s = (status or "").lower()
        if any(x in s for x in ("exception", "failed", "rto", "undeliver")):
            return '<span class="dot-ex">●</span>'
        if "delivered" in s:
            return '<span class="dot-ok">●</span>'
        return '<span class="dot-neu">●</span>'

    def _fmt(raw) -> str:
        import datetime as _dt
        raw = str(raw or "").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                    "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d %b %Y %H:%M:%S"):
            try:
                return _dt.datetime.strptime(raw, fmt).strftime("%d %b %Y  %H:%M")
            except Exception:
                pass
        return raw or "—"

    # ── LIVE SEARCH RESULT ────────────────────────────────────────────────────
    if search_trigger and live_track_id.strip():
        tid = live_track_id.strip()
        from shipment.tools.tool_serve import track_shipment_eshipz

        with st.spinner(f"Connecting to eShipz Gateway for **{tid}** …"):
            raw_response = track_shipment_eshipz(tid)

        # ── Config / network errors ───────────────────────────────────────────
        if raw_response.startswith("Configuration Error") or \
           raw_response.startswith("Network Error") or \
           raw_response.startswith("Server Alert"):
            st.error(f"⚙️ {raw_response}")

        elif "No records found" in raw_response:
            st.warning(f"📭 {raw_response}")

        else:
            try:
                data = json.loads(raw_response)

                # Normalise to list
                if isinstance(data, dict):
                    for k in ("data", "result", "results", "trackings", "shipments"):
                        if k in data and isinstance(data[k], list):
                            data = data[k]
                            break
                    else:
                        data = [data]

                if not isinstance(data, list) or not data:
                    st.warning("No shipment records in the API response.")
                else:
                    st.success(f"✅ {len(data)} record(s) retrieved for **{tid}**")

                    for idx, shipment in enumerate(data):
                        if len(data) > 1:
                            st.markdown(f"---\n**Shipment {idx + 1}**")

                        # ── Field extraction (handles AfterShip + eShipz keys) ──
                        status   = (shipment.get("tag") or shipment.get("status")
                                    or shipment.get("current_status") or "—")
                        carrier  = (shipment.get("slug") or shipment.get("carrier_name")
                                    or shipment.get("carrier") or shipment.get("courier_name") or "—")
                        origin   = (shipment.get("origin_country_iso3")
                                    or shipment.get("origin") or shipment.get("from") or "—")
                        dest     = (shipment.get("destination_country_iso3")
                                    or shipment.get("destination") or shipment.get("to") or "—")
                        order_id = (shipment.get("order_id") or shipment.get("reference_id") or "—")
                        awb      = (shipment.get("awb") or shipment.get("tracking_number")
                                    or shipment.get("awb_number") or tid)
                        updated  = _fmt(shipment.get("updated_at") or shipment.get("last_update") or "")

                        # ── Info row ──────────────────────────────────────────
                        st.markdown(
                            f"**AWB / ID:** `{awb}` &nbsp; {_badge(status)}",
                            unsafe_allow_html=True,
                        )
                        st.markdown(f"""
                        <div class="info-grid">
                          <div class="info-cell"><div class="lbl">Carrier</div>
                            <div class="val">{carrier.upper()}</div></div>
                          <div class="info-cell"><div class="lbl">Status</div>
                            <div class="val">{status}</div></div>
                          <div class="info-cell"><div class="lbl">Origin</div>
                            <div class="val">{origin}</div></div>
                          <div class="info-cell"><div class="lbl">Destination</div>
                            <div class="val">{dest}</div></div>
                          <div class="info-cell"><div class="lbl">Order ID</div>
                            <div class="val">{order_id}</div></div>
                          <div class="info-cell"><div class="lbl">Last Updated</div>
                            <div class="val">{updated}</div></div>
                        </div>
                        """, unsafe_allow_html=True)

                        # ── Checkpoints table ─────────────────────────────────
                        checkpoints = (
                            shipment.get("checkpoints")
                            or shipment.get("tracking_events")
                            or shipment.get("events")
                            or shipment.get("scans")
                            or []
                        )

                        if checkpoints:
                            st.markdown(f"**{len(checkpoints)} Checkpoints**")
                            rows = ""
                            for cp in checkpoints:
                                cp_status = (cp.get("tag") or cp.get("status")
                                             or cp.get("activity") or cp.get("event") or "—")
                                cp_loc    = (cp.get("city") or cp.get("location")
                                             or cp.get("place") or "—")
                                cp_dt     = _fmt(cp.get("checkpoint_time")
                                                 or cp.get("timestamp")
                                                 or cp.get("date") or "")
                                cp_msg    = (cp.get("message") or cp.get("remark")
                                             or cp.get("description") or cp.get("remarks") or "")
                                rows += (
                                    f"<tr><td>{_dot(cp_status)}{cp_status}</td>"
                                    f"<td>{cp_loc}</td>"
                                    f"<td>{cp_dt}</td>"
                                    f"<td>{cp_msg}</td></tr>"
                                )

                            st.markdown(f"""
                            <table class="chk-table">
                              <thead>
                                <tr>
                                  <th style="width:22%">Status</th>
                                  <th style="width:18%">Location</th>
                                  <th style="width:18%">Date &amp; Time</th>
                                  <th>Details</th>
                                </tr>
                              </thead>
                              <tbody>{rows}</tbody>
                            </table>
                            """, unsafe_allow_html=True)
                        else:
                            st.info("No checkpoint events in this record.")

                        with st.expander("🛠 Raw JSON (debug)"):
                            st.json(shipment)

            except json.JSONDecodeError:
                st.error(f"Could not parse API response as JSON:\n\n{raw_response}")

    elif search_trigger:
        st.warning("Please enter a tracking ID before searching.")

    # ── DATABASE LEDGER ───────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📜 Shipment Ledger (Database Records)")
    if _user_role == "admin":
        st.caption("Admin view — all shipments in MongoDB.")
    else:
        st.caption("Your shipment history from MongoDB.")

    if db is not None:
        search_db = st.text_input("Filter Ledger by Destination", key="ht_db_filter")
        query = {} if _user_role == "admin" else {"user_id": _user_id}
        if search_db:
            query["details.destination"] = {"$regex": search_db, "$options": "i"}

        history = list(db.history.find(query).sort("timestamp", -1))

        if history:
            for item in history:
                ts  = item["timestamp"].strftime("%Y-%m-%d %H:%M")
                tid = item.get("tracking_id", "Unknown")
                with st.expander(f"📦 {tid}  |  {ts}"):
                    d = item.get("details", {})
                    st.write(f"**Route:** {d.get('source','?')} → {d.get('destination','?')}")
                    st.write(f"**Status:** {item.get('status', 'Pending')}")
                    st.info(f"**Agent Decision:**\n{item.get('agent_output', '—')}")
        else:
            st.info("No records found in the database.")
    else:
        st.warning("Database is offline — cannot load ledger.")
# ═════════════════════════════════════════════════════════════════════════════
# PAGE 4: AGENT INSIGHTS (unchanged)
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Agent Insights":
    st.title("Agent Intelligence Profiles")
    st.write("Understand the roles of your autonomous workers.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("🕵️ Planner")
        st.write("Selects carriers based on cost, weight, and distance.")
    with col2:
        st.subheader("📝 Booker")
        st.write("Generates AWBs and triggers Barcode tools.")
    with col3:
        st.subheader("📡 Tracker")
        st.write("Real-time GPS tracking via MCP tools. Predicts delays.")

    col4, col5 = st.columns(2)
    with col4:
        st.subheader("🛡️ Supervisor")
        st.write("Monitors bulk shipments by date range. Filters exceptions & returns.")
    with col5:
        st.subheader("🔍 Intelligence")
        st.write("Deep per-shipment analysis: delay, stuck, risk, and movement discrepancy detection.")

    st.markdown("---")
    st.subheader("System Architecture")
    st.code("""
    Frontend:       Streamlit (UI)
    Orchestration:  CrewAI (Agent Framework)
    Intelligence:   Groq LLaMA-3.3-70B (LLM)
    Tracking:       MCP Server (FastMCP)
    Simulation:     Real-time GPS Engine (5-sec ticks)
    Database:       MongoDB Atlas + SQLite (Auth)
    Auth:           SHA-256 + Salt · Session-based
    Analytics:      Carrier Performance + Delay AI
    Visualization:  Leaflet.js (Dark Map)
    Tools:          Python Barcode & Network Ping
    Agents:         5 (Planner, Booker, Tracker, Supervisor, Intelligence)
    """)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 5: AI ASSISTANT  — Calls CrewAI + renders live eShipz checkpoint table
# ═════════════════════════════════════════════════════════════════════════════
elif page == "AI Assistant":
    import sys as _sys
    import os as _os

    # Make sure src/ is on sys.path so 'from shipment.main import run' works
    _src = _os.path.join(_os.path.dirname(__file__), "src")
    if _src not in _sys.path:
        _sys.path.insert(0, _src)

    st.markdown("""
    <style>
    .ai-header{
        background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);
        border-radius:14px;padding:24px 30px;margin-bottom:22px;color:white;
    }
    .ai-header h2{margin:0;font-size:1.6rem;font-weight:700;}
    .ai-header p{margin:4px 0 0;opacity:.7;font-size:.9rem;}
    .step-info{background:#12141b;border:1px solid #334155;border-radius:9px;
               padding:12px 18px;margin:12px 0;font-size:.85rem;color:#94a3b8;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="ai-header">
      <h2>🤖 AI Tracking Assistant</h2>
      <p>Multi-agent CrewAI analysis · Live eShipz V2 API · Checkpoint Intelligence</p>
    </div>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("#### 🛰️ Enter Tracking ID for AI Analysis")
        st.caption("The AI agent will call the live eShipz API and return a full checkpoint report.")
        col_inp2, col_btn2 = st.columns([5, 1])
        with col_inp2:
            ai_track_id = st.text_input(
                "Tracking ID",
                value="80970274836",
                placeholder="e.g. 80970274836",
                label_visibility="collapsed",
                key="ai_track_input",
            )
        with col_btn2:
            ai_run_btn = st.button(
                "🤖 Run", use_container_width=True, key="ai_run_btn"
            )

        st.markdown("""
        <div class="step-info">
          <b>How it works:</b>&nbsp;
          Planner → picks carrier &amp; route &nbsp;|&nbsp;
          Booker → generates AWB &nbsp;|&nbsp;
          Tracker → calls eShipz API &amp; returns live checkpoints
        </div>
        """, unsafe_allow_html=True)

    if ai_run_btn:
        tid = (ai_track_id or "").strip()
        if not tid:
            st.warning("Please enter a tracking ID before running.")
        else:
            with st.status(f"🤖 AI agents analysing **{tid}** …", expanded=True) as _ai_status:
                st.write("🧠 Planning agent — selecting optimal carrier & route …")
                st.write("📦 Booking agent — generating AWB number …")
                st.write("🛰️ Tracking agent — calling eShipz V2 API …")
                try:
                    from shipment.main import run as _crew_run
                    _result = _crew_run(tracking_id=tid)
                    _ai_status.update(
                        label="✅ AI Analysis Complete",
                        state="complete",
                        expanded=False,
                    )
                except Exception as _e:
                    _ai_status.update(label="❌ Error", state="error")
                    st.error(f"CrewAI Orchestration Error: {_e}")
                    _result = None

            if _result is not None:
                # ── Token usage row ───────────────────────────────────────────
                try:
                    _tu = _result.token_usage
                    _mc1, _mc2, _mc3, _mc4 = st.columns(4)
                    _mc1.metric("🔢 Total Tokens",      f"{_tu.total_tokens:,}")
                    _mc2.metric("📤 Prompt Tokens",     f"{_tu.prompt_tokens:,}")
                    _mc3.metric("📥 Completion Tokens", f"{_tu.completion_tokens:,}")
                    _mc4.metric("🔄 API Calls",         _tu.successful_requests)
                except Exception:
                    pass

                # ── Agent decision cards (Planner + Booker only) ──────────────
                try:
                    _tasks = _result.tasks_output or []
                    if _tasks:
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
                        _card_meta = {
                            "carrier_selection_task": "🧠 Planner — Carrier Recommendation",
                            "booking_task":           "📦 Booker — AWB & Barcode",
                        }
                        for _to in _tasks:
                            if _to.name not in _card_meta:
                                continue   # skip tracking task — table shows it
                            _heading = _card_meta[_to.name]
                            _body = (_to.raw or "").strip()
                            if len(_body) > 420:
                                _body = _body[:420] + " …"
                            st.markdown(
                                f'<div class="agent-card">'
                                f'<div class="ac-label">{_heading}</div>'
                                f'<div class="ac-agent">Agent: {(_to.agent or "").strip()}</div>'
                                f'<div class="ac-body">{_body}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                except Exception:
                    pass

                # ── Checkpoint table ───────────────────────────────────────────
                st.markdown("---")
                st.subheader("📍 Live Checkpoint Intelligence")
                render_tracking_output(_result)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE 6: SHIPMENT INTELLIGENCE (NEW — Agent 4 + Agent 5)
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Shipment Intelligence":
    import json as _json
    import datetime as _dt

    st.markdown("""
    <style>
    .intel-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #312e81 100%);
        border-radius: 14px; padding: 28px 32px; margin-bottom: 24px; color: white;
    }
    .intel-header h2 { margin:0; font-size:1.7rem; font-weight:800;
        background: linear-gradient(90deg, #a78bfa, #818cf8, #6366f1);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .intel-header p { margin:6px 0 0; opacity:.7; font-size:.9rem; color:#c4b5fd; }
    .intel-card {
        background: #12141b; border: 1px solid #1e2235; border-radius: 12px;
        padding: 18px 22px; margin-bottom: 14px;
        transition: border-color 0.2s;
    }
    .intel-card:hover { border-color: #6366f1; }
    .intel-card .ic-title { font-size: .85rem; font-weight: 700; color: #e2e8f0; margin-bottom: 8px; }
    .intel-card .ic-issues { font-size: .8rem; color: #94a3b8; line-height: 1.6; }
    .intel-card .ic-issues li { margin-bottom: 3px; }
    .status-pill {
        display: inline-block; padding: 4px 14px; border-radius: 20px;
        font-size: .78rem; font-weight: 700; margin-right: 8px;
    }
    .pill-ontime    { background: #064e3b; color: #6ee7b7; border: 1px solid #34d399; }
    .pill-delayed   { background: #78350f; color: #fcd34d; border: 1px solid #fbbf24; }
    .pill-stuck     { background: #1e3a5f; color: #93c5fd; border: 1px solid #60a5fa; }
    .pill-highrisk  { background: #450a0a; color: #fca5a5; border: 1px solid #f87171; }
    .intel-metric-row {
        display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0;
    }
    .intel-metric {
        background: #1a1f2d; border: 1px solid #334155; border-radius: 10px;
        padding: 14px 20px; flex: 1; min-width: 140px; text-align: center;
    }
    .intel-metric .im-val { font-size: 1.4rem; font-weight: 800; color: #e2e8f0; }
    .intel-metric .im-lbl { font-size: .7rem; color: #64748b; text-transform: uppercase;
        letter-spacing: .5px; margin-top: 4px; }
    .prediction-box {
        background: #1a1f2d; border-left: 3px solid #818cf8; border-radius: 0 10px 10px 0;
        padding: 12px 18px; margin: 8px 0; font-size: .85rem; color: #c4b5fd;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="intel-header">
      <h2>🛡️ Shipment Intelligence Center</h2>
      <p>Agent 4: Logistics Supervisor · Agent 5: Shipment Intelligence Analyst · Proactive Risk Detection</p>
    </div>
    """, unsafe_allow_html=True)

    def _status_pill(status):
        s = (status or "").lower()
        if "high risk" in s:
            return f'<span class="status-pill pill-highrisk">🔴 {status}</span>'
        if "stuck" in s:
            return f'<span class="status-pill pill-stuck">🟠 {status}</span>'
        if "delayed" in s:
            return f'<span class="status-pill pill-delayed">🟡 {status}</span>'
        return f'<span class="status-pill pill-ontime">🟢 {status}</span>'

    def _status_emoji(s):
        s_lower = (s or "").lower()
        if "high risk" in s_lower:
            return "🔴 High Risk"
        if "stuck" in s_lower:
            return "🧊 Stuck"
        if "delayed" in s_lower:
            return "⏱ Delayed"
        if "unavailable" in s_lower:
            return "⚫ Data Unavailable"
        return "🟢 On-Time"

    # ── Mode tabs ─────────────────────────────────────────────────────────────
    intel_tab1, intel_tab2 = st.tabs([
        "📅 Date Range Scan",
        "🔍 Single Tracking Analysis",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1: Date Range Scan
    # SQLite → booking list only (AWB + route + date, NO status)
    # eShipz API → live status + analysis per AWB
    # ══════════════════════════════════════════════════════════════════════════
    with intel_tab1:
        st.markdown("#### 📅 Date Range Shipment Monitor")
        st.info(
            "Select a date range to view shipments booked in your system. "
            "Live tracking status is fetched from the **eShipz API** for each AWB. "
            "Shipments not yet registered with eShipz will show as **Pending**."
        )

        with st.container(border=True):
            col_d1, col_d2, col_dbtn = st.columns([2, 2, 1])
            with col_d1:
                dr_min = st.date_input(
                    "From Date",
                    value=_dt.date.today() - _dt.timedelta(days=30),
                    key="dr_min_date",
                )
            with col_d2:
                dr_max = st.date_input(
                    "To Date",
                    value=_dt.date.today(),
                    key="dr_max_date",
                )
            with col_dbtn:
                st.markdown("<br>", unsafe_allow_html=True)
                dr_scan_btn = st.button("🔍 Scan", use_container_width=True, key="dr_scan_btn")

        if dr_scan_btn:
            min_str = dr_min.strftime("%Y-%m-%d")
            max_str = dr_max.strftime("%Y-%m-%d")

            with st.status(f"📅 Scanning {min_str} → {max_str} …", expanded=True) as _dr_status:
                try:
                    from shipment.tools.tool_serve import (
                        fetch_shipments_by_date_direct, _run_analysis_pure
                    )

                    # Step 1: fetch shipment list directly from eShipz API
                    st.write("🛰️ **Step 1:** Calling eShipz `get-shipments` API…")
                    api_result = fetch_shipments_by_date_direct(min_str, max_str, limit=100)

                    if api_result["error"]:
                        raise ValueError(api_result["error"])

                    ships = api_result["shipments"]
                    st.write(f"✅ eShipz returned **{len(ships)}** shipment(s).")

                    # Step 2: run analysis on each shipment
                    st.write("🔍 **Step 2:** Running delay / stuck / risk analysis…")
                    _dr_results = []
                    for ship in ships:
                        # v1 field names
                        awb_val = (ship.get("awb") or ship.get("awb_number") or "—").strip()

                        # origin / destination from order_details nested structure
                        order_details = ship.get("order_details") or {}
                        sender   = order_details.get("sender_address") or {}
                        receiver = order_details.get("receiver_address") or {}
                        origin      = sender.get("city") or sender.get("state") or "—"
                        destination = receiver.get("city") or receiver.get("state") or "—"

                        carrier = (
                            ship.get("vendor_display_name") or ship.get("slug") or
                            ship.get("carrier_name") or "—"
                        )
                        order_id    = ship.get("order_id") or awb_val
                        created_raw = ship.get("creation_date") or ""
                        created_str = str(created_raw)[:16] if created_raw else "—"

                        # fetch live checkpoints via tracking API
                        from shipment.tools.tool_serve import _fetch_tracking_direct
                        td = _fetch_tracking_direct(awb_val) if awb_val != "—" else None
                        if td:
                            obj = td[0] if isinstance(td, list) and td else td
                            # merge tracking data into ship for analysis
                            ship = {**ship, **obj}

                        analysis = _run_analysis_pure(ship)

                        _dr_results.append({
                            "awb":         awb_val,
                            "order_id":    order_id,
                            "carrier":     carrier,
                            "origin":      origin,
                            "destination": destination,
                            "created":     created_str,
                            "live_status": analysis["status"],
                            "current_tag": analysis["current_tag"],
                            "checkpoints": analysis["total_checkpoints"],
                            "last_update": analysis["last_movement_time"] or "—",
                            "delay_days":  analysis["delay_days"],
                            "failed_att":  analysis["failed_attempts"],
                            "issues":      analysis["issues"],
                            "prediction":  analysis["prediction"],
                            "explanation": analysis["explanation"],
                            "repeated_hubs": analysis["repeated_hubs"],
                            "is_delayed":  analysis["is_delayed"],
                            "is_stuck":    analysis["is_stuck"],
                            "is_high_risk":analysis["is_high_risk"],
                        })

                    st.session_state["_dr_results"] = _dr_results
                    st.session_state["_dr_label"]   = f"{min_str} → {max_str}"
                    _dr_status.update(label="✅ Scan Complete", state="complete")

                except Exception as _dr_ex:
                    _dr_status.update(label="❌ Error", state="error")
                    st.error(f"Scan error: {_dr_ex}")
                    st.session_state.pop("_dr_results", None)

        # ── Render results ────────────────────────────────────────────────────
        _dr_res   = st.session_state.get("_dr_results")
        _dr_label = st.session_state.get("_dr_label", "")

        if "_dr_results" in st.session_state:
            if not _dr_res:
                st.info(f"No shipments found for {_dr_label}.")
            else:
                _delayed_c  = sum(1 for r in _dr_res if r["live_status"] == "Delayed")
                _stuck_c    = sum(1 for r in _dr_res if r["live_status"] == "Stuck")
                _risk_c     = sum(1 for r in _dr_res if r["live_status"] == "High Risk")
                _ontime_c   = sum(1 for r in _dr_res if r["live_status"] == "On-Time")

                st.markdown("---")
                st.markdown(f"##### 📊 Results — {_dr_label}")
                sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                sc1.metric("📦 Total",      len(_dr_res))
                sc2.metric("� On-Time",    _ontime_c)
                sc3.metric("⏱ Delayed",    _delayed_c)
                sc4.metric("🧊 Stuck",      _stuck_c)
                sc5.metric("🔴 High Risk",  _risk_c)

                st.markdown("---")
                _dr_filter = st.selectbox(
                    "Filter by Status",
                    ["All", "On-Time", "Delayed", "Stuck", "High Risk"],
                    key="dr_status_filter",
                )
                _dr_filtered = _dr_res if _dr_filter == "All" else [
                    r for r in _dr_res if r["live_status"] == _dr_filter
                ]

                st.markdown(f"#### 📋 Shipments ({len(_dr_filtered)} shown)")
                if _dr_filtered:
                    _tbl = []
                    for r in _dr_filtered:
                        _tbl.append({
                            "AWB":         r["awb"],
                            "Order ID":    r["order_id"],
                            "Carrier":     r["carrier"],
                            "Origin":      r["origin"],
                            "Destination": r["destination"],
                            "Created":     r["created"],
                            "Status":      _status_emoji(r["live_status"]),
                            "Checkpoints": r["checkpoints"],
                            "Last Update": r["last_update"],
                            "Issues":      "; ".join(r["issues"]) if r["issues"] else "—",
                        })
                    st.dataframe(
                        pd.DataFrame(_tbl),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Issues": st.column_config.TextColumn("Issues", width="large"),
                        },
                    )
                else:
                    st.info(f"No shipments match filter: **{_dr_filter}**")

                st.markdown("---")
                st.markdown("#### 🔍 Detailed Analysis")
                for r in _dr_filtered:
                    _exp_lbl = f"{_status_emoji(r['live_status'])} | {r['awb']} | {r['origin']} → {r['destination']}"
                    with st.expander(_exp_lbl, expanded=False):
                        _ec1, _ec2, _ec3, _ec4 = st.columns(4)
                        _ec1.metric("Delay",           f"{r['delay_days']}d")
                        _ec2.metric("Failed Attempts",  r["failed_att"])
                        _ec3.metric("Checkpoints",      r["checkpoints"])
                        _ec4.metric("Last Update",      r["last_update"])

                        if r["repeated_hubs"]:
                            st.warning(f"🔁 Repeated hubs: **{', '.join(r['repeated_hubs'])}**")

                        if r["issues"]:
                            st.markdown("**Issues:**")
                            for iss in r["issues"]:
                                st.markdown(f"- {iss}")

                        st.markdown(f"""
                        <div class="prediction-box">
                          <strong>🔮 Prediction:</strong> {r['prediction']}<br>
                          <strong>💡 Explanation:</strong> {r['explanation']}
                        </div>
                        """, unsafe_allow_html=True)

                        if r["current_tag"]:
                            st.caption(f"Carrier status tag: `{r['current_tag']}`")

                if not (_delayed_c + _stuck_c + _risk_c):
                    st.success("✅ All shipments in this range are progressing normally.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2: Single Tracking ID Analysis
    # ══════════════════════════════════════════════════════════════════════════
    with intel_tab2:
        st.markdown("#### 🔍 Single Shipment Deep Analysis")
        st.caption(
            "Enter a tracking ID to fetch live data from eShipz and run "
            "pure-Python delay, stuck, risk, and movement discrepancy detection."
        )

        with st.container(border=True):
            col_t1, col_t2 = st.columns([5, 1])
            with col_t1:
                intel_track_id = st.text_input(
                    "Tracking ID",
                    placeholder="e.g. 80970274836",
                    label_visibility="collapsed",
                    key="intel_single_track",
                )
            with col_t2:
                intel_analyze_btn = st.button(
                    "🔍 Analyze", use_container_width=True, key="intel_analyze_btn"
                )

        if intel_analyze_btn:
            tid = (intel_track_id or "").strip()
            if not tid:
                st.warning("Please enter a tracking ID.")
            else:
                with st.status(f"🔍 Analyzing shipment **{tid}** …", expanded=True) as _a_status:
                    st.write("🛰️ Fetching live tracking data from eShipz API…")
                    st.write("🔍 Running pure-Python intelligence analysis…")
                    try:
                        from shipment.tools.tool_serve import analyze_single_shipment
                        a_json2 = analyze_single_shipment(tid)
                        _a_status.update(label="✅ Analysis Complete", state="complete")
                    except Exception as _ex2:
                        _a_status.update(label="❌ Error", state="error")
                        st.error(f"Analysis error: {_ex2}")
                        a_json2 = None

                # ── Render single analysis result ─────────────────────────────
                if a_json2:
                    oid2  = a_json2.get("order_id", tid)
                    s2    = a_json2.get("status", "On-Time")
                    iss2  = a_json2.get("issues", [])
                    pred2 = a_json2.get("prediction", "—")
                    expl2 = a_json2.get("explanation", "—")
                    d_days = a_json2.get("delay_days", 0)
                    f_att  = a_json2.get("failed_attempts", 0)
                    t_cp   = a_json2.get("total_checkpoints", 0)
                    lmt2   = a_json2.get("last_movement_time") or "—"

                    st.markdown(f"""
                    <div class="intel-metric-row">
                      <div class="intel-metric">
                        <div class="im-val">{_status_pill(s2)}</div>
                        <div class="im-lbl">Status</div>
                      </div>
                      <div class="intel-metric">
                        <div class="im-val">{d_days}</div>
                        <div class="im-lbl">Days Delayed</div>
                      </div>
                      <div class="intel-metric">
                        <div class="im-val">{f_att}</div>
                        <div class="im-lbl">Failed Attempts</div>
                      </div>
                      <div class="intel-metric">
                        <div class="im-val">{t_cp}</div>
                        <div class="im-lbl">Checkpoints</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                    issues_html2 = "".join(f"<li>{iss}</li>" for iss in iss2)
                    st.markdown(f"""
                    <div class="intel-card">
                      <div class="ic-title">📦 {oid2} &nbsp; {_status_pill(s2)}</div>
                      <div class="ic-issues"><ul>{issues_html2}</ul></div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown(f"""
                    <div class="prediction-box">
                      <strong>🔮 Prediction:</strong> {pred2}<br>
                      <strong>💡 Explanation:</strong> {expl2}
                    </div>
                    """, unsafe_allow_html=True)

                    r_hubs2 = a_json2.get("repeated_hubs", [])
                    if r_hubs2:
                        st.warning(f"🔁 Repeated hubs: **{', '.join(r_hubs2)}**")

                    with st.expander("🛠 Raw Analysis (debug)"):
                        st.json(a_json2)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 7: LIVE TRACKING
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Live Tracking":
    from dashboards.user_dashboard import render_user_dashboard
    render_user_dashboard(db=db, user_id=_user_id, user_name=_user_name)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE 8: ADMIN DASHBOARD (admin only)
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Admin Dashboard":
    if _user_role != "admin":
        st.error("🔒 Access Denied. Admin privileges required.")
        st.stop()
    from dashboards.admin_dashboard import render_admin_dashboard
    render_admin_dashboard(db=db)
