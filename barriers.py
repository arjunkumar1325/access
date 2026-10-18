"""
AccessAI - Barrier Reports and Management (Member 5)
Handles reporting, loading, and applying accessibility barriers onto the walking network.
Supports SQLite/SQLAlchemy with JSON fallback.
"""

import json
import os
import osmnx as ox
from models import db, BarrierReport

FILE = 'barriers.json'
BIG = 10000


def load_barriers(active_only=True):
    """
    Loads barriers from SQLite database if inside Flask application context,
    or falls back to reading barriers.json.
    """
    try:
        from flask import has_app_context
        if has_app_context():
            query = BarrierReport.query
            if active_only:
                query = query.filter_by(status='active')
            reports = query.order_by(BarrierReport.created_at.desc()).all()
            return [r.to_dict() for r in reports]
    except Exception:
        pass

    # Fallback to local json file if database context is not active
    if not os.path.exists(FILE):
        return []
    try:
        with open(FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if active_only:
                return [b for b in data if b.get('status', 'active') == 'active']
            return data
    except Exception:
        return []


def add_barrier(lat, lon, note='', category='Other obstacle', image_filename=None):
    """
    Adds a new barrier report to SQLite database and mirrors to barriers.json.
    Returns the created barrier dictionary.
    """
    lat = float(lat)
    lon = float(lon)
    barrier_dict = {
        'lat': lat,
        'lon': lon,
        'note': str(note or ''),
        'category': str(category or 'Other obstacle'),
        'image_filename': image_filename,
        'status': 'active',
        'verification_status': 'community_reported'
    }

    # 1. Save to SQLite database if possible
    saved_to_db = False
    try:
        report = BarrierReport(
            latitude=lat,
            longitude=lon,
            category=barrier_dict['category'],
            description=barrier_dict['note'],
            status='active',
            image_filename=image_filename,
            verification_status='community_reported'
        )
        db.session.add(report)
        db.session.commit()
        barrier_dict['id'] = report.id
        saved_to_db = True
    except Exception:
        # Session rollback if needed
        try:
            db.session.rollback()
        except Exception:
            pass

    # 2. Mirror to barriers.json
    try:
        current_data = []
        if os.path.exists(FILE):
            try:
                with open(FILE, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
            except Exception:
                current_data = []

        if not saved_to_db:
            barrier_dict['id'] = len(current_data) + 1

        current_data.append(barrier_dict)
        with open(FILE, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to write to {FILE}: {e}")

    return barrier_dict


def resolve_barrier(barrier_id):
    """Marks a barrier as resolved so it no longer penalizes routes."""
    updated = False
    try:
        report = db.session.get(BarrierReport, int(barrier_id))
        if report:
            report.status = 'resolved'
            db.session.commit()
            updated = True
    except Exception:
        pass

    # Update barriers.json
    if os.path.exists(FILE):
        try:
            with open(FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for item in data:
                if str(item.get('id')) == str(barrier_id):
                    item['status'] = 'resolved'
                    updated = True
            with open(FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    return updated


def apply_barrier(G, b):
    """Applies a high routing penalty to the nearest walking edge for a barrier."""
    lat = float(b.get('lat') if 'lat' in b else b['latitude'])
    lon = float(b.get('lon') if 'lon' in b else b['longitude'])

    try:
        u, v, k = ox.distance.nearest_edges(G, X=lon, Y=lat)
        edge_data = G[u][v][k]
        base = float(edge_data.get('base_access_cost', edge_data.get('length', 1.0)))
        curr = float(edge_data.get('access_cost', base))
        edge_data['base_access_cost'] = base
        edge_data['access_cost'] = max(curr, base + BIG)

        if G.has_edge(v, u):
            for kk in G[v][u]:
                rev_edge = G[v][u][kk]
                rev_base = float(rev_edge.get('base_access_cost', rev_edge.get('length', 1.0)))
                rev_curr = float(rev_edge.get('access_cost', rev_base))
                rev_edge['base_access_cost'] = rev_base
                rev_edge['access_cost'] = max(rev_curr, rev_base + BIG)
    except Exception as e:
        print(f"Notice: Could not snap barrier ({lat}, {lon}) to edge: {e}")


def apply_all(G):
    """Applies all active barriers to the graph."""
    for b in load_barriers(active_only=True):
        apply_barrier(G, b)


def refresh_graph_costs(G):
    """
    Deterministically resets edge costs to base_access_cost and applies active barriers.
    Prevents duplicate barrier cost accumulation on repeated requests.
    """
    from routing import add_costs
    # If base_access_cost is missing on edges, initialize once
    has_base = any('base_access_cost' in d for _, _, _, d in G.edges(keys=True, data=True))
    if not has_base:
        add_costs(G)
    else:
        for u, v, k, d in G.edges(keys=True, data=True):
            try:
                base = float(d.get('base_access_cost', d.get('length', 1.0)))
            except (ValueError, TypeError):
                base = 1.0
            d['base_access_cost'] = base
            d['access_cost'] = base
            if 'length' in d:
                try:
                    d['length'] = float(d['length'])
                except (ValueError, TypeError):
                    d['length'] = 1.0

    apply_all(G)

