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
from src.utils import apply_custom_css, load_lottie_file
from streamlit_lottie import st_lottie
from streamlit_option_menu import option_menu

load_dotenv()

# MUST be first Streamlit call
st.set_page_config(page_title="Eshipz AI", layout="wide")

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
            "Live Tracking",
            "Admin Dashboard",
        ]
        nav_icons = [
            "grid-1x2", "plus-circle", "clock-history", "cpu",
            "geo-alt", "display",
        ]
    else:
        # Regular users don't see Admin Dashboard
        nav_options = [
            "Dashboard",
            "New Shipment",
            "History & Tracking",
            "Agent Insights",
            "Live Tracking",
        ]
        nav_icons = [
            "grid-1x2", "plus-circle", "clock-history", "cpu",
            "geo-alt",
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
        st.metric("Active Agents", "3")
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
                                    "carrier":     result.get("carrier", "Pending"),
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
                        carrier      = result.get("carrier", "Pending"),
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
# ═════════════════════════════════════════════════════════════════════════════
elif page == "History & Tracking":
    st.title("Shipment Ledger")

    if _user_role == "admin":
        st.write("Admin view — all shipments in MongoDB.")
    else:
        st.write("Your shipment history from MongoDB.")

    if db is not None:
        search = st.text_input("Search by Destination")
        query  = {} if _user_role == "admin" else {"user_id": _user_id}
        if search:
            query["details.destination"] = {"$regex": search, "$options": "i"}

        history = list(db.history.find(query).sort("timestamp", -1))

        if history:
            for item in history:
                with st.expander(f"📦 ID: {item['_id']} | {item['timestamp'].strftime('%Y-%m-%d %H:%M')}"):
                    st.write(f"**Route:** {item['details']['source']} to {item['details']['destination']}")
                    st.write(f"**Weight:** {item['details']['weight']} kg")
                    if _user_role == "admin":
                        st.write(f"**Booked by:** {item.get('user_name', 'Unknown')}")
                    st.info(f"**Agent Decision:**\n{item['agent_output']}")
        else:
            st.info("No records found in the database.")
    else:
        st.warning("Database is offline.")

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

    st.markdown("---")
    st.subheader("System Architecture")
    st.code("""
    Frontend:       Streamlit (UI)
    Orchestration:  CrewAI (Agent Framework)
    Intelligence:   Gemini 2.0 Flash (LLM)
    Tracking:       MCP Server (FastMCP)
    Simulation:     Real-time GPS Engine (5-sec ticks)
    Database:       MongoDB Atlas + SQLite (Auth)
    Auth:           SHA-256 + Salt · Session-based
    Analytics:      Carrier Performance + Delay AI
    Visualization:  Leaflet.js (Dark Map)
    Tools:          Python Barcode & Network Ping
    """)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 5: LIVE TRACKING
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Live Tracking":
    from dashboards.user_dashboard import render_user_dashboard
    render_user_dashboard(db=db, user_id=_user_id, user_name=_user_name)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE 6: ADMIN DASHBOARD (admin only)
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Admin Dashboard":
    if _user_role != "admin":
        st.error("🔒 Access Denied. Admin privileges required.")
        st.stop()
    from dashboards.admin_dashboard import render_admin_dashboard
    render_admin_dashboard(db=db)
