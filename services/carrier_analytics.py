"""
Carrier Performance Analytics
Tracks on-time rates, average delays, and reliability scores per carrier.
"""

import datetime
import random
from typing import Dict, List, Any, Optional


# ── Seed data for carriers ────────────────────────────────────────────────────
_DEFAULT_CARRIERS = [
    {
        "carrier_name":       "BlueDart",
        "total_shipments":    142,
        "on_time_deliveries": 135,
        "average_delay_min":  18.4,
        "reliability_score":  0.95,
    },
    {
        "carrier_name":       "FedEx",
        "total_shipments":    98,
        "on_time_deliveries": 91,
        "average_delay_min":  22.1,
        "reliability_score":  0.93,
    },
    {
        "carrier_name":       "Delhivery",
        "total_shipments":    214,
        "on_time_deliveries": 188,
        "average_delay_min":  35.6,
        "reliability_score":  0.88,
    },
    {
        "carrier_name":       "DTDC",
        "total_shipments":    76,
        "on_time_deliveries": 62,
        "average_delay_min":  48.2,
        "reliability_score":  0.82,
    },
    {
        "carrier_name":       "eShipz Express",
        "total_shipments":    53,
        "on_time_deliveries": 48,
        "average_delay_min":  14.7,
        "reliability_score":  0.91,
    },
]


class CarrierAnalytics:
    """
    In-memory carrier performance store.
    Uses MongoDB when available.
    """

    def __init__(self, db=None):
        self.db = db
        self._data: Dict[str, Dict[str, Any]] = {}
        self._init_seed()

    def _init_seed(self):
        for c in _DEFAULT_CARRIERS:
            self._data[c["carrier_name"]] = dict(c)

        # Load from MongoDB if available
        if self.db is not None:
            try:
                docs = list(self.db.carrier_performance.find({}, {"_id": 0}))
                for d in docs:
                    self._data[d["carrier_name"]] = d
            except Exception:
                pass

    # ── Public API ─────────────────────────────────────────────────────────

    def get_all(self) -> List[Dict[str, Any]]:
        """Return all carrier records as a list."""
        return list(self._data.values())

    def get_carrier(self, name: str) -> Optional[Dict[str, Any]]:
        return dict(self._data.get(name, {}))

    def record_delivery(self, carrier: str, on_time: bool, delay_minutes: int = 0):
        """
        Update carrier metrics after a delivery event.
        """
        if carrier not in self._data:
            self._data[carrier] = {
                "carrier_name":       carrier,
                "total_shipments":    0,
                "on_time_deliveries": 0,
                "average_delay_min":  0.0,
                "reliability_score":  0.80,
            }
        rec = self._data[carrier]
        rec["total_shipments"] += 1
        if on_time:
            rec["on_time_deliveries"] += 1
        # Rolling average delay
        n = rec["total_shipments"]
        rec["average_delay_min"] = round(
            (rec["average_delay_min"] * (n - 1) + delay_minutes) / n, 1
        )
        rec["reliability_score"] = round(rec["on_time_deliveries"] / rec["total_shipments"], 3)

        # Persist
        if self.db is not None:
            try:
                self.db.carrier_performance.update_one(
                    {"carrier_name": carrier},
                    {"$set": rec},
                    upsert=True
                )
            except Exception:
                pass

    def on_time_rate(self, carrier: str) -> float:
        rec = self._data.get(carrier, {})
        total = rec.get("total_shipments", 1)
        on_time = rec.get("on_time_deliveries", 0)
        return round(on_time / total * 100, 1)

    def summary_table(self) -> List[Dict[str, Any]]:
        """Return formatted table rows for display."""
        rows = []
        for rec in self._data.values():
            total = rec.get("total_shipments", 1)
            on_time = rec.get("on_time_deliveries", 0)
            rows.append({
                "Carrier":          rec["carrier_name"],
                "Total Shipments":  total,
                "On-Time":          on_time,
                "On-Time Rate (%)": round(on_time / total * 100, 1),
                "Avg Delay (min)":  rec.get("average_delay_min", 0),
                "Reliability Score":rec.get("reliability_score", 0),
            })
        return sorted(rows, key=lambda x: x["Reliability Score"], reverse=True)


# ── Singleton ─────────────────────────────────────────────────────────────────
_analytics_instance: Optional[CarrierAnalytics] = None


def get_analytics(db=None) -> CarrierAnalytics:
    global _analytics_instance
    if _analytics_instance is None:
        _analytics_instance = CarrierAnalytics(db=db)
    return _analytics_instance
