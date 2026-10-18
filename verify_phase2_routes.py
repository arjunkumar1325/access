"""
AccessAI - Phase 2 Routing Engine Validation Script
Tests 3 valid start/destination pairs against the running backend API:
1. Stairs Avoidance and Wheelchair Detour Test
2. Long Pedestrian Walking Corridor Across Campus
3. Dynamic Community Barrier Avoidance and Rerouting Test

Verifies:
- Coordinates are extracted from real OpenStreetMap graph edges
- No hardcoded demo routes are used
- Latitude/longitude order is preserved for Leaflet frontend
- Deterministic barrier penalty application without cost accumulation
"""

import requests
import json
import math

BASE_URL = "http://127.0.0.1:5000"

def run_tests():
    print("=" * 70)
    print("ACCESSAI - PHASE 2 BACKEND ROUTING ENGINE VERIFICATION")
    print("=" * 70)

    # Health Check
    health_resp = requests.get(f"{BASE_URL}/api/health")
    assert health_resp.status_code == 200, f"Health check failed: {health_resp.status_code}"
    health_data = health_resp.json()
    print(f"Server Status: {health_data['status']}")
    print(f"Graph Loaded: {health_data['graph']['nodes']} nodes, {health_data['graph']['edges']} edges")
    print(f"Coverage Area: {health_data['graph']['area_name']}\n")

    # --------------------------------------------------------------------------
    # TEST PAIR 1: Real OpenStreetMap Stairs Avoidance
    # --------------------------------------------------------------------------
    print("-" * 70)
    print("TEST PAIR 1: Stairs Avoidance and Accessible Detour Calculation")
    print("-" * 70)
    pair1_payload = {
        "start": [12.9677227, 77.5926506],
        "end": [12.9678777, 77.5927888],
        "mode": "both"
    }
    r1 = requests.post(f"{BASE_URL}/api/route", json=pair1_payload)
    assert r1.status_code == 200, f"Pair 1 request failed: {r1.status_code} - {r1.text}"
    d1 = r1.json()

    assert d1["success"] is True
    short1 = d1["shortest_route"]
    acc1 = d1["accessible_route"]

    print(f"Start: {pair1_payload['start']}")
    print(f"Destination: {pair1_payload['end']}")
    print(f"Shortest Route Distance: {short1['distance_meters']} m | Steps: {short1['steps_count']} flight(s)")
    print(f"Accessible Route Distance: {acc1['distance_meters']} m | Steps: {acc1['steps_count']} flight(s)")
    print(f"Duration: {acc1['duration_minutes']} min | Speed Basis: {acc1['speed_basis']}")
    print(f"Detour Reasons: {d1['reasons']}")
    print(f"Route Coordinates Count: {len(acc1['coordinates'])} points")
    print(f"Sample First 2 Coords: {acc1['coordinates'][:2]}")
    print(f"Sample Last 2 Coords: {acc1['coordinates'][-2:]}")

    # Assertions
    assert short1["steps_count"] >= 1, "Shortest route must identify the real mapped stairs!"
    assert acc1["steps_count"] == 0, "Accessible route must completely avoid all stairs!"
    assert acc1["distance_meters"] > short1["distance_meters"], "Accessible detour must be longer than direct stairs!"
    assert any("stair" in r.lower() for r in d1["reasons"]), "Reasons must report stair bypass!"
    assert all(len(pt) == 2 and 12.0 < pt[0] < 13.5 and 77.0 < pt[1] < 78.0 for pt in acc1["coordinates"])
    print(">> TEST PAIR 1 PASSED: Accessible engine successfully rerouted around real OSM stairs!\n")

    # --------------------------------------------------------------------------
    # TEST PAIR 2: Long Pedestrian Walking Corridor Across Campus
    # --------------------------------------------------------------------------
    print("-" * 70)
    print("TEST PAIR 2: Long Pedestrian Walking Corridor Across Campus")
    print("-" * 70)
    pair2_payload = {
        "start": [12.9672102, 77.5920049],
        "end": [12.9759970, 77.5984411],
        "mode": "accessible"
    }
    r2 = requests.post(f"{BASE_URL}/api/route", json=pair2_payload)
    assert r2.status_code == 200, f"Pair 2 request failed: {r2.status_code} - {r2.text}"
    d2 = r2.json()

    assert d2["success"] is True
    acc2 = d2["accessible_route"]

    print(f"Start: {pair2_payload['start']}")
    print(f"Destination: {pair2_payload['end']}")
    print(f"Total Walking Distance: {d2['distance']} meters ({d2['distance']/1000.0:.2f} km)")
    print(f"Estimated Duration: {d2['duration_minutes']} minutes | {d2['speed_basis']}")
    print(f"Streets/Footpaths Used: {acc2['streets']}")
    print(f"Total Traversed Path Coordinates: {len(d2['coordinates'])} points")
    print(f"Disclaimers & Warnings: {d2['warnings']}")

    # Assertions
    assert d2["distance"] > 1000.0, "Corridor route must traverse real distance across campus!"
    assert d2["duration_minutes"] > 15, "Estimated duration must match real distance calculation!"
    assert len(acc2["streets"]) >= 2, "Route must traverse multiple mapped street/footpath segments!"
    assert len(d2["coordinates"]) > 30, "Route must return dense polyline points from graph geometry!"
    print(">> TEST PAIR 2 PASSED: Long corridor routing operates seamlessly across MultiDiGraph edges!\n")

    # --------------------------------------------------------------------------
    # TEST PAIR 3: Dynamic Community Barrier Avoidance and Rerouting
    # --------------------------------------------------------------------------
    print("-" * 70)
    print("TEST PAIR 3: Dynamic Barrier Avoidance & Non-Accumulating Penalties")
    print("-" * 70)
    # Target edge endpoints (12558269330, 11425338163)
    start_pt = [12.971661, 77.595296]
    end_pt = [12.971682, 77.595303]

    # Step 3A: Compute unblocked baseline
    r3_base = requests.post(f"{BASE_URL}/api/route", json={"start": start_pt, "end": end_pt, "mode": "accessible"})
    assert r3_base.status_code == 200
    d3_base = r3_base.json()
    base_dist = d3_base["accessible_route"]["distance_meters"]
    print(f"Baseline (Unblocked) Distance: {base_dist} m ({len(d3_base['coordinates'])} points)")

    # Step 3B: Report an active obstacle directly on this footpath
    barrier_payload = {
        "lat": 12.97167185,
        "lon": 77.5952994,
        "category": "Broken pavement / deep ditch",
        "note": "Phase 2 automated barrier test obstacle"
    }
    r_post_barr = requests.post(f"{BASE_URL}/api/barriers", json=barrier_payload)
    assert r_post_barr.status_code == 201, f"Failed to post barrier: {r_post_barr.text}"
    created_barrier = r_post_barr.json()["barrier"]
    barrier_id = created_barrier["id"]
    print(f"Submitted Barrier #{barrier_id} at ({barrier_payload['lat']}, {barrier_payload['lon']})")

    # Step 3C: Recompute route with active barrier
    r3_blocked = requests.post(f"{BASE_URL}/api/route", json={"start": start_pt, "end": end_pt, "mode": "accessible"})
    assert r3_blocked.status_code == 200
    d3_blocked = r3_blocked.json()
    blocked_dist = d3_blocked["accessible_route"]["distance_meters"]
    print(f"Detoured Route Distance with Barrier: {blocked_dist} m ({len(d3_blocked['coordinates'])} points)")
    print(f"Detour Route Reason: Bypassed blocked path ({blocked_dist}m vs direct {base_dist}m)")

    assert blocked_dist > base_dist, "Route must take alternate detour around the barrier!"

    # Step 3D: Test non-accumulation over 5 consecutive requests
    print("Verifying penalty non-accumulation over 5 repeated requests...")
    repeated_distances = []
    for _ in range(5):
        r_rep = requests.post(f"{BASE_URL}/api/route", json={"start": start_pt, "end": end_pt, "mode": "accessible"})
        repeated_distances.append(r_rep.json()["accessible_route"]["distance_meters"])

    assert all(d == blocked_dist for d in repeated_distances), f"Distances varied across requests: {repeated_distances}"
    print(f"All 5 requests yielded identical deterministic distance: {repeated_distances[0]} m")

    # Step 3E: Resolve the barrier and verify route restores to direct path
    r_res = requests.patch(f"{BASE_URL}/api/barriers/{barrier_id}", json={"status": "resolved"})
    assert r_res.status_code == 200
    print(f"Resolved Barrier #{barrier_id}. Recomputing route...")

    r3_restored = requests.post(f"{BASE_URL}/api/route", json={"start": start_pt, "end": end_pt, "mode": "accessible"})
    restored_dist = r3_restored.json()["accessible_route"]["distance_meters"]
    print(f"Restored Route Distance after Barrier Resolution: {restored_dist} m")
    assert restored_dist == base_dist, f"Route did not restore to baseline: {restored_dist} != {base_dist}"
    print(">> TEST PAIR 3 PASSED: Dynamic barrier detour, non-accumulation, and restoration verified!\n")

    print("=" * 70)
    print("ALL 3 VALID GRAPH PAIR TESTS COMPLETED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
