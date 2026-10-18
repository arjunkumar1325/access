"""
AccessAI - Accessibility Routing Engine (Member 2)
Computes accessible walking routes by prioritizing wheelchair-friendly footpaths,
penalizing stairs, wheelchair=no restrictions, rough surfaces, and reported barriers.
Handles MultiDiGraph edges correctly, extracts real polyline geometries, and enforces
strict spatial boundaries, non-negative costs, and transparent accessibility notices.
"""

import math
import networkx as nx
import osmnx as ox
from graph import get_graph_bounds, get_area_name

BIG = 10000.0
ROUGH = (
    'gravel', 'sand', 'dirt', 'grass', 'cobblestone', 'unpaved',
    'ground', 'earth', 'mud', 'fine_gravel', 'compacted', 'pebblestone'
)
WHEELCHAIR_SPEED_MPS = 1.0  # Approx. 3.6 km/h (moderate wheelchair navigation speed)
MAX_ALLOWED_SNAP_DISTANCE_METERS = 500.0  # Maximum distance to snap a coordinate to nearest path



class OutOfBoundsLocationError(ValueError):
    """Raised when a coordinate is outside the loaded graph's coverage area."""
    pass


class DisconnectedNetworkError(ValueError):
    """Raised when no connected path exists between two graph nodes."""
    pass


def edge_cost(d):
    """
    Calculates accessibility cost for a street/footpath edge.
    Validates tags, handles list-valued attributes, and ensures non-negative cost.
    """
    length = float(d.get('length', 1.0))
    if math.isnan(length) or length < 0:
        length = 1.0
    cost = max(0.1, length)

    # 1. Check highway tag (string or list)
    hw = d.get('highway')
    hw_list = [h.lower() for h in hw] if isinstance(hw, list) else [str(hw or '').lower()]
    if 'steps' in hw_list:
        cost += BIG

    # 2. Check wheelchair tag (string or list)
    wc = d.get('wheelchair')
    wc_list = [w.lower() for w in wc] if isinstance(wc, list) else [str(wc or '').lower()]
    if 'no' in wc_list:
        cost += BIG
    elif 'limited' in wc_list:
        cost += 500.0  # Moderate penalty for limited accessibility (e.g. assistance needed)
    elif 'designated' in wc_list or 'yes' in wc_list:
        cost *= 0.95   # Slight preference for verified accessible paths

    # 3. Check surface tag (string or list)
    surf = d.get('surface')
    surf_list = [s.lower() for s in surf] if isinstance(surf, list) else [str(surf or '').lower()]
    if any(s in ROUGH for s in surf_list):
        cost *= 1.8

    # 4. Check pedestrian access / foot tag
    foot = d.get('foot')
    foot_list = [f.lower() for f in foot] if isinstance(foot, list) else [str(foot or '').lower()]
    if any(f in ('no', 'private', 'prohibited') for f in foot_list):
        cost += BIG

    # 5. Barrier tag on edge
    barrier = d.get('barrier')
    barrier_list = [b.lower() for b in barrier] if isinstance(barrier, list) else [str(barrier or '').lower()]
    if any(b in ('stile', 'turnstile', 'chain', 'fence') for b in barrier_list):
        cost += BIG

    # Ensure strictly positive and non-negative
    return max(0.1, cost)


def add_costs(G):
    """
    Annotates all graph edges with 'base_access_cost' and 'access_cost'.
    Resets any temporary barrier penalties to ensure a clean base graph.
    """
    for u, v, k, d in G.edges(keys=True, data=True):
        cost = edge_cost(d)
        d['base_access_cost'] = cost
        d['access_cost'] = cost


