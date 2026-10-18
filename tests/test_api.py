"""
AccessAI - Backend API and Routing Integration Tests
Tests Flask endpoints, barrier reporting, route computation, geocoding,
and spatial boundary validation.
"""

import unittest
import json
import os
import sys

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from models import db, BarrierReport


class AccessAIApiTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

        with app.app_context():
            db.create_all()
            b = BarrierReport(
                latitude=12.9716,
                longitude=77.5946,
                category='Stairs',
                description='Test flight of steps',
                status='active',
                verification_status='verified'
            )
            db.session.add(b)
            db.session.commit()
            self.test_barrier_id = b.id

    def tearDown(self):
        with app.app_context():
            try:
                b = db.session.get(BarrierReport, self.test_barrier_id)
                if b:
                    db.session.delete(b)
                # Clean up any barriers added during the tests
                test_barriers = BarrierReport.query.filter(BarrierReport.description.like('%test%')).all()
                for tb in test_barriers:
                    db.session.delete(tb)
                db.session.commit()
            except Exception:
                db.session.rollback()
            db.session.remove()

    def test_health_check(self):
        """GET /api/health returns healthy status, graph bounds, and area info."""
        resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('graph', data)
        self.assertGreater(data['graph']['nodes'], 0)
        self.assertGreater(data['graph']['edges'], 0)
        self.assertIn('area_name', data['graph'])

    def test_map_info_endpoint(self):
        """GET /api/map-info returns spatial boundaries and coverage information."""
        resp = self.client.get('/api/map-info')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('bounds', data)
        self.assertIn('min_lat', data['bounds'])
        self.assertIn('max_lat', data['bounds'])
        self.assertIn('min_lon', data['bounds'])
        self.assertIn('max_lon', data['bounds'])
        self.assertEqual(data['max_snap_distance_meters'], 350.0)

    def test_geocode_endpoint(self):
        """GET /api/geocode returns structured search results with boundary checks."""
        resp = self.client.get('/api/geocode?q=Cubbon+Park')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('results', data)
        if len(data['results']) > 0:
            first = data['results'][0]
            self.assertIn('lat', first)
            self.assertIn('lon', first)
            self.assertIn('in_graph_bounds', first)

    def test_geocode_empty_query(self):
        """GET /api/geocode with empty query returns 400."""
        resp = self.client.get('/api/geocode?q=')
        self.assertEqual(resp.status_code, 400)

    def test_get_barriers(self):
        """GET /api/barriers returns list of active barriers."""
        resp = self.client.get('/api/barriers')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertGreaterEqual(len(data['barriers']), 1)
        self.assertEqual(data['barriers'][0]['category'], 'Stairs')

    def test_post_barrier_success(self):
        """POST /api/barriers successfully saves a new barrier and applies penalty."""
        payload = {
            'lat': 12.9730,
            'lon': 77.5950,
            'category': 'Construction',
            'note': 'Sidewalk closed due to cable trenching'
        }
        resp = self.client.post(
            '/api/barriers',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['barrier']['category'], 'Construction')
        self.assertEqual(data['barrier']['lat'], 12.9730)

    def test_post_barrier_invalid_coords(self):
        """POST /api/barriers rejects non-numeric or out-of-range coordinates."""
        payload = {
            'lat': 'not-a-number',
            'lon': 77.5950,
            'category': 'Stairs'
        }
        resp = self.client.post(
            '/api/barriers',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])

    def test_patch_barrier_resolve(self):
        """PATCH /api/barriers/<id> resolves a barrier so it stops penalizing routes."""
        resp = self.client.patch(
            f'/api/barriers/{self.test_barrier_id}',
            data=json.dumps({'status': 'resolved'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'resolved')

    def test_route_calculation_real_locations(self):
        """POST /api/route returns accessible route coordinates and comparison for real coordinates."""
        payload = {
            'start': [12.9712, 77.5977],
            'end': [12.9723, 77.5942]
        }
        resp = self.client.post(
            '/api/route',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('accessible_route', data)
        self.assertIn('shortest_route', data)
        self.assertGreater(len(data['accessible_route']['coordinates']), 1)
        self.assertGreater(data['accessible_route']['distance_meters'], 0)
        self.assertGreater(data['accessible_route']['duration_minutes'], 0)
        self.assertIn('reasons', data)
        self.assertIn('warnings', data)

    def test_route_out_of_bounds_rejection(self):
        """POST /api/route strictly rejects coordinates outside the loaded map coverage area."""
        # London coordinates (far away from Bengaluru campus)
        payload = {
            'start': [51.5074, -0.1278],
            'end': [12.9723, 77.5942]
        }
        resp = self.client.post(
            '/api/route',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data.get('error_type'), 'OUT_OF_BOUNDS')
        self.assertIn('outside the loaded map coverage area', data.get('error', ''))
        self.assertIn('loaded_area', data)

    def test_route_missing_parameters(self):
        """POST /api/route returns 400 when start or end is missing."""
        resp = self.client.post(
            '/api/route',
            data=json.dumps({'start': [12.9712, 77.5977]}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])

    def test_route_mode_selection(self):
        """POST /api/route supports mode='accessible' and mode='shortest'."""
        payload = {
            'start': [12.9712, 77.5977],
            'end': [12.9723, 77.5942],
            'mode': 'shortest'
        }
        resp = self.client.post('/api/route', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['route_mode'], 'shortest')
        self.assertEqual(data['distance'], data['shortest_route']['distance_meters'])

    def test_route_get_request(self):
        """GET /api/route works with query parameters."""
        resp = self.client.get('/api/route?start=12.9712,77.5977&end=12.9723,77.5942&mode=accessible')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['route_mode'], 'accessible')
        self.assertIn('coordinates', data)
        self.assertGreater(len(data['coordinates']), 1)

    def test_barrier_penalty_non_accumulation(self):
        """Repeated routing requests reset and rebuild costs without inflating edge weights."""
        from app import G
        from barriers import refresh_graph_costs

        with app.app_context():
            refresh_graph_costs(G)
            max_cost_1 = max(d.get('access_cost', 0) for _, _, _, d in G.edges(keys=True, data=True))

        # Perform 5 consecutive routing calls
        payload = {'start': [12.9712, 77.5977], 'end': [12.9723, 77.5942]}
        for _ in range(5):
            resp = self.client.post('/api/route', data=json.dumps(payload), content_type='application/json')
            self.assertEqual(resp.status_code, 200)

        with app.app_context():
            max_cost_2 = max(d.get('access_cost', 0) for _, _, _, d in G.edges(keys=True, data=True))

        # The maximum cost should remain identical and not accumulate
        self.assertEqual(max_cost_1, max_cost_2)

    def test_stairs_avoidance_routing(self):
        """Accessible routing avoids mapped stairs while standard shortest path uses them."""
        payload = {
            'start': [12.9677227, 77.5926506],
            'end': [12.9678777, 77.5927888],
            'mode': 'both'
        }
        resp = self.client.post('/api/route', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        short = data['shortest_route']
        acc = data['accessible_route']

        self.assertGreaterEqual(short['steps_count'], 1, "Shortest route should include the stairs")
        self.assertEqual(acc['steps_count'], 0, "Accessible route should avoid all stairs")
        self.assertGreater(acc['distance_meters'], short['distance_meters'], "Accessible detour should be longer than direct stairs")
        self.assertTrue(any('stair' in r.lower() for r in data['reasons']))


if __name__ == '__main__':
    unittest.main()

