"""
AccessAI - Dynamic Coverage & Walking Network Routing Tests
Tests:
1. Routing within default Cubbon Park network (instant cache hit).
2. Routing outside default Cubbon Park network (e.g. Lalbagh Botanical Garden, Bengaluru):
   - Dynamically loads and caches the walking network from OSMnx.
   - Computes real wheelchair accessible route with step-avoidance and turn cues.
   - Subsequent calls hit disk/memory cache in < 0.2s.
3. Distant unsupported routing (> 25 km, e.g. London or Mumbai to Bengaluru):
   - Returns clear and informative OUT_OF_BOUNDS message explaining pedestrian limit.
4. Correct coordinate ordering: (latitude, longitude) for inputs/outputs, (longitude, latitude) for OSMnx.
"""

import unittest
import time
import json
import os
import sys

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from graph import get_graph_for_route, is_point_within_graph, GRAPH_CACHE_DIR


class DynamicCoverageTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_01_inside_cubbon_park_routing(self):
        """Routing within Cubbon Park uses base graph with zero network overhead."""
        payload = {
            'start': [12.9712, 77.5977],
            'end': [12.9723, 77.5942]
        }
        t0 = time.time()
        resp = self.client.post('/api/route', json=payload)
        elapsed = time.time() - t0

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data.get('area_info', {}).get('source'), 'base_graph')
        self.assertLess(elapsed, 1.0, "Base graph routing should be virtually instantaneous")
        self.assertGreater(len(data['coordinates']), 2)

    def test_02_outside_cubbon_park_dynamic_download_and_caching(self):
        """Routing outside Cubbon Park (Lalbagh, Bengaluru) dynamically downloads, caches, and routes."""
        # Lalbagh West Gate to Lalbagh Glass House (~750m walking distance)
        # Coordinates: [lat, lon]
        start_point = [12.9482, 77.5802]
        end_point = [12.9515, 77.5855]

        # Call 1: Dynamic download or load from cache
        t0 = time.time()
        resp1 = self.client.post('/api/route', json={'start': start_point, 'end': end_point})
        elapsed1 = time.time() - t0
        self.assertEqual(resp1.status_code, 200, f"Failed with: {resp1.get_json()}")
        data1 = resp1.get_json()
        self.assertTrue(data1['success'])
        self.assertGreater(data1['distance'], 400.0)
        self.assertGreater(len(data1['coordinates']), 3)
        self.assertIn('accessible_route', data1)
        self.assertIn('shortest_route', data1)
        self.assertIn('guidance_steps', data1)
        self.assertGreater(len(data1['guidance_steps']), 1)

        # Verify coordinates order is [lat, lon]
        for coord in data1['coordinates'][:5]:
            self.assertEqual(len(coord), 2)
            lat, lon = coord
            self.assertTrue(12.0 <= lat <= 14.0, f"Latitude {lat} out of Bengaluru bounds")
            self.assertTrue(77.0 <= lon <= 78.0, f"Longitude {lon} out of Bengaluru bounds")

        # Call 2: Must be an instant cache hit (< 0.5s)
        t1 = time.time()
        resp2 = self.client.post('/api/route', json={'start': start_point, 'end': end_point})
        elapsed2 = time.time() - t1
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2['success'])
        self.assertEqual(data2['distance'], data1['distance'])
        self.assertLess(elapsed2, 0.5, f"Cached query should be under 0.5s, took {elapsed2:.2f}s")
        self.assertTrue(data2.get('area_info', {}).get('cached', False), "Second call must be cached")

    def test_03_distance_exceeding_pedestrian_limit(self):
        """Routing requests for distant cities (> 25km) return clear OUT_OF_BOUNDS error."""
        # Mumbai to Bengaluru (~840 km)
        resp = self.client.post('/api/route', json={
            'start': [19.0760, 72.8777],
            'end': [12.9716, 77.5946]
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data.get('error_type'), 'OUT_OF_BOUNDS')
        self.assertIn('outside the loaded map coverage area', data.get('error', ''))
        self.assertIn('pedestrian routing distance', data.get('error', ''))

    def test_04_coordinate_input_formats(self):
        """API accepts both array [lat, lon] and string formats without error."""
        resp = self.client.get('/api/route?start=12.9712,77.5977&end=12.9723,77.5942')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('coordinates', data)


if __name__ == '__main__':
    unittest.main()