def _validate_and_snap(G, lat, lon, label="Location"):
    """
    Validates a coordinate and ensures it is within the loaded graph area.
    Returns (nearest_node_id, distance_meters).
    Raises OutOfBoundsLocationError if outside the coverage area.
    """
    bounds = get_graph_bounds(G)
    area = bounds.get('area_name', 'Loaded Walking Network')

    try:
        nearest_node = ox.distance.nearest_nodes(G, X=lon, Y=lat)
    except Exception as e:
        raise ValueError(f"Could not locate graph nodes near {label} ({lat}, {lon}): {e}")

    node_lat = float(G.nodes[nearest_node]['y'])
    node_lon = float(G.nodes[nearest_node]['x'])
    dist = ox.distance.great_circle(lat, lon, node_lat, node_lon)

    if dist > MAX_ALLOWED_SNAP_DISTANCE_METERS:
        raise OutOfBoundsLocationError(
            f"{label} ({lat:.5f}, {lon:.5f}) is outside the loaded map coverage area. "
            f"It is {int(dist)}m away from the nearest mapped footpath "
            f"(maximum supported distance is {int(MAX_ALLOWED_SNAP_DISTANCE_METERS)}m).\n"
            f"Currently loaded area: '{area}' "
            f"[Lat: {bounds['min_lat']:.4f} to {bounds['max_lat']:.4f}, "
            f"Lon: {bounds['min_lon']:.4f} to {bounds['max_lon']:.4f}].\n"
            f"Please select a location closer to a public road or pedestrian footpath."
        )

    return nearest_node, dist



def _extract_path_coordinates(G, node_path, weight_attr='access_cost'):
    """
    Extracts real street polyline coordinates from the traversed MultiDiGraph edges.
    Preserves curve geometry when available in OpenStreetMap data, returning coordinates
    consistently in (latitude, longitude) order.
    """
    coords = []
    for i in range(len(node_path) - 1):
        u = node_path[i]
        v = node_path[i + 1]
        edge_dict = G.get_edge_data(u, v)
        if not edge_dict:
            coords.append((float(G.nodes[u]['y']), float(G.nodes[u]['x'])))
            continue

        # Select the specific edge key with the minimum weight in the MultiDiGraph
        best_k = min(edge_dict.keys(), key=lambda k: edge_dict[k].get(weight_attr, float('inf')))
        d = edge_dict[best_k]

        geom = d.get('geometry')
        if geom is not None and hasattr(geom, 'coords'):
            # LineString coordinates are (lon, lat) in Shapely; convert to (lat, lon)
            edge_coords = [(float(y), float(x)) for x, y in geom.coords]
            if coords and edge_coords and coords[-1] == edge_coords[0]:
                coords.extend(edge_coords[1:])
            else:
                coords.extend(edge_coords)
        else:
            pt_u = (float(G.nodes[u]['y']), float(G.nodes[u]['x']))
            pt_v = (float(G.nodes[v]['y']), float(G.nodes[v]['x']))
            if not coords or coords[-1] != pt_u:
                coords.append(pt_u)
            coords.append(pt_v)

    if not coords and node_path:
        coords = [(float(G.nodes[n]['y']), float(G.nodes[n]['x'])) for n in node_path]

    return coords


def _path_metrics(G, node_path, weight_attr='access_cost'):
    """Calculates distance, time, and flags (stairs, rough surface) along a node path."""
    total_length = 0.0
    total_cost = 0.0
    steps_count = 0
    wheelchair_no_count = 0
    wheelchair_unverified_count = 0
    rough_surface_count = 0
    streets_used = []

    for i in range(len(node_path) - 1):
        u = node_path[i]
        v = node_path[i + 1]
        edge_dict = G.get_edge_data(u, v)
        if not edge_dict:
            continue

        best_k = min(edge_dict.keys(), key=lambda k: edge_dict[k].get(weight_attr, float('inf')))
        d = edge_dict[best_k]

        edge_len = max(0.0, float(d.get('length', 0.0)))
        total_length += edge_len
        total_cost += float(d.get(weight_attr, edge_len))

        # Check steps
        hw = d.get('highway')
        hw_list = [h.lower() for h in hw] if isinstance(hw, list) else [str(hw or '').lower()]
        if 'steps' in hw_list:
            steps_count += 1

        # Check wheelchair tag
        wc = d.get('wheelchair')
        if wc is None:
            wheelchair_unverified_count += 1
        else:
            wc_list = [w.lower() for w in wc] if isinstance(wc, list) else [str(wc).lower()]
            if 'no' in wc_list:
                wheelchair_no_count += 1

        # Check surface tag
        surf = d.get('surface')
        surf_list = [s.lower() for s in surf] if isinstance(surf, list) else [str(surf or '').lower()]
        if any(s in ROUGH for s in surf_list):
            rough_surface_count += 1

        name = d.get('name')
        if isinstance(name, list):
            name = name[0]
        if name and name not in streets_used:
            streets_used.append(str(name))

    duration_seconds = total_length / WHEELCHAIR_SPEED_MPS if WHEELCHAIR_SPEED_MPS > 0 else 0
    duration_minutes = math.ceil(duration_seconds / 60.0)

    guidance = _generate_guidance_steps(G, node_path, weight_attr=weight_attr)

    return {
        'distance_meters': round(total_length, 1),
        'duration_minutes': duration_minutes,
        'duration_seconds': round(duration_seconds),
        'speed_basis': f"Estimated at {WHEELCHAIR_SPEED_MPS} m/s (moderate wheelchair speed)",
        'steps_count': steps_count,
        'wheelchair_no_count': wheelchair_no_count,
        'wheelchair_unverified_count': wheelchair_unverified_count,
        'rough_surface_count': rough_surface_count,
        'total_cost': round(total_cost, 1),
        'streets': streets_used,
        'guidance_steps': guidance
    }


