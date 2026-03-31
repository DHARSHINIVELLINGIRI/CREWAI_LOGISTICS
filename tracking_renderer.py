# ═══════════════════════════════════════════════════════════════════════════════
# TRACKING RESULT RENDERER
# Call this after you get crew results back in the AI Assistant tab.
# It detects the JSON from track_shipment_eshipz and renders the full
# checkpoint table — identical to what you see in Postman.
#
# Usage in your AI Assistant section:
#   result = crew.kickoff(...)
#   render_tracking_output(result)
# ═══════════════════════════════════════════════════════════════════════════════

import json
import streamlit as st
from email.utils import parsedate_to_datetime
import datetime


def _fmt(raw: str) -> str:
    """Parse RFC-2822 dates like 'Thu, 08 Jan 2026 15:26:00 GMT'."""
    raw = (raw or "").strip()
    if not raw or raw == "null":
        return "—"
    try:
        return parsedate_to_datetime(raw).strftime("%d %b %Y  %H:%M")
    except Exception:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.datetime.strptime(raw, fmt).strftime("%d %b %Y  %H:%M")
            except Exception:
                pass
    return raw


def _tag_badge(tag: str) -> str:
    t = (tag or "").lower()
    if "exception" in t:
        return f'<span style="background:#2d1a1a;color:#f87171;border:1px solid #f87171;padding:3px 12px;border-radius:20px;font-size:.78rem;font-weight:700;">⚠ {tag}</span>'
    if "delivered" in t and "out" not in t:
        return f'<span style="background:#1a2d1a;color:#4ade80;border:1px solid #4ade80;padding:3px 12px;border-radius:20px;font-size:.78rem;font-weight:700;">✓ {tag}</span>'
    if "outfordelivery" in t or ("out" in t and "delivery" in t):
        return f'<span style="background:#1a1f2d;color:#60a5fa;border:1px solid #60a5fa;padding:3px 12px;border-radius:20px;font-size:.78rem;font-weight:700;">🚚 {tag}</span>'
    if "intransit" in t or "transit" in t:
        return f'<span style="background:#2d2a1a;color:#fbbf24;border:1px solid #fbbf24;padding:3px 12px;border-radius:20px;font-size:.78rem;font-weight:700;">→ {tag}</span>'
    if "pickedup" in t or "pickup" in t:
        return f'<span style="background:#241a2d;color:#c084fc;border:1px solid #c084fc;padding:3px 12px;border-radius:20px;font-size:.78rem;font-weight:700;">📦 {tag}</span>'
    if "info" in t or "registered" in t:
        return f'<span style="background:#1e2235;color:#94a3b8;border:1px solid #475569;padding:3px 12px;border-radius:20px;font-size:.78rem;font-weight:700;">ℹ {tag}</span>'
    return f'<span style="background:#1e2235;color:#94a3b8;border:1px solid #334155;padding:3px 12px;border-radius:20px;font-size:.78rem;font-weight:700;">{tag or "—"}</span>'


def _dot(tag: str) -> str:
    t = (tag or "").lower()
    if "exception" in t: return '<span style="color:#f87171">●</span>'
    if "delivered" in t and "out" not in t: return '<span style="color:#4ade80">●</span>'
    if "outfordelivery" in t or ("out" in t and "delivery" in t): return '<span style="color:#60a5fa">●</span>'
    if "intransit" in t or "transit" in t: return '<span style="color:#fbbf24">●</span>'
    if "pickedup" in t or "pickup" in t: return '<span style="color:#c084fc">●</span>'
    return '<span style="color:#475569">●</span>'


