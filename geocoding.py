"""
AccessAI - Geocoding Service
Provides place name to coordinate resolution and search suggestions via OpenStreetMap Nominatim.
Adheres strictly to Nominatim Usage Policy:
- Custom, identifiable User-Agent with contact information.
- Rate limiting (minimum 1.0 second between upstream requests).
- Local in-memory caching to avoid redundant queries.
"""

import time
import threading
import urllib.parse
import urllib.request
import json
import logging

logger = logging.getLogger(__name__)

# Nominatim Usage Policy Compliance
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AccessAI-AccessibleNavigation/1.0 (contact: arjun.accessai@local.dev)"
MIN_REQUEST_INTERVAL = 1.1  # Seconds between outbound calls to respect Nominatim rate limit

_last_request_time = 0.0
_request_lock = threading.Lock()
_cache = {}


def _rate_limit():
    """Enforces minimum interval between outbound requests to Nominatim."""
    global _last_request_time
    with _request_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            sleep_duration = MIN_REQUEST_INTERVAL - elapsed
            time.sleep(sleep_duration)
        _last_request_time = time.time()


def geocode_place(query, bounds=None, limit=5):
    """
    Geocodes a place name into coordinates.
    Optionally biases results toward graph bounds.
    Returns a list of candidate dictionaries:
    [
        {
            "display_name": "...",
            "lat": float,
            "lon": float,
            "type": "...",
            "importance": float,
            "in_graph_bounds": bool
        }
    ]
    """
    query = query.strip()
    if not query:
        return []

    cache_key = f"{query.lower()}_{bounds}"
    if cache_key in _cache:
        return _cache[cache_key]

    params = {
        'q': query,
        'format': 'json',
        'addressdetails': 1,
        'limit': limit
    }

    if bounds:
        # viewbox=<left>,<top>,<right>,<bottom> = min_lon, max_lat, max_lon, min_lat
        params['viewbox'] = f"{bounds['min_lon']},{bounds['max_lat']},{bounds['max_lon']},{bounds['min_lat']}"
        params['bounded'] = 0  # Prefer within box, but don't completely exclude if not found

    url = f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': USER_AGENT,
            'Accept': 'application/json'
        }
    )

    _rate_limit()

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status != 200:
                logger.warning(f"Nominatim returned status {response.status}")
                return []
            raw_data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Geocoding network error for query '{query}': {e}")
        return []

    results = []
    for item in raw_data:
        try:
            lat = float(item['lat'])
            lon = float(item['lon'])
            in_bounds = True
            if bounds:
                in_bounds = (
                    bounds['min_lat'] <= lat <= bounds['max_lat'] and
                    bounds['min_lon'] <= lon <= bounds['max_lon']
                )

            results.append({
                'display_name': item.get('display_name', query),
                'lat': lat,
                'lon': lon,
                'type': item.get('type', 'place'),
                'class': item.get('class', 'place'),
                'importance': float(item.get('importance', 0.0)),
                'in_graph_bounds': in_bounds
            })
        except (ValueError, KeyError):
            continue

    _cache[cache_key] = results
    return results
