"""Quick test: verify _run_analysis_pure returns prediction + explanation for all status paths."""
import sys, json, datetime
sys.path.insert(0, "src")
from shipment.tools.tool_serve import _run_analysis_pure

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Test 1: On-Time shipment
r1 = _run_analysis_pure({
    "order_id": "ONTIME-001", "tag": "in_transit",
    "checkpoints": [{"city": "Delhi", "tag": "dispatched", "checkpoint_time": now}]
})
print(f"TEST 1 On-Time:   status={r1['status']}  pred={r1['prediction']}")
print(f"  explanation: {r1['explanation']}")
assert r1["status"] == "On-Time"
assert "prediction" in r1
assert "explanation" in r1

# Test 2: Delayed shipment
r2 = _run_analysis_pure({
    "order_id": "DELAY-002", "tag": "in_transit",
    "expected_delivery_date": "2026-03-10",
    "checkpoints": [{"city": "Mumbai", "tag": "in_transit", "checkpoint_time": now}]
})
print(f"TEST 2 Delayed:   status={r2['status']}  pred={r2['prediction']}")
print(f"  explanation: {r2['explanation']}")
assert r2["status"] == "Delayed"
assert "delayed" in r2["explanation"].lower()

# Test 3: High Risk (failed delivery + RTO)
r3 = _run_analysis_pure({
    "order_id": "RISK-003", "tag": "rto",
    "checkpoints": [
        {"city": "Delhi", "tag": "failed delivery", "checkpoint_time": now},
        {"city": "Delhi", "tag": "delivery attempt failed", "checkpoint_time": now},
    ]
})
print(f"TEST 3 High Risk: status={r3['status']}  pred={r3['prediction']}")
print(f"  explanation: {r3['explanation']}")
assert r3["status"] == "High Risk"
assert "return" in r3["prediction"].lower()

# Test 4: No checkpoints
r4 = _run_analysis_pure({
    "order_id": "NEW-004", "tag": "booked", "checkpoints": []
})
print(f"TEST 4 No data:   status={r4['status']}  pred={r4['prediction']}")
print(f"  explanation: {r4['explanation']}")
assert r4["status"] == "On-Time"
assert "prediction" in r4

# Test 5: Stuck shipment (old checkpoint)
r5 = _run_analysis_pure({
    "order_id": "STUCK-005", "tag": "in_transit",
    "checkpoints": [
        {"city": "Chennai", "tag": "arrived", "checkpoint_time": "2026-03-20 10:00:00"},
        {"city": "Chennai", "tag": "arrived", "checkpoint_time": "2026-03-19 08:00:00"},
        {"city": "Chennai", "tag": "arrived", "checkpoint_time": "2026-03-18 06:00:00"},
    ]
})
print(f"TEST 5 Stuck:     status={r5['status']}  pred={r5['prediction']}")
print(f"  explanation: {r5['explanation']}")
assert r5["status"] == "Stuck"
assert "stuck" in r5["explanation"].lower() or "no movement" in r5["explanation"].lower()

print("\n✅ ALL 5 TESTS PASSED — prediction+explanation deterministic, no LLM")