def render_tracking_output(crew_result):
    """
    Pass in the CrewAI result object (or its .raw string).
    Scans all task outputs for a JSON tracking payload and renders it.
    Falls back to plain text if no JSON is found.
    """

    st.markdown("""
    <style>
    .tr-table{width:100%;border-collapse:collapse;font-size:.83rem;margin-top:8px}
    .tr-table th{background:#1a1a2e;color:#a5b4fc;padding:9px 13px;text-align:left;
                 font-weight:600;border-bottom:2px solid #334155}
    .tr-table td{padding:8px 13px;border-bottom:1px solid #1e2235;vertical-align:middle}
    .tr-table tr:nth-child(even) td{background:#12141b}
    .tr-table tr:hover td{background:#1e2a45}
    .row-exc td:first-child{border-left:3px solid #f87171}
    .row-tra td:first-child{border-left:3px solid #fbbf24}
    .row-del td:first-child{border-left:3px solid #4ade80}
    .row-def td:first-child{border-left:3px solid #334155}
    .info-row2{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 18px}
    .info-cell2{background:#12141b;border:1px solid #1e2235;border-radius:9px;
                padding:11px 16px;flex:1;min-width:130px}
    .info-cell2 .lbl{font-size:.67rem;color:#64748b;text-transform:uppercase;letter-spacing:.5px}
    .info-cell2 .val{font-size:.92rem;font-weight:700;color:#e2e8f0;margin-top:3px}
    .sum2{background:#1a1f2d;border:1px solid #334155;border-radius:9px;
          padding:11px 18px;display:flex;gap:22px;flex-wrap:wrap;margin-bottom:12px}
    .sum2 .sl{color:#64748b;font-size:.73rem;display:block}
    .sum2 .sv{color:#e2e8f0;font-weight:700;font-size:.97rem}
    </style>
    """, unsafe_allow_html=True)

    # ── collect all raw strings AND tool-call message contents ────────────────
    raw_strings = []
    tool_contents = []   # tool responses from messages (this is where JSON lives)
    try:
        for task_out in crew_result.tasks_output:
            raw_strings.append(task_out.raw or "")
            # Walk the LLM message log and grab every tool response
            for msg in (task_out.messages or []):
                if msg.get("role") == "tool":
                    tc = msg.get("content", "")
                    if tc:
                        tool_contents.append(tc)
    except Exception:
        raw_strings.append(str(crew_result))

    def _extract_checkpoints(text: str):
        """Return parsed tracking list if `text` contains eShipz checkpoint JSON."""
        for start_char, wrapper in (("[", None), ("{", "dict")):
            idx = text.find(start_char)
            if idx == -1:
                continue
            try:
                candidate = json.loads(text[idx:])
                if wrapper is None and isinstance(candidate, list) and candidate and "checkpoints" in candidate[0]:
                    return candidate
                if wrapper == "dict" and isinstance(candidate, dict) and "checkpoints" in candidate:
                    return [candidate]
            except Exception:
                pass
        return None

    # ── 1. Prefer tool-call responses (contain the raw JSON the agent received) ─
    tracking_json = None
    for tc in tool_contents:
        tracking_json = _extract_checkpoints(tc)
        if tracking_json:
            break

    # ── 2. Fall back to scanning raw text ─────────────────────────────────────
    if not tracking_json:
        for raw in raw_strings:
            tracking_json = _extract_checkpoints(raw)
            if tracking_json:
                break

    # ── if we found real tracking data, render the full table ─────────────────
    if tracking_json:
        st.success(f"✅ Live eShipz data retrieved — {len(tracking_json)} record(s)")

        for ship in tracking_json:
            tag         = ship.get("tag", "—")
            slug        = ship.get("slug", "—").upper()
            order_id    = ship.get("order_id", "—")
            track_num   = ship.get("tracking_number", "—")
            exp_del     = _fmt(str(ship.get("expected_delivery_date") or ""))
            actual_del  = _fmt(str(ship.get("delivery_date") or ""))
            checkpoints = ship.get("checkpoints", [])

            st.markdown(
                f"**AWB** &nbsp;`{track_num}`&nbsp;&nbsp;{_tag_badge(tag)}",
                unsafe_allow_html=True,
            )

            st.markdown(f"""
            <div class="info-row2">
              <div class="info-cell2"><div class="lbl">Carrier</div>
                <div class="val">{slug}</div></div>
              <div class="info-cell2"><div class="lbl">Tag</div>
                <div class="val">{tag}</div></div>
              <div class="info-cell2"><div class="lbl">Order ID</div>
                <div class="val">{order_id}</div></div>
              <div class="info-cell2"><div class="lbl">Expected Delivery</div>
                <div class="val">{exp_del}</div></div>
              <div class="info-cell2"><div class="lbl">Actual Delivery</div>
                <div class="val">{"⏳ Pending" if actual_del == "—" else actual_del}</div></div>
            </div>""", unsafe_allow_html=True)

            exc_n  = sum(1 for c in checkpoints if c.get("tag","").lower() == "exception")
            tra_n  = sum(1 for c in checkpoints if c.get("tag","").lower() == "intransit")
            latest = checkpoints[0].get("city","—") if checkpoints else "—"

            st.markdown(f"""
            <div class="sum2">
              <div><span class="sl">Total Events</span>
                   <span class="sv">{len(checkpoints)}</span></div>
              <div><span class="sl">Exception</span>
                   <span class="sv" style="color:#f87171">{exc_n}</span></div>
              <div><span class="sl">InTransit</span>
                   <span class="sv" style="color:#fbbf24">{tra_n}</span></div>
              <div><span class="sl">Latest Hub</span>
                   <span class="sv">{latest}</span></div>
            </div>""", unsafe_allow_html=True)

            st.markdown(f"**📍 All {len(checkpoints)} Checkpoint Events**")

            if checkpoints:
                rows_html = ""
                total = len(checkpoints)
                for i, cp in enumerate(checkpoints):
                    cp_tag    = cp.get("tag", "—")
                    cp_subtag = cp.get("subtag", "")
                    cp_city   = cp.get("city", "—")
                    cp_state  = (cp.get("state") or "").strip()
                    cp_date   = _fmt(cp.get("date", ""))
                    cp_remark = cp.get("remark", "—")
                    location  = cp_city + (f", {cp_state}" if cp_state else "")
                    seq       = total - i

                    t_lower   = cp_tag.lower()
                    row_cls   = ("row-exc" if "exception" in t_lower else
                                 "row-del" if "delivered" in t_lower else
                                 "row-tra" if "intransit" in t_lower else "row-def")

                    subtag_html = ""
                    if cp_subtag:
                        subtag_html = (f'<span style="background:#2d1a1a;color:#fca5a5;'
                                       f'border:1px solid #f87171;border-radius:8px;'
                                       f'padding:1px 7px;font-size:.67rem;margin-left:6px">'
                                       f'{cp_subtag}</span>')

                    rows_html += f"""
                    <tr class="{row_cls}">
                      <td style="color:#475569;font-size:.7rem">#{seq}</td>
                      <td>{_dot(cp_tag)}&nbsp;{cp_tag}{subtag_html}</td>
                      <td style="white-space:nowrap">{location}</td>
                      <td style="white-space:nowrap;color:#94a3b8">{cp_date}</td>
                      <td style="color:#cbd5e1">{cp_remark}</td>
                    </tr>"""

                st.markdown(f"""
                <table class="tr-table">
                  <thead><tr>
                    <th>#</th><th>Tag · Subtag</th>
                    <th>City / Hub</th><th>Date &amp; Time</th><th>Remark</th>
                  </tr></thead>
                  <tbody>{rows_html}</tbody>
                </table>""", unsafe_allow_html=True)
            else:
                st.info("No checkpoint events in this record.")

            with st.expander("🛠 Raw JSON (debug)", expanded=False):
                st.json(ship)

    else:
        # ── no JSON found — show plain agent text output ───────────────────────
        for raw in raw_strings:
            if raw.strip():
                st.markdown(raw)