def _calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculates forward compass bearing between two geographic points in degrees."""
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _turn_label(b1, b2):
    """Determines turn direction phrase and icon type from bearing difference."""
    diff = (b2 - b1 + 360) % 360
    if diff > 180:
        diff -= 360
    if abs(diff) < 25:
        return "Continue straight", "straight"
    elif 25 <= diff < 70:
        return "Bear slightly right", "slight_right"
    elif 70 <= diff < 120:
        return "Turn right", "right"
    elif diff >= 120:
        return "Make a sharp right", "sharp_right"
    elif -70 < diff <= -25:
        return "Bear slightly left", "slight_left"
    elif -120 < diff <= -70:
        return "Turn left", "left"
    else:
        return "Make a sharp left", "sharp_left"


def _generate_guidance_steps(G, node_path, weight_attr='access_cost'):
    """Generates real step-by-step navigation cues along the route edges."""
    if not node_path or len(node_path) < 2:
        return []

    raw_steps = []
    current_name = None
    accum_dist = 0.0
    accum_coords = []
    prev_bearing = None

    for i in range(len(node_path) - 1):
        u = node_path[i]
        v = node_path[i + 1]
        edge_dict = G.get_edge_data(u, v)
        if not edge_dict:
            continue
        best_k = min(edge_dict.keys(), key=lambda k: edge_dict[k].get(weight_attr, float('inf')))
        d = edge_dict[best_k]

        edge_len = max(1.0, float(d.get('length', 1.0)))
        raw_name = d.get('name')
        if isinstance(raw_name, list):
            raw_name = raw_name[0]
        hw = d.get('highway')
        if isinstance(hw, list):
            hw = hw[0]
        
        street_label = raw_name if raw_name else ("Pedestrian Ramp / Footpath" if hw == 'footway' else "Accessible Walkway")
        lat_u, lon_u = float(G.nodes[u]['y']), float(G.nodes[u]['x'])
        lat_v, lon_v = float(G.nodes[v]['y']), float(G.nodes[v]['x'])
        bearing = _calculate_bearing(lat_u, lon_u, lat_v, lon_v)

        if current_name is None:
            current_name = street_label
            accum_dist = edge_len
            accum_coords = [[lat_u, lon_u], [lat_v, lon_v]]
            prev_bearing = bearing
        elif street_label == current_name and abs(((bearing - prev_bearing + 360) % 360) - 180) > 130:
            accum_dist += edge_len
            accum_coords.append([lat_v, lon_v])
            prev_bearing = bearing
        else:
            turn_phrase, turn_type = _turn_label(prev_bearing, bearing)
            raw_steps.append({
                'instruction': f"{turn_phrase} onto {street_label}",
                'street': street_label,
                'distance_meters': round(accum_dist, 1),
                'turn': turn_type,
                'start_coord': accum_coords[0] if accum_coords else [lat_u, lon_u]
            })
            current_name = street_label
            accum_dist = edge_len
            accum_coords = [[lat_u, lon_u], [lat_v, lon_v]]
            prev_bearing = bearing

    if current_name:
        raw_steps.append({
            'instruction': f"Continue on {current_name}",
            'street': current_name,
            'distance_meters': round(accum_dist, 1),
            'turn': 'straight',
            'start_coord': accum_coords[0] if accum_coords else [float(G.nodes[node_path[-1]]['y']), float(G.nodes[node_path[-1]]['x'])]
        })

    dest_coord = [float(G.nodes[node_path[-1]]['y']), float(G.nodes[node_path[-1]]['x'])]
    raw_steps.append({
        'instruction': "Arrive at destination",
        'street': "Destination",
        'distance_meters': 0.0,
        'turn': 'arrive',
        'start_coord': dest_coord
    })

    if raw_steps:
        raw_steps[0]['instruction'] = f"Depart along {raw_steps[0]['street']}"
        raw_steps[0]['turn'] = 'depart'

    return raw_steps



def get_route(G, start, end):
    """
    Computes accessible route between start and end (lat, lon) tuples.
    Returns list of (lat, lon) coordinates along the path.
    Preserves exact Member 2 function signature and dynamically resolves
    walking network if points are outside the passed graph.
    """
    start_lat, start_lon = float(start[0]), float(start[1])
    end_lat, end_lon = float(end[0]), float(end[1])

    if G is None:
        from graph import get_graph_for_route
        G, _ = get_graph_for_route(start, end)
        from barriers import refresh_graph_costs
        refresh_graph_costs(G)
    else:
        from graph import is_point_within_graph, get_graph_for_route
        cov_s, _, _ = is_point_within_graph(G, start_lat, start_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
        cov_e, _, _ = is_point_within_graph(G, end_lat, end_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
        if not (cov_s and cov_e):
            G, _ = get_graph_for_route(start, end)
            from barriers import refresh_graph_costs
            refresh_graph_costs(G)

    a, _ = _validate_and_snap(G, start_lat, start_lon, label="Start location")
    b, _ = _validate_and_snap(G, end_lat, end_lon, label="Destination")

    if not nx.has_path(G, a, b):
        raise DisconnectedNetworkError(
            "No connected walking route exists between the selected start and destination "
            "in the OpenStreetMap data."
        )

    route = nx.shortest_path(G, a, b, weight='access_cost')
    return _extract_path_coordinates(G, route, weight_attr='access_cost')



def get_route_details(G, start, end, mode='both'):
    """
    Computes both the accessible route and the standard shortest route,
    providing full metrics, comparison, turn cues, and accessibility warnings.
    """
    # 1. Validate coordinate types
    try:
        start_lat, start_lon = float(start[0]), float(start[1])
        end_lat, end_lon = float(end[0]), float(end[1])
    except (ValueError, TypeError, IndexError):
        raise ValueError("Invalid coordinates provided. Must be numeric (lat, lon) pairs.")

    if not (-90.0 <= start_lat <= 90.0 and -180.0 <= start_lon <= 180.0):
        raise ValueError(f"Start coordinates ({start_lat}, {start_lon}) are out of valid geographic range.")

    if not (-90.0 <= end_lat <= 90.0 and -180.0 <= end_lon <= 180.0):
        raise ValueError(f"Destination coordinates ({end_lat}, {end_lon}) are out of valid geographic range.")

    # 2. Dynamically resolve graph if G is None or points are outside G
    if G is None:
        from graph import get_graph_for_route
        G, _ = get_graph_for_route(start, end)
        from barriers import refresh_graph_costs
        refresh_graph_costs(G)
    else:
        from graph import is_point_within_graph, get_graph_for_route
        cov_s, _, _ = is_point_within_graph(G, start_lat, start_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
        cov_e, _, _ = is_point_within_graph(G, end_lat, end_lon, MAX_ALLOWED_SNAP_DISTANCE_METERS)
        if not (cov_s and cov_e):
            G, _ = get_graph_for_route(start, end)
            from barriers import refresh_graph_costs
            refresh_graph_costs(G)

    # 3. Find nearest graph nodes and verify they are within coverage bounds
    a, node_a_dist = _validate_and_snap(G, start_lat, start_lon, label="Start location")
    b, node_b_dist = _validate_and_snap(G, end_lat, end_lon, label="Destination")


    warnings = []
    if node_a_dist > 60:
        warnings.append(f"Start point is {int(node_a_dist)}m from the nearest mapped footpath.")
    if node_b_dist > 60:
        warnings.append(f"Destination is {int(node_b_dist)}m from the nearest mapped footpath.")

    # 3. Check network connectivity between points
    if not nx.has_path(G, a, b):
        raise DisconnectedNetworkError(
            "No connected walking route exists between the selected start and destination "
            "in the OpenStreetMap data. The paths appear to be in physically disconnected pedestrian networks. "
            "Please select a point on an adjacent connected walkway."
        )

    # 4. Compute accessible route (weight='access_cost')
    accessible_node_path = nx.shortest_path(G, a, b, weight='access_cost')

    # 5. Compute standard shortest route (weight='length')
    shortest_node_path = nx.shortest_path(G, a, b, weight='length')

    # Extract real street coordinates (with curves if present)
    accessible_coords = _extract_path_coordinates(G, accessible_node_path, weight_attr='access_cost')
    shortest_coords = _extract_path_coordinates(G, shortest_node_path, weight_attr='length')

    # Metrics
    accessible_metrics = _path_metrics(G, accessible_node_path, weight_attr='access_cost')
    shortest_metrics = _path_metrics(G, shortest_node_path, weight_attr='length')

    # Explanations for why the route was chosen
    reasons = []
    if shortest_metrics['steps_count'] > accessible_metrics['steps_count']:
        avoided = shortest_metrics['steps_count'] - accessible_metrics['steps_count']
        reasons.append(f"Bypassed {avoided} stair flight{'s' if avoided > 1 else ''} found on the standard shortest path.")

    if shortest_metrics['wheelchair_no_count'] > accessible_metrics['wheelchair_no_count']:
        avoided = shortest_metrics['wheelchair_no_count'] - accessible_metrics['wheelchair_no_count']
        reasons.append(f"Avoided {avoided} segment{'s' if avoided > 1 else ''} marked wheelchair=no.")

    if shortest_metrics['rough_surface_count'] > accessible_metrics['rough_surface_count']:
        avoided = shortest_metrics['rough_surface_count'] - accessible_metrics['rough_surface_count']
        reasons.append(f"Avoided {avoided} rough/unpaved section{'s' if avoided > 1 else ''}.")

    if not reasons:
        reasons.append("The shortest path contains no mapped stairs or barriers, so it is optimal for accessibility.")

    # Transparent accessibility disclaimers (Requirement 6)
    if accessible_metrics['wheelchair_unverified_count'] > 0:
        warnings.append(
            f"{accessible_metrics['wheelchair_unverified_count']} segment(s) on this route lack explicit wheelchair "
            f"tags in OpenStreetMap. Slopes, curb cuts, and surface conditions cannot be guaranteed."
        )

    warnings.append(
        "OpenStreetMap walking data may not reflect live construction or temporary obstacles. "
        "Always exercise personal discretion."
    )

    return {
        'route_mode': mode,
        'accessible_route': {
            'coordinates': accessible_coords,
            'distance_meters': accessible_metrics['distance_meters'],
            'duration_minutes': accessible_metrics['duration_minutes'],
            'duration_seconds': accessible_metrics['duration_seconds'],
            'speed_basis': accessible_metrics['speed_basis'],
            'steps_count': accessible_metrics['steps_count'],
            'rough_surface_count': accessible_metrics['rough_surface_count'],
            'wheelchair_no_count': accessible_metrics['wheelchair_no_count'],
            'unverified_count': accessible_metrics['wheelchair_unverified_count'],
            'streets': accessible_metrics['streets'],
            'guidance_steps': accessible_metrics.get('guidance_steps', [])
        },
        'shortest_route': {
            'coordinates': shortest_coords,
            'distance_meters': shortest_metrics['distance_meters'],
            'duration_minutes': shortest_metrics['duration_minutes'],
            'duration_seconds': shortest_metrics['duration_seconds'],
            'speed_basis': shortest_metrics['speed_basis'],
            'steps_count': shortest_metrics['steps_count'],
            'rough_surface_count': shortest_metrics['rough_surface_count'],
            'wheelchair_no_count': shortest_metrics['wheelchair_no_count'],
            'unverified_count': shortest_metrics['wheelchair_unverified_count'],
            'streets': shortest_metrics['streets'],
            'guidance_steps': shortest_metrics.get('guidance_steps', [])
        },
        'reasons': reasons,
        'warnings': warnings
    }
