"""
AccessAI - Map Data (Member 1)
Downloads and loads walking network data from OpenStreetMap using OSMnx.
Manages spatial bounds, area configuration, node proximity validation,
and dynamic walking network retrieval with local file and memory caching.
"""

import os
import glob
import math
import osmnx as ox

DEFAULT_FILE = 'map.graphml'
DEFAULT_PLACE = os.environ.get('ACCESSAI_PLACE', 'Cubbon Park & Central Campus, Bengaluru')
DEFAULT_POINT = (
    float(os.environ.get('ACCESSAI_CENTER_LAT', 12.9716)),
    float(os.environ.get('ACCESSAI_CENTER_LON', 77.5946))
)
DEFAULT_DIST = int(os.environ.get('ACCESSAI_DIST', 600))
MAX_ALLOWED_SNAP_DISTANCE_METERS = 500.0
MAX_SUPPORTED_WALK_DISTANCE_METERS = 25000.0  # 25 km max pedestrian route limit

# Cache directory for dynamically downloaded walking graphs
GRAPH_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'graph_cache')
os.makedirs(GRAPH_CACHE_DIR, exist_ok=True)

# In-memory graph cache to prevent redundant disk reads or network calls
_GRAPH_MEMORY_CACHE = {}
_BASE_GRAPH = None


def get_area_name():
    """Returns the human-readable area name for the default loaded graph."""
    return os.environ.get('ACCESSAI_PLACE', 'Cubbon Park & Central Campus, Bengaluru')


def _sanitize_graph_attributes(G):
    """Ensures numeric edge attributes (length, access_cost, base_access_cost) are floats."""
    for _, _, _, d in G.edges(keys=True, data=True):
        if 'length' in d:
            try:
                d['length'] = float(d['length'])
            except (ValueError, TypeError):
                d['length'] = 1.0
        if 'base_access_cost' in d:
            try:
                d['base_access_cost'] = float(d['base_access_cost'])
            except (ValueError, TypeError):
                d['base_access_cost'] = float(d.get('length', 1.0))
        if 'access_cost' in d:
            try:
                d['access_cost'] = float(d['access_cost'])
            except (ValueError, TypeError):
                d['access_cost'] = float(d.get('base_access_cost', d.get('length', 1.0)))
    return G


def load_graph(file_path=DEFAULT_FILE, place=None, center_point=None, dist=None):
    """
    Loads walking graph from GraphML file if available;
    otherwise downloads it via OSMnx and caches it locally.
    Registers the result into in-memory cache as base graph.
    """
    global _BASE_GRAPH
    if os.path.exists(file_path):
        G = ox.load_graphml(file_path)
        _sanitize_graph_attributes(G)
        _BASE_GRAPH = G
        _GRAPH_MEMORY_CACHE['base'] = G
        return G


    # If file doesn't exist, download walking network
    search_dist = dist or DEFAULT_DIST
    try:
        if center_point:
            G = ox.graph_from_point(center_point, dist=search_dist, network_type='walk')
        elif place:
            G = ox.graph_from_place(place, network_type='walk')
        else:
            G = ox.graph_from_point(DEFAULT_POINT, dist=search_dist, network_type='walk')

        ox.save_graphml(G, file_path)
        _BASE_GRAPH = G
        _GRAPH_MEMORY_CACHE['base'] = G
        return G
    except Exception as e:
        raise RuntimeError(
            f"Could not load or download walking graph from OpenStreetMap: {e}. "
            f"Check internet connection or specify a valid place name in ACCESSAI_PLACE."
        )


def get_base_graph():
    """Returns the base campus graph, loading it if not already initialized."""
    global _BASE_GRAPH
    if _BASE_GRAPH is None:
        _BASE_GRAPH = load_graph()
    return _BASE_GRAPH


def get_graph_bounds(G):
    """Returns minimum and maximum latitude and longitude of the graph nodes."""
    if G is None or len(G.nodes) == 0:
        return {
            'min_lat': 0.0, 'max_lat': 0.0,
            'min_lon': 0.0, 'max_lon': 0.0,
            'center_lat': 0.0, 'center_lon': 0.0,
            'area_name': get_area_name()
        }
    lats = [G.nodes[n]['y'] for n in G.nodes]
    lons = [G.nodes[n]['x'] for n in G.nodes]
    return {
        'min_lat': min(lats),
        'max_lat': max(lats),
        'min_lon': min(lons),
        'max_lon': max(lons),
        'center_lat': sum(lats) / len(lats),
        'center_lon': sum(lons) / len(lons),
        'area_name': get_area_name()
    }


