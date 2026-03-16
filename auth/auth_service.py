"""
Authentication Service — all auth business logic.
register, login, get_user, get_all_users, save_shipment, get_user_shipments
"""

import hashlib
import secrets
import datetime
from typing import Optional, Dict, Any, List

from auth.database import get_conn


# ── Password helpers ──────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()

def _make_salt() -> str:
    return secrets.token_hex(16)


# ── User registration ─────────────────────────────────────────────────────────

def register_user(name: str, email: str, password: str, role: str = "user") -> Dict[str, Any]:
    """
    Register a new user.
    Returns {"success": True, "user_id": int} or {"success": False, "error": str}
    """
    if not name.strip() or not email.strip() or not password:
        return {"success": False, "error": "All fields are required."}
    if len(password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters."}
    if "@" not in email:
        return {"success": False, "error": "Invalid email address."}

    salt    = _make_salt()
    pw_hash = _hash_password(password, salt)

    try:
        conn = get_conn()
        cur  = conn.execute(
            "INSERT INTO users (name, email, password_hash, salt, role) VALUES (?,?,?,?,?)",
            (name.strip(), email.strip().lower(), pw_hash, salt, role)
        )
        conn.commit()
        user_id = cur.lastrowid
        conn.close()
        return {"success": True, "user_id": user_id}
    except Exception as e:
        if "UNIQUE" in str(e):
            return {"success": False, "error": "An account with this email already exists."}
        return {"success": False, "error": f"Registration failed: {e}"}


# ── Login ─────────────────────────────────────────────────────────────────────

def login_user(email: str, password: str) -> Dict[str, Any]:
    """
    Validate credentials.
    Returns {"success": True, "user": {...}} or {"success": False, "error": str}
    """
    conn = get_conn()
    row  = conn.execute(
        "SELECT id, name, email, password_hash, salt, role, created_at FROM users WHERE email = ?",
        (email.strip().lower(),)
    ).fetchone()
    conn.close()

    if row is None:
        return {"success": False, "error": "No account found with that email."}

    expected = _hash_password(password, row["salt"])
    if expected != row["password_hash"]:
        return {"success": False, "error": "Incorrect password."}

    return {
        "success": True,
        "user": {
            "id":         row["id"],
            "name":       row["name"],
            "email":      row["email"],
            "role":       row["role"],
            "created_at": row["created_at"],
        }
    }


# ── User queries ──────────────────────────────────────────────────────────────

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row  = conn.execute(
        "SELECT id, name, email, role, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users() -> List[Dict[str, Any]]:
    """Admin-only: return all registered users."""
    conn  = get_conn()
    rows  = conn.execute(
        "SELECT id, name, email, role, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_users(query: str) -> List[Dict[str, Any]]:
    """Admin-only: search users by name or email."""
    q    = f"%{query}%"
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, email, role, created_at FROM users "
        "WHERE name LIKE ? OR email LIKE ? ORDER BY created_at DESC",
        (q, q)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_count() -> int:
    conn = get_conn()
    n    = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n


# ── Shipment records ──────────────────────────────────────────────────────────

def save_user_shipment(
    tracking_id: str, user_id: int, source: str, destination: str,
    weight: float, priority: str, carrier: str = "", agent_output: str = "",
    user_name: str = "", awb: str = ""
) -> int:
    """Save a shipment linked to a user. Returns the new shipment id."""
    conn = get_conn()
    cur  = conn.execute(
        """INSERT INTO user_shipments
           (tracking_id, user_id, source, destination, weight, priority, carrier, agent_output, awb)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (tracking_id, user_id, source, destination, weight, priority, carrier, agent_output, awb)
    )
    conn.commit()
    sid = cur.lastrowid
    conn.close()

    # Notify admin that a new shipment needs a delivery partner assigned
    try:
        from services.notifications import create_admin_notification
        create_admin_notification(
            tracking_id = tracking_id,
            user_id     = user_id,
            user_name   = user_name or f"User #{user_id}",
            source      = source,
            destination = destination,
            weight      = weight,
            priority    = priority,
        )
    except Exception:
        pass

    return sid


def update_shipment_awb(tracking_id: str, awb: str) -> bool:
    """Update the AWB for a shipment (called when carrier is assigned)."""
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE user_shipments SET awb=? WHERE tracking_id=?",
            (awb, tracking_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_user_shipments(user_id: int) -> List[Dict[str, Any]]:
    """Return shipments belonging to a specific user."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM user_shipments WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_shipments() -> List[Dict[str, Any]]:
    """Admin-only: return all shipments with user info."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT us.*, u.name as user_name, u.email as user_email
           FROM user_shipments us
           LEFT JOIN users u ON us.user_id = u.id
           ORDER BY us.created_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_shipment_status(tracking_id: str, new_status: str) -> bool:
    """Admin: update shipment status in SQLite AND live simulator."""
    changed = False

    # 1. Try to update SQLite user_shipments
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE user_shipments SET status = ? WHERE tracking_id = ?",
            (new_status, tracking_id)
        )
        conn.commit()
        changed = conn.total_changes > 0
        conn.close()
    except Exception:
        pass

    # 2. Always sync to live simulator (even if SQLite row missing)
    try:
        from services.simulation_engine import get_simulator
        from services.lifecycle import STAGE_DELIVERED
        import datetime
        sim = get_simulator()
        with sim._lock:
            s = sim._shipments.get(tracking_id)
            if s is not None:
                s["status"] = new_status
                # Lock status for 10 minutes so _tick doesn't overwrite it
                s["status_locked_until"] = (
                    datetime.datetime.now() +
                    datetime.timedelta(minutes=10)
                ).isoformat()
                if new_status == STAGE_DELIVERED:
                    from services.india_network import INDIA_CITIES
                    dest = INDIA_CITIES.get(s["destination"], {})
                    if dest:
                        s["lat"]          = dest["lat"]
                        s["lon"]          = dest["lon"]
                        s["current_city"] = s["destination"]
                changed = True  # count simulator update as success
            else:
                # Shipment only in SQLite, not in simulator — load it in
                _load_shipment_into_sim(sim, tracking_id, initial_status=new_status)
                changed = True
    except Exception:
        pass

    # 3. Create a notification for the shipment owner
    try:
        conn2 = get_conn()
        row = conn2.execute(
            "SELECT user_id, status FROM user_shipments WHERE tracking_id=?",
            (tracking_id,)
        ).fetchone()
        conn2.close()
        if row:
            from services.notifications import create_notification
            create_notification(
                user_id     = row["user_id"],
                tracking_id = tracking_id,
                new_status  = new_status,
                old_status  = row["status"] or "",
            )
    except Exception:
        pass

    return changed


def _load_shipment_into_sim(sim, tracking_id: str, initial_status: str = ""):
    """Load a persisted shipment from SQLite into the live simulator."""
    try:
        conn = get_conn()
        row  = conn.execute(
            "SELECT tracking_id, user_id, source, destination, weight, priority, carrier, status "
            "FROM user_shipments WHERE tracking_id = ?",
            (tracking_id,)
        ).fetchone()
        conn.close()
        if row:
            rec = dict(row)
            if initial_status:
                rec["status"] = initial_status
            sim.create_shipment_from_record(rec)
    except Exception:
        pass


def get_shipment_stats() -> Dict[str, Any]:
    """Admin analytics: shipment counts by status."""
    conn  = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM user_shipments").fetchone()[0]
    by_status = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM user_shipments GROUP BY status"
    ).fetchall()
    conn.close()
    return {"total": total, "by_status": {r["status"]: r["cnt"] for r in by_status}}
