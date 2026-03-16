"""
Login & Registration Page — Streamlit module.
Matches the existing dark cyberpunk design system.
Call render_auth_page() from app.py when user is not authenticated.
"""

import streamlit as st
from auth.auth_service import login_user, register_user


def render_auth_page():
    """
    Renders the full-page login/register form.
    Sets st.session_state keys on success:
        authenticated, user_id, user_name, user_email, user_role
    """

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align:center; padding: 2rem 0 1rem 0;">
        <h1 style="background: linear-gradient(to right, #00D1FF, #FFFFFF);
                   -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                   font-size: 2.8rem; font-weight: 800; margin-bottom: 0;">
            🚚 Eshipz AI
        </h1>
        <p style="color: #94A3B8; font-size: 1rem; margin-top: 4px;">
            Intelligent Logistics Platform — Sign in to continue
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Centered card ─────────────────────────────────────────────────────────
    col_l, col_c, col_r = st.columns([1, 1.4, 1])
    with col_c:

        # Tab selector: Login / Register
        tab_login, tab_register = st.tabs(["🔑 Sign In", "📝 Create Account"])

        # ── LOGIN TAB ─────────────────────────────────────────────────────────
        with tab_login:
            st.markdown("<br>", unsafe_allow_html=True)
            email    = st.text_input("Email", placeholder="you@example.com",    key="login_email")
            password = st.text_input("Password", type="password",
                                     placeholder="••••••••",                    key="login_password")
            st.caption("Default admin: admin@eshipz.com / Admin@123")

            if st.button("🔐 Sign In", use_container_width=True, key="login_btn"):
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    result = login_user(email, password)
                    if result["success"]:
                        u = result["user"]
                        st.session_state["authenticated"] = True
                        st.session_state["user_id"]       = u["id"]
                        st.session_state["user_name"]     = u["name"]
                        st.session_state["user_email"]    = u["email"]
                        st.session_state["user_role"]     = u["role"]
                        st.success(f"Welcome back, {u['name']}! 👋")
                        st.rerun()
                    else:
                        st.error(result["error"])

        # ── REGISTER TAB ──────────────────────────────────────────────────────
        with tab_register:
            st.markdown("<br>", unsafe_allow_html=True)
            reg_name  = st.text_input("Full Name",  placeholder="John Doe",         key="reg_name")
            reg_email = st.text_input("Email",       placeholder="you@example.com",  key="reg_email")
            reg_pass  = st.text_input("Password",    type="password",
                                      placeholder="Min. 6 characters",              key="reg_pass")
            reg_pass2 = st.text_input("Confirm Password", type="password",
                                      placeholder="Repeat password",                key="reg_pass2")

            if st.button("🚀 Create Account", use_container_width=True, key="register_btn"):
                if not all([reg_name, reg_email, reg_pass, reg_pass2]):
                    st.error("All fields are required.")
                elif reg_pass != reg_pass2:
                    st.error("Passwords do not match.")
                else:
                    result = register_user(reg_name, reg_email, reg_pass, role="user")
                    if result["success"]:
                        st.success("✅ Account created! Please sign in.")
                    else:
                        st.error(result["error"])

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align:center; margin-top: 3rem; color: #4B5563; font-size: 0.8rem;">
        Eshipz AI Logistics Platform · Secured with SHA-256 Encryption
    </div>
    """, unsafe_allow_html=True)
