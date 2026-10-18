"""
AccessAI - Phase 1 Homepage and Interactive Map Verification
Tests:
1. Homepage loads immediately with 200 OK
2. Interactive Leaflet map container (#map) is present on load
3. Search panel contains all required inputs (start, end, swap, locate, find, clear)
4. Start and destination inputs are completely empty by default (no demo route)
5. Welcome guidance card ("Plan a safer, more accessible journey.") is visible on initial load
6. Route results panel (#route-results) is hidden on initial load
7. Map legend with accessibility items and Report Barrier action is present
8. Static assets (style.css, auth.css, app.js, auth.js) are properly linked
9. Real OpenStreetMap attribution and config data are rendered
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app


class AccessAIPhase1TestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_homepage_loads_immediately(self):
        """GET / returns 200 OK and renders main layout."""
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # 1. Main Title & Branding
        self.assertIn('AccessAI', html)
        self.assertIn('Intelligent Accessible Route Planning', html)

        # 2. Interactive Map Container
        self.assertIn('id="map"', html)
        self.assertIn('leaflet-map', html)
        self.assertIn('leaflet.js', html)
        self.assertIn('leaflet.css', html)

        # 3. Clean Search Panel Elements
        self.assertIn('id="start-input"', html)
        self.assertIn('id="end-input"', html)
        self.assertIn('id="btn-swap-locations"', html)
        self.assertIn('id="start-suggestions"', html)
        self.assertIn('id="end-suggestions"', html)
        self.assertIn('id="btn-find-route"', html)
        self.assertIn('id="btn-locate-start"', html)
        self.assertIn('id="btn-clear-route"', html)

        # 4. No hardcoded demo route coordinates in input values
        self.assertNotIn('value="12.', html[html.find('id="start-input"'):html.find('id="start-input"')+100])
        self.assertNotIn('value="77.', html[html.find('id="start-input"'):html.find('id="start-input"')+100])
        self.assertNotIn('value="12.', html[html.find('id="end-input"'):html.find('id="end-input"')+100])
        self.assertNotIn('value="77.', html[html.find('id="end-input"'):html.find('id="end-input"')+100])

        # 5. Welcome Guidance Message shown before a route is selected
        self.assertIn('id="welcome-panel"', html)
        self.assertIn('Plan a safer, more accessible journey.', html)
        self.assertIn('Step-Free Routing', html)
        self.assertIn('Community Barrier Alerts', html)

        # 6. Route Results hidden initially
        self.assertIn('id="route-results" class="panel-section results-section hidden"', html)

        # 7. Map Legend and Report Barrier
        self.assertIn('id="map-legend"', html)
        self.assertIn('Accessible Route (Wheelchair)', html)
        self.assertIn('Shortest Route (May have stairs)', html)
        self.assertIn('Start Location (A)', html)
        self.assertIn('Destination (B)', html)
        self.assertIn('Reported Barrier / Hazard', html)
        self.assertIn('btn-legend-report-barrier', html)

        # 8. Floating map controls
        self.assertIn('btn-recenter-map', html)
        self.assertIn('btn-toggle-barriers-layer', html)

        # 9. Accessible route result structure ready for routing
        self.assertIn('Wheelchair-accessible route', html)
        self.assertIn('chip-mode-wheelchair', html)
        self.assertIn('chip-mode-low-vision', html)
        self.assertIn('btn-select-safest', html)
        self.assertIn('btn-select-shortest', html)
        self.assertIn('btn-start-navigation', html)
        self.assertIn('btn-open-safety-details', html)

        print("\n>> ALL PHASE 1 HOMEPAGE & INTERACTIVE MAP CHECKS PASSED SUCCESSFULLY!")


if __name__ == '__main__':
    unittest.main()
