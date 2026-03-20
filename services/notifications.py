"""
Notification Service — tracks shipment status-change notifications for users.

Notifications are stored in SQLite and shown in the sidebar.
Only admin-triggered status changes create notifications (not simulation ticks).
"""

import datetime
from typing import List, Dict, Optional
from auth.database import get_conn


# ── Schema ─────────────────────────────────────────────────────────────────────
_NOTIF_TABLE = """
CREATE TABLE IF NOT EXISTS notifications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    tracking_id  TEXT    NOT NULL,
    old_status   TEXT,
    new_status   TEXT    NOT NULL,
    message      TEXT    NOT NULL,
    is_read      INTEGER NOT NULL DEFAULT 0,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read);
"""


def init_notifications_table():
    try:
        conn = get_conn()
        conn.executescript(_NOTIF_TABLE)
        conn.commit()
        conn.close()
    except Exception:
        pass


init_notifications_table()


# ── Status → emoji + message ────────────────────────────────────────────────────
_STATUS_MESSAGES = {
    "Created":           ("📝", "has been created and is awaiting pickup"),
    "Picked Up":         ("📦", "has been picked up from the origin warehouse"),
    "In Transit":        ("🚚", "is now in transit"),
    "Out for Delivery":  ("🏠", "is out for delivery — arriving soon!"),
    "Delivered":         ("✅", "has been delivered successfully!"),
    "Delayed":           ("⚠️", "has been delayed"),
    "Cancelled":         ("❌", "has been cancelled"),
}

_STATUS_COLORS = {
    "Created":           "#818CF8",
    "Picked Up":         "#F59E0B",
    "In Transit":        "#00D1FF",
    "Out for Delivery":  "#FB923C",
    "Delivered":         "#22C55E",
    "Delayed":           "#EF4444",
    "Cancelled":         "#6B7280",
}


def create_notification(
    user_id: int,
    tracking_id: str,
    new_status: str,
    old_status: str = "",
) -> bool:
    """Insert a notification for a user about their shipment status change."""
    try:
        emoji, desc = _STATUS_MESSAGES.get(new_status, ("📍", f"status updated to {new_status}"))
        message = f"{emoji} Shipment **{tracking_id}** {desc}"

        conn = get_conn()
        conn.execute(
            "INSERT INTO notifications (user_id, tracking_id, old_status, new_status, message) "
            "VALUES (?,?,?,?,?)",
            (user_id, tracking_id, old_status or "", new_status, message)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_unread_notifications(user_id: int, limit: int = 5) -> List[Dict]:
    """Return the N most recent unread notifications for a user."""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT id, tracking_id, new_status, message, created_at "
            "FROM notifications WHERE user_id=? AND is_read=0 "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_all_notifications(user_id: int, limit: int = 20) -> List[Dict]:
    """Return all recent notifications (read + unread) for a user."""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT id, tracking_id, new_status, message, is_read, created_at "
            "FROM notifications WHERE user_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_unread_count(user_id: int) -> int:
    """Return count of unread notifications for a user."""
    try:
        conn = get_conn()
        n = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (user_id,)
        ).fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def mark_notification_read(notification_id: int):
    """Mark a single notification as read."""
    try:
        conn = get_conn()
        conn.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def mark_all_read(user_id: int):
    """Mark all notifications for a user as read."""
    try:
        conn = get_conn()
        conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_status_color(status: str) -> str:
    return _STATUS_COLORS.get(status, "#94A3B8")


def get_status_emoji(status: str) -> str:
    return _STATUS_MESSAGES.get(status, ("📍", ""))[0]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ADMIN NOTIFICATIONS — inform admins about new shipments needing assignment
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_ADMIN_NOTIF_TABLE = """
CREATE TABLE IF NOT EXISTS admin_notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_id     TEXT    NOT NULL UNIQUE,
    user_id         INTEGER NOT NULL,
    user_name       TEXT    NOT NULL DEFAULT '',
    source          TEXT    NOT NULL DEFAULT '',
    destination     TEXT    NOT NULL DEFAULT '',
    weight          REAL    NOT NULL DEFAULT 1.0,
    priority        TEXT    NOT NULL DEFAULT 'Medium',
    carrier_assigned TEXT   DEFAULT '',
    is_read         INTEGER NOT NULL DEFAULT 0,
    is_assigned     INTEGER NOT NULL DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_notif_assigned
    ON admin_notifications(is_assigned, created_at);
"""

