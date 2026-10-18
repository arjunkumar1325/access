"""
AccessAI - Phase 3 Final Acceptance Test Suite
Automated execution of all Phase 3 Final Acceptance Criteria:
1. Search for two different real locations inside configured map area
2. Change start location and confirm recalculation
3. Change destination and confirm recalculation
4. Switch between shortest and accessibility-prioritized routing
5. Submit a barrier and verify persistence in DB and routing influence
6. Test invalid location and location outside the graph
7. Confirm failures show honest error messages without demo routes
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:5000"

def run_acceptance_tests():
    print("=" * 75)
    print("ACCESSAI - PHASE 3 FINAL ACCEPTANCE TEST SUITE")
    print("=" * 75)
    
    results = {}

    # Health check
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=5)
        assert r.status_code == 200, f"Health check failed with {r.status_code}"
        health = r.json()
        print(f"[PREFLIGHT] Server OK. Graph: {health['graph']['nodes']} nodes, {health['graph']['edges']} edges.")
        print(f"[PREFLIGHT] Coverage Area: {health['graph']['area_name']}\n")
    except Exception as e:
        print(f"[FATAL] Server not reachable: {e}")
        return False

    # --------------------------------------------------------------------------
    # CRITERION 1: Search for two different real locations inside configured area
    # --------------------------------------------------------------------------
    print("[TEST 1] Searching two real locations inside map area...")
    try:
        # Step 1A: Geocode place query
        geo_resp = requests.get(f"{BASE_URL}/api/geocode?q=Cubbon+Park")
        assert geo_resp.status_code == 200
        geo_data = geo_resp.json()
        assert geo_data["success"] is True and len(geo_data["results"]) > 0
        first_loc = geo_data["results"][0]
        print(f"  Geocoded 'Cubbon Park' -> [{first_loc['lat']:.5f}, {first_loc['lon']:.5f}] (in_bounds: {first_loc['in_graph_bounds']})")

        # Step 1B: Calculate route between two real locations
        loc_a = [12.97350, 77.59250]
        loc_b = [12.97100, 77.59600]
        route_resp = requests.post(f"{BASE_URL}/api/route", json={
            "start": loc_a,
            "end": loc_b,
            "mode": "accessible"
        })
        assert route_resp.status_code == 200
        r_data1 = route_resp.json()
        assert r_data1["success"] is True
        assert len(r_data1["coordinates"]) > 5
        assert r_data1["distance"] > 100.0
        assert r_data1["duration_minutes"] > 0
        print(f"  Route 1 Calculated: Distance = {r_data1['distance']}m, Duration = {r_data1['duration_minutes']} min, Points = {len(r_data1['coordinates'])}")
        results["1. Search real locations"] = "PASSED"
    except Exception as err:
        print(f"  FAILED: {err}")
        results["1. Search real locations"] = f"FAILED: {err}"

    # --------------------------------------------------------------------------
    # CRITERION 2: Change start location and confirm route is recalculated
    # --------------------------------------------------------------------------
    print("\n[TEST 2] Changing start location and confirming recalculation...")
    try:
        new_loc_a = [12.96772, 77.59265]  # southern entrance
        route_resp2 = requests.post(f"{BASE_URL}/api/route", json={
            "start": new_loc_a,
            "end": loc_b,
            "mode": "accessible"
        })
        assert route_resp2.status_code == 200
        r_data2 = route_resp2.json()
        assert r_data2["success"] is True
        # Must differ from route 1
        assert r_data2["distance"] != r_data1["distance"], f"Distance did not change: {r_data2['distance']} == {r_data1['distance']}"
        assert r_data2["coordinates"] != r_data1["coordinates"], "Route coordinates did not change!"
        print(f"  Route 2 Calculated (New Start): Distance = {r_data2['distance']}m (was {r_data1['distance']}m), Points = {len(r_data2['coordinates'])}")
        results["2. Recalculate on start change"] = "PASSED"
    except Exception as err:
        print(f"  FAILED: {err}")
        results["2. Recalculate on start change"] = f"FAILED: {err}"

    # --------------------------------------------------------------------------
    # CRITERION 3: Change destination and confirm route is recalculated
    # --------------------------------------------------------------------------
    print("\n[TEST 3] Changing destination and confirming recalculation...")
    try:
        new_loc_b = [12.97599, 77.59844]  # northeast corridor
        route_resp3 = requests.post(f"{BASE_URL}/api/route", json={
            "start": new_loc_a,
            "end": new_loc_b,
            "mode": "accessible"
        })
        assert route_resp3.status_code == 200
        r_data3 = route_resp3.json()
        assert r_data3["success"] is True
        assert r_data3["distance"] != r_data2["distance"], f"Distance did not change: {r_data3['distance']} == {r_data2['distance']}"
        assert r_data3["coordinates"] != r_data2["coordinates"], "Route coordinates did not change!"
        print(f"  Route 3 Calculated (New Destination): Distance = {r_data3['distance']}m (was {r_data2['distance']}m), Points = {len(r_data3['coordinates'])}")
        results["3. Recalculate on destination change"] = "PASSED"
    except Exception as err:
        print(f"  FAILED: {err}")
        results["3. Recalculate on destination change"] = f"FAILED: {err}"

    # --------------------------------------------------------------------------
    # CRITERION 4: Switch between shortest and accessibility-prioritized routing
    # --------------------------------------------------------------------------
    print("\n[TEST 4] Switching between Shortest and Accessible routing modes...")
    try:
        stairs_pair_start = [12.9677227, 77.5926506]
        stairs_pair_end = [12.9678777, 77.5927888]

        # Mode A: Shortest
        r_short = requests.post(f"{BASE_URL}/api/route", json={
            "start": stairs_pair_start,
            "end": stairs_pair_end,
            "mode": "shortest"
        })
        assert r_short.status_code == 200
        d_short = r_short.json()
        assert d_short["route_mode"] == "shortest"
        assert d_short["distance"] == d_short["shortest_route"]["distance_meters"]
        assert d_short["shortest_route"]["steps_count"] >= 1, "Shortest route must identify the steps!"
        print(f"  Mode 'shortest': Distance = {d_short['distance']}m | Steps = {d_short['shortest_route']['steps_count']} flight(s)")

        # Mode B: Accessible
        r_acc = requests.post(f"{BASE_URL}/api/route", json={
            "start": stairs_pair_start,
            "end": stairs_pair_end,
            "mode": "accessible"
        })
        assert r_acc.status_code == 200
        d_acc = r_acc.json()
        assert d_acc["route_mode"] == "accessible"
        assert d_acc["distance"] == d_acc["accessible_route"]["distance_meters"]
        assert d_acc["accessible_route"]["steps_count"] == 0, "Accessible route must avoid all steps!"
        assert d_acc["distance"] > d_short["distance"], "Accessible detour must be longer than stairs!"
        print(f"  Mode 'accessible': Distance = {d_acc['distance']}m | Steps = {d_acc['accessible_route']['steps_count']} flight(s)")
        print(f"  Reasons: {d_acc['reasons']}")
        results["4. Switch shortest vs accessible"] = "PASSED"
    except Exception as err:
        print(f"  FAILED: {err}")
        results["4. Switch shortest vs accessible"] = f"FAILED: {err}"

    # --------------------------------------------------------------------------
    # CRITERION 5: Submit a barrier, verify persistence & routing influence
    # --------------------------------------------------------------------------
    print("\n[TEST 5] Submitting barrier, verifying persistence and route influence...")
    try:
        seg_start = [12.971661, 77.595296]
        seg_end = [12.971682, 77.595303]

        # Pre-barrier baseline
        r_pre = requests.post(f"{BASE_URL}/api/route", json={"start": seg_start, "end": seg_end, "mode": "accessible"})
        dist_pre = r_pre.json()["accessible_route"]["distance_meters"]
        print(f"  Pre-barrier baseline distance: {dist_pre}m")

        # Submit barrier report
        barrier_report = {
            "lat": 12.97167185,
            "lon": 77.5952994,
            "category": "Broken ramp",
            "note": "Phase 3 acceptance test obstacle: high lip edge > 10cm"
        }
        r_barr = requests.post(f"{BASE_URL}/api/barriers", json=barrier_report)
        assert r_barr.status_code == 201, f"Barrier submission failed: {r_barr.text}"
        barrier_id = r_barr.json()["barrier"]["id"]
        print(f"  Barrier #{barrier_id} submitted and stored in SQLite database.")

        # Verify barrier is listed in GET /api/barriers
        r_list = requests.get(f"{BASE_URL}/api/barriers")
        assert r_list.status_code == 200
        barriers_list = r_list.json()["barriers"]
        assert any(b["id"] == barrier_id for b in barriers_list), f"Barrier #{barrier_id} not in GET /api/barriers!"
        print(f"  Barrier #{barrier_id} verified present in GET /api/barriers ({len(barriers_list)} total active).")

        # Recompute route and verify detour
        r_post = requests.post(f"{BASE_URL}/api/route", json={"start": seg_start, "end": seg_end, "mode": "accessible"})
        dist_post = r_post.json()["accessible_route"]["distance_meters"]
        print(f"  Post-barrier detour distance: {dist_post}m (detoured around obstacle: {dist_post > dist_pre})")
        assert dist_post > dist_pre, "Accessible route was not influenced by the new active barrier!"

        # Mark barrier resolved and verify restoration
        r_res = requests.patch(f"{BASE_URL}/api/barriers/{barrier_id}", json={"status": "resolved"})
        assert r_res.status_code == 200
        r_restored = requests.post(f"{BASE_URL}/api/route", json={"start": seg_start, "end": seg_end, "mode": "accessible"})
        dist_restored = r_restored.json()["accessible_route"]["distance_meters"]
        assert dist_restored == dist_pre, f"Route did not restore after resolution: {dist_restored} != {dist_pre}"
        print(f"  Barrier resolved. Route restored to baseline: {dist_restored}m.")
        results["5. Submit barrier & route influence"] = "PASSED"
    except Exception as err:
        print(f"  FAILED: {err}")
        results["5. Submit barrier & route influence"] = f"FAILED: {err}"

    # --------------------------------------------------------------------------
    # CRITERION 6: Test invalid location & location outside the graph
    # --------------------------------------------------------------------------
    print("\n[TEST 6] Testing invalid locations and out-of-bounds coordinates...")
    try:
        # 6A: Non-numeric / invalid coordinate
        r_inv = requests.post(f"{BASE_URL}/api/route", json={
            "start": ["invalid_lat", "not_a_lon"],
            "end": [12.9710, 77.5960]
        })
        assert r_inv.status_code == 400
        d_inv = r_inv.json()
        assert d_inv["success"] is False
        assert "numeric" in d_inv["error"].lower() or "coordinates" in d_inv["error"].lower()
        print(f"  Invalid coordinates correctly rejected with 400: '{d_inv['error']}'")

        # 6B: Location outside graph coverage (Paris, France)
        r_out = requests.post(f"{BASE_URL}/api/route", json={
            "start": [48.8566, 2.3522],
            "end": [12.9710, 77.5960]
        })
        assert r_out.status_code == 400
        d_out = r_out.json()
        assert d_out["success"] is False
        assert d_out["error_type"] == "OUT_OF_BOUNDS"
        assert "outside the loaded map coverage area" in d_out["error"]
        print(f"  Out-of-bounds location correctly rejected with OUT_OF_BOUNDS: {d_out['error'][:75]}...")
        results["6. Invalid & out-of-bounds rejection"] = "PASSED"
    except Exception as err:
        print(f"  FAILED: {err}")
        results["6. Invalid & out-of-bounds rejection"] = f"FAILED: {err}"

    # --------------------------------------------------------------------------
    # CRITERION 7: Confirm failures show honest error messages without demo routes
    # --------------------------------------------------------------------------
    print("\n[TEST 7] Confirming failure responses contain honest errors without fake demo routes...")
    try:
        test_cases = [
            {"start": [12.9710, 77.5960]}, # missing destination
            {"end": [12.9710, 77.5960]},   # missing start
            {"start": [51.5074, -0.1278], "end": [12.9710, 77.5960]}, # London
        ]
        for idx, tc in enumerate(test_cases, 1):
            r = requests.post(f"{BASE_URL}/api/route", json=tc)
            assert r.status_code == 400
            data = r.json()
            assert data["success"] is False
            assert "coordinates" not in data or data.get("coordinates") is None, f"Failure response leaked route coordinates!"
            assert "error" in data and len(data["error"]) > 5
            print(f"  Error Case {idx}: HTTP {r.status_code} -> '{data['error'][:60]}...' (No fake routes returned)")
        results["7. Honest error messages without demo routes"] = "PASSED"
    except Exception as err:
        print(f"  FAILED: {err}")
        results["7. Honest error messages without demo routes"] = f"FAILED: {err}"

    # --------------------------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------------------------
    print("\n" + "=" * 75)
    print("PHASE 3 FINAL ACCEPTANCE SUMMARY")
    print("=" * 75)
    all_passed = True
    for criterion, status in results.items():
        print(f"  {criterion.ljust(45)}: {status}")
        if status != "PASSED":
            all_passed = False
    print("=" * 75)
    if all_passed:
        print(">> ALL ACCEPTANCE CRITERIA PASSED SUCCESSFULLY! <<")
    else:
        print(">> ONE OR MORE ACCEPTANCE CRITERIA FAILED! <<")
    print("=" * 75)
    return all_passed

if __name__ == "__main__":
    run_acceptance_tests()