def is_point_within_graph(G, lat, lon, max_distance_meters=MAX_ALLOWED_SNAP_DISTANCE_METERS):
    """
    Checks if a given coordinate is close enough to the loaded walking network.
    Returns:
        (is_inside: bool, distance_meters: float, nearest_node_id: int)
    """
    if G is None or len(G.nodes) == 0:
        return (False, float('inf'), None)

    try:
        nearest_node = ox.distance.nearest_nodes(G, X=lon, Y=lat)
        node_lat = float(G.nodes[nearest_node]['y'])
        node_lon = float(G.nodes[nearest_node]['x'])
        dist = ox.distance.great_circle(lat, lon, node_lat, node_lon)
        return (dist <= max_distance_meters, round(dist, 1), nearest_node)
    except Exception:
        return (False, float('inf'), None)



def get_graph_for_route(start_coords, end_coords, max_walk_distance_meters=MAX_SUPPORTED_WALK_DISTANCE_METERS):
    """
    Dynamically obtains an appropriate walking network covering start and destination.
    1. Checks if the base graph (Cubbon Park) covers both points.
    2. Checks in-memory cache and disk cache for any graph covering both points.
    3. If not covered, downloads the walking network from OpenStreetMap via OSMnx,
       annotates accessibility costs, applies active barriers, and saves to graph_cache/.
    Returns: (graph: nx.MultiDiGraph, info: dict)
    """
    try:
        start_lat = float(start_coords[0])
        start_lon = float(start_coords[1])
        end_lat = float(end_coords[0])
        end_lon = float(end_coords[1])
    except (ValueError, TypeError, IndexError):
        raise ValueError("Invalid coordinates provided. Must be numeric (lat, lon) pairs.")

    straight_dist = ox.distance.great_circle(start_lat, start_lon, end_lat, end_lon)
    if straight_dist > max_walk_distance_meters:
        # Import lazily to avoid circular dependency
        from routing import OutOfBoundsLocationError
        dist_km = straight_dist / 1000.0
        max_km = max_walk_distance_meters / 1000.0
        raise OutOfBoundsLocationError(
            f"Start ({start_lat:.4f}, {start_lon:.4f}) and Destination ({end_lat:.4f}, {end_lon:.4f}) "
            f"are {dist_km:.1f} km apart, which is outside the loaded map coverage area and exceeds "
            f"the maximum supported pedestrian routing distance of {int(max_km)} km. "
            f"Loaded area: '{get_area_name()}'. Please select locations within walkable reach."
        )

    # 1. Check if the default base graph covers both points
    base_g = get_base_graph()
    cov_s, dist_s, _ = is_point_within_graph(base_g, start_lat, start_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
    cov_e, dist_e, _ = is_point_within_graph(base_g, end_lat, end_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
    if cov_s and cov_e:
        return base_g, {
            'source': 'base_graph',
            'cached': True,
            'area_name': get_area_name()
        }

    # 2. Check in-memory cached graphs
    for key, cached_g in _GRAPH_MEMORY_CACHE.items():
        if key == 'base':
            continue
        c_s, _, _ = is_point_within_graph(cached_g, start_lat, start_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
        c_e, _, _ = is_point_within_graph(cached_g, end_lat, end_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
        if c_s and c_e:
            return cached_g, {
                'source': 'memory_cache',
                'cached': True,
                'area_name': f"Cached Area ({key})"
            }

    # 3. Check disk cache files in graph_cache/
    for fpath in glob.glob(os.path.join(GRAPH_CACHE_DIR, '*.graphml')):
        fname = os.path.basename(fpath)
        if fname not in _GRAPH_MEMORY_CACHE:
            try:
                disk_g = ox.load_graphml(fpath)
                _sanitize_graph_attributes(disk_g)
                _GRAPH_MEMORY_CACHE[fname] = disk_g
            except Exception as e:
                print(f"Notice: Could not load cached graph {fname}: {e}")
                continue

        candidate_g = _GRAPH_MEMORY_CACHE.get(fname)
        if candidate_g:
            c_s, _, _ = is_point_within_graph(candidate_g, start_lat, start_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
            c_e, _, _ = is_point_within_graph(candidate_g, end_lat, end_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
            if c_s and c_e:
                return candidate_g, {
                    'source': 'disk_cache',
                    'cached': True,
                    'area_name': f"Disk Cached Area ({fname})"
                }

    # 4. Not covered in any cache: Dynamically download walking network via OSMnx
    center_lat = (start_lat + end_lat) / 2.0
    center_lon = (start_lon + end_lon) / 2.0
    # Determine search radius: generous padding around both points (min 900m)
    radius_m = int(max(straight_dist + 500.0, 900.0))


    print(f"Dynamically loading walking network around ({center_lat:.5f}, {center_lon:.5f}) with radius {radius_m}m...")

    try:
        # Note: ox.graph_from_point expects center_point as (latitude, longitude)
        G_new = ox.graph_from_point((center_lat, center_lon), dist=radius_m, network_type='walk')
    except Exception as exc:
        raise RuntimeError(
            f"Could not download walking network from OpenStreetMap for ({center_lat:.4f}, {center_lon:.4f}): {exc}. "
            f"Please verify your connection and coordinates."
        )

    if len(G_new.nodes) == 0:
        raise RuntimeError(
            f"No walkable paths found for the selected area around ({center_lat:.4f}, {center_lon:.4f}) in OpenStreetMap."
        )

    # Initialize edge accessibility weights (penalize stairs, rough surfaces, wheelchair=no)
    from routing import add_costs
    add_costs(G_new)

    # Apply any active community barriers to the new graph
    from barriers import apply_all
    apply_all(G_new)

    # Save to disk cache
    cache_fname = f"graph_{center_lat:.4f}_{center_lon:.4f}_{radius_m}m.graphml"
    cache_path = os.path.join(GRAPH_CACHE_DIR, cache_fname)
    try:
        ox.save_graphml(G_new, cache_path)
    except Exception as save_err:
        print(f"Notice: Failed to persist graph to {cache_fname}: {save_err}")

    # Register in memory cache
    _GRAPH_MEMORY_CACHE[cache_fname] = G_new

    # Verify that the downloaded graph actually snaps both locations within tolerance
    cov_s_new, dist_s_new, _ = is_point_within_graph(G_new, start_lat, start_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
    cov_e_new, dist_e_new, _ = is_point_within_graph(G_new, end_lat, end_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)

    from routing import OutOfBoundsLocationError
    if not cov_s_new:
        dist_desc = f"{int(dist_s_new)}m" if not math.isinf(dist_s_new) else "far"
        raise OutOfBoundsLocationError(
            f"Start location ({start_lat:.5f}, {start_lon:.5f}) is {dist_desc} away from the nearest "
            f"mapped walking path in OpenStreetMap (maximum supported distance is {int(MAX_ALLOWED_SNAP_DISTANCE_METERS)}m). "
            f"Please select a location closer to a public road or pedestrian footpath."
        )
    if not cov_e_new:
        dist_desc = f"{int(dist_e_new)}m" if not math.isinf(dist_e_new) else "far"
        raise OutOfBoundsLocationError(
            f"Destination ({end_lat:.5f}, {end_lon:.5f}) is {dist_desc} away from the nearest "
            f"mapped walking path in OpenStreetMap (maximum supported distance is {int(MAX_ALLOWED_SNAP_DISTANCE_METERS)}m). "
            f"Please select a location closer to a public road or pedestrian footpath."
        )


    return G_new, {
        'source': 'osm_dynamic_download',
        'cached': False,
        'area_name': f"Dynamic Area ({center_lat:.4f}, {center_lon:.4f})",
        'radius_m': radius_m,
        'nodes': len(G_new.nodes),
        'edges': len(G_new.edges)
    }


if __name__ == '__main__':
    G = load_graph()
    bounds = get_graph_bounds(G)
    print(f"Loaded graph: {len(G.nodes)} nodes, {len(G.edges)} edges")
    print(f"Area: {bounds['area_name']}")
    print(f"Center: ({bounds['center_lat']:.4f}, {bounds['center_lon']:.4f})")
    print(f"Bounds: Lat [{bounds['min_lat']:.4f}, {bounds['max_lat']:.4f}], Lon [{bounds['min_lon']:.4f}, {bounds['max_lon']:.4f}]")