CARRIERS = ["BlueDart", "Delhivery", "FedEx", "DTDC", "eShipz Express"]


def _init_admin_notifications_table():
    try:
        conn = get_conn()
        conn.executescript(_ADMIN_NOTIF_TABLE)
        conn.commit()
        conn.close()
    except Exception:
        pass


_init_admin_notifications_table()


def create_admin_notification(
    tracking_id: str,
    user_id: int,
    user_name: str,
    source: str,
    destination: str,
    weight: float,
    priority: str,
) -> bool:
    """Called when a user creates a new shipment — notifies admin to assign a carrier."""
    try:
        conn = get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO admin_notifications "
            "(tracking_id, user_id, user_name, source, destination, weight, priority) "
            "VALUES (?,?,?,?,?,?,?)",
            (tracking_id, user_id, user_name, source, destination, weight, priority)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_pending_admin_notifications(limit: int = 20) -> list:
    """Return unassigned shipments for admin review."""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT id, tracking_id, user_id, user_name, source, destination, "
            "weight, priority, carrier_assigned, is_read, is_assigned, created_at "
            "FROM admin_notifications "
            "WHERE is_assigned=0 ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_all_admin_notifications(limit: int = 30) -> list:
    """Return all admin notifications (assigned + unassigned)."""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT id, tracking_id, user_id, user_name, source, destination, "
            "weight, priority, carrier_assigned, is_read, is_assigned, created_at "
            "FROM admin_notifications ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_admin_pending_count() -> int:
    """Return count of unassigned shipments."""
    try:
        conn = get_conn()
        n = conn.execute(
            "SELECT COUNT(*) FROM admin_notifications WHERE is_assigned=0"
        ).fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def mark_admin_notifications_read():
    """Mark ALL admin notifications as read."""
    try:
        conn = get_conn()
        conn.execute("UPDATE admin_notifications SET is_read=1")
        conn.commit()
        conn.close()
    except Exception:
        pass


def assign_carrier(notif_id: int, tracking_id: str, carrier: str) -> bool:
    """
    Admin assigns a carrier to a shipment:
    1. Update admin_notifications row
    2. Update user_shipments carrier column
    3. Update live simulator
    4. Notify the user
    """
    try:
        conn = get_conn()
        # 1. Mark as assigned
        conn.execute(
            "UPDATE admin_notifications SET carrier_assigned=?, is_assigned=1, is_read=1 "
            "WHERE id=?",
            (carrier, notif_id)
        )
        # 2. Update user_shipments carrier
        conn.execute(
            "UPDATE user_shipments SET carrier=? WHERE tracking_id=?",
            (carrier, tracking_id)
        )
        # Get user_id for notification
        row = conn.execute(
            "SELECT user_id FROM user_shipments WHERE tracking_id=?",
            (tracking_id,)
        ).fetchone()
        user_id = row["user_id"] if row else None

        conn.commit()
        conn.close()

        # 3. Regenerate the AWB with the correct carrier prefix and save it
        try:
            from services.single_shot_processor import generate_awb
            from auth.auth_service import update_shipment_awb
            new_awb = generate_awb(carrier)
            update_shipment_awb(tracking_id, new_awb)
        except Exception:
            pass

        # 4. Update live simulator carrier
        try:
            from services.simulation_engine import get_simulator
            sim = get_simulator()
            with sim._lock:
                s = sim._shipments.get(tracking_id)
                if s:
                    s["carrier"] = carrier
        except Exception:
            pass

        # 5. Notify the user
        if user_id:
            try:
                _notify_user_carrier_assigned(user_id, tracking_id, carrier)
            except Exception:
                pass

        return True
    except Exception:
        return False


def _notify_user_carrier_assigned(user_id: int, tracking_id: str, carrier: str):
    """Create a user-facing notification that their delivery partner was assigned."""
    message = f"🚛 Delivery partner **{carrier}** has been assigned to shipment {tracking_id}"
    conn = get_conn()
    conn.execute(
        "INSERT INTO notifications (user_id, tracking_id, old_status, new_status, message) "
        "VALUES (?,?,?,?,?)",
        (user_id, tracking_id, "Created", "Carrier Assigned", message)
    )
    conn.commit()
    conn.close()
