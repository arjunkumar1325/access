"""
AccessAI - Flask Web Application & REST API (Member 3)
Intelligent Accessible Route Planning Website & Backend Engine.
Integrates walking graph (Member 1), accessibility routing (Member 2),
AI vision classification (Member 4), barrier reporting (Member 5),
and compliant OpenStreetMap Nominatim geocoding.
"""

import os
import re
from datetime import timedelta
from functools import wraps
import networkx as nx
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash

from models import db, BarrierReport, User
from database import init_db
from graph import load_graph, get_graph_bounds, get_area_name, get_graph_for_route
from routing import (
    add_costs, get_route_details, get_route,
    OutOfBoundsLocationError, DisconnectedNetworkError
)
from barriers import (
    add_barrier, apply_barrier, apply_all, resolve_barrier,
    load_barriers, refresh_graph_costs
)
from geocoding import geocode_place
import vision

app = Flask(__name__)

# Security & Upload Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'accessai-prod-session-key-e7b39a842f1c')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=14)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

# Initialize database
init_db(app)


def get_current_user():
    """Retrieve currently authenticated user from session if present."""
    user_id = session.get('user_id')
    if user_id:
        try:
            return db.session.get(User, user_id)
        except Exception:
            return None
    return None


@app.context_processor
def inject_user():
    """Inject current_user into all rendered templates."""
    return dict(current_user=get_current_user())


def login_required(f):
    """Decorator to protect routes requiring authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Authentication required. Please sign in.'}), 401
            flash("Please sign in to access this feature.", "warning")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# Load walking graph and initialize edge accessibility costs
print("Loading walking graph and initializing accessibility weights...")
G = load_graph()
with app.app_context():
    refresh_graph_costs(G)
bounds = get_graph_bounds(G)
print(f"Graph loaded successfully: {len(G.nodes)} nodes, {len(G.edges)} edges.")
print(f"Area: {bounds.get('area_name')} | Center: ({bounds['center_lat']:.4f}, {bounds['center_lon']:.4f})")


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Serves the main interactive accessible navigation application."""
    return render_template(
        'index.html',
        area_name=bounds.get('area_name', 'Loaded Campus Area'),
        center_lat=bounds['center_lat'],
        center_lon=bounds['center_lon'],
        min_lat=bounds['min_lat'],
        max_lat=bounds['max_lat'],
        min_lon=bounds['min_lon'],
        max_lon=bounds['max_lon']
    )


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Safely serves uploaded barrier photos."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], secure_filename(filename))


# ==========================================
# AUTHENTICATION ROUTES (LOGIN & REGISTRATION)
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Display login page or authenticate user credentials."""
    # If already logged in, redirect to index or requested next URL
    if get_current_user():
        next_url = request.args.get('next') or request.form.get('next')
        return redirect(next_url if next_url and next_url.startswith('/') else url_for('index'))

    if request.method == 'GET':
        return render_template('login.html', next=request.args.get('next'))

    # POST request (supports both HTML form submission and JSON fetch)
    is_json = request.is_json
    data = request.get_json(silent=True) or request.form

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    remember_me = str(data.get('remember_me', '')).lower() in ('true', '1', 'on', 'yes')
    next_url = request.args.get('next') or data.get('next')

    # Server-side validation
    if not email:
        error_msg = "Email address is required."
        if is_json:
            return jsonify({'success': False, 'error': error_msg}), 400
        flash(error_msg, "error")
        return render_template('login.html', email=email, next=next_url), 400

    if not password:
        error_msg = "Password is required."
        if is_json:
            return jsonify({'success': False, 'error': error_msg}), 400
        flash(error_msg, "error")
        return render_template('login.html', email=email, next=next_url), 400

    # User lookup
    user = User.query.filter_by(email=email).first()

    # Password check with safe constant-time hashing comparison
    if not user or not user.check_password(password):
        error_msg = "Invalid email or password. Please verify your credentials and try again."
        if is_json:
            return jsonify({'success': False, 'error': error_msg}), 401
        flash(error_msg, "error")
        return render_template('login.html', email=email, next=next_url), 401

    # Successful login: prevent session fixation
    session.clear()
    session['user_id'] = user.id
    session['user_name'] = user.full_name
    session['user_email'] = user.email
    session.permanent = remember_me

    flash(f"Welcome back, {user.full_name}!", "success")

    target_redirect = next_url if next_url and next_url.startswith('/') else url_for('index')
    if is_json:
        return jsonify({
            'success': True,
            'message': f'Welcome back, {user.full_name}!',
            'redirect_url': target_redirect,
            'user': user.to_dict()
        }), 200

    return redirect(target_redirect)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Display registration page or securely create a new user account."""
    if get_current_user():
        return redirect(url_for('index'))

    if request.method == 'GET':
        return render_template('register.html')

    # POST request (supports both HTML form submission and JSON fetch)
    is_json = request.is_json
    data = request.get_json(silent=True) or request.form

    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    confirm_password = data.get('confirm_password') or ''

    # Server-side validation
    if not full_name or len(full_name) < 2:
        error_msg = "Full name must be at least 2 characters long."
        if is_json:
            return jsonify({'success': False, 'error': error_msg}), 400
        flash(error_msg, "error")
        return render_template('register.html', full_name=full_name, email=email), 400

    email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    if not email or not re.match(email_regex, email):
        error_msg = "Please provide a valid email address (e.g., name@example.com)."
        if is_json:
            return jsonify({'success': False, 'error': error_msg}), 400
        flash(error_msg, "error")
        return render_template('register.html', full_name=full_name, email=email), 400

    if not password or len(password) < 8:
        error_msg = "Password must be at least 8 characters long."
        if is_json:
            return jsonify({'success': False, 'error': error_msg}), 400
        flash(error_msg, "error")
        return render_template('register.html', full_name=full_name, email=email), 400

    if password != confirm_password:
        error_msg = "Passwords do not match. Please verify your entries."
        if is_json:
            return jsonify({'success': False, 'error': error_msg}), 400
        flash(error_msg, "error")
        return render_template('register.html', full_name=full_name, email=email), 400

    # Duplicate email check
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        error_msg = "An account with this email address already exists. Please sign in or use a different email."
        if is_json:
            return jsonify({'success': False, 'error': error_msg}), 409
        flash(error_msg, "error")
        return render_template('register.html', full_name=full_name, email=email), 409

    try:
        new_user = User(full_name=full_name, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()

        # Automatically log in the newly registered user
        session.clear()
        session['user_id'] = new_user.id
        session['user_name'] = new_user.full_name
        session['user_email'] = new_user.email
        session.permanent = True

        flash("Account created successfully! Welcome to AccessAI.", "success")

        if is_json:
            return jsonify({
                'success': True,
                'message': 'Account created successfully! Welcome to AccessAI.',
                'redirect_url': url_for('index'),
                'user': new_user.to_dict()
            }), 201

        return redirect(url_for('index'))
    except Exception as exc:
        db.session.rollback()
        error_msg = f"An error occurred while creating your account. Please try again."
        if is_json:
            return jsonify({'success': False, 'error': error_msg}), 500
        flash(error_msg, "error")
        return render_template('register.html', full_name=full_name, email=email), 500


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Clear the authenticated session and redirect to login."""
    session.clear()
    flash("You have been signed out successfully.", "info")
    if request.is_json:
        return jsonify({'success': True, 'redirect_url': url_for('login')}), 200
    return redirect(url_for('login'))


@app.route('/api/auth/status', methods=['GET'])
def api_auth_status():
    """Return JSON status of the current user session."""
    user = get_current_user()
    if user:
        return jsonify({
            'authenticated': True,
            'user': user.to_dict()
        }), 200
    return jsonify({
        'authenticated': False,
        'user': None
    }), 200


# ==========================================
# REST API ENDPOINTS
# ==========================================

@app.route('/api/health', methods=['GET'])
def api_health():
    """Returns application health, database status, graph metrics, and AI readiness."""
    active_barriers = BarrierReport.query.filter_by(status='active').count()
    return jsonify({
        'status': 'healthy',
        'app': 'AccessAI — Intelligent Accessible Route Planning',
        'database': 'connected',
        'graph': {
            'nodes': len(G.nodes),
            'edges': len(G.edges),
            'bounds': bounds,
            'area_name': get_area_name()
        },
        'active_barriers_count': active_barriers,
        'ai_classifier_ready': vision.is_ai_available(),
        'version': '1.1.0'
    })


@app.route('/api/map-info', methods=['GET'])
def api_map_info():
    """Returns coverage information and boundary coordinates for the loaded map area."""
    return jsonify({
        'success': True,
        'area_name': get_area_name(),
        'center': {
            'lat': bounds['center_lat'],
            'lon': bounds['center_lon']
        },
        'bounds': {
            'min_lat': bounds['min_lat'],
            'max_lat': bounds['max_lat'],
            'min_lon': bounds['min_lon'],
            'max_lon': bounds['max_lon']
        },
        'nodes_count': len(G.nodes),
        'edges_count': len(G.edges),
        'max_snap_distance_meters': 350.0,
        'dynamic_coverage': True,
        'instructions': (
            "AccessAI loads walking paths for the specified campus/neighborhood. "
            "Locations outside the initial map coverage are automatically downloaded and cached dynamically."
        )
    })



@app.route('/api/geocode', methods=['GET'])
def api_geocode():
    """
    Geocodes a place name query to latitude/longitude coordinates via Nominatim.
    Adheres strictly to Nominatim rate limits and usage policies.
    """
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({
            'success': False,
            'error': 'Missing search query parameter "q".'
        }), 400

    results = geocode_place(query, bounds=bounds, limit=5)
    return jsonify({
        'success': True,
        'query': query,
        'results_count': len(results),
        'results': results,
        'loaded_area': get_area_name()
    })


@app.route('/api/barriers', methods=['GET'])
def api_get_barriers():
    """Returns active barrier reports with coordinates, category, description, and status."""
    include_all = request.args.get('all', 'false').lower() == 'true'
    barriers = load_barriers(active_only=not include_all)
    return jsonify({
        'success': True,
        'count': len(barriers),
        'barriers': barriers
    })


@app.route('/api/barriers', methods=['POST'])
def api_post_barrier():
    """Validates and persists a new barrier report, applying penalty to the graph."""
    lat = None
    lon = None
    category = 'Other obstacle'
    note = ''
    image_filename = None

    if request.is_json:
        data = request.get_json() or {}
        lat = data.get('lat') or data.get('latitude')
        lon = data.get('lon') or data.get('longitude')
        category = data.get('category', 'Other obstacle')
        note = data.get('note') or data.get('description', '')
    else:
        lat = request.form.get('lat') or request.form.get('latitude')
        lon = request.form.get('lon') or request.form.get('longitude')
        category = request.form.get('category', 'Other obstacle')
        note = request.form.get('note') or request.form.get('description', '')

        # Handle optional photo upload
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '' and allowed_file(file.filename):
                safe_name = secure_filename(file.filename)
                unique_name = f"barrier_{int(os.path.getmtime(app.root_path))}_{safe_name}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
                file.save(save_path)
                image_filename = unique_name

    # Validate coordinate inputs
    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        return jsonify({
            'success': False,
            'error': 'Invalid coordinates. Latitude and longitude must be valid floating-point numbers.'
        }), 400

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return jsonify({
            'success': False,
            'error': f'Coordinates out of range: ({lat}, {lon}).'
        }), 400

    # Save to database and barriers list
    barrier_dict = add_barrier(
        lat=lat,
        lon=lon,
        note=note,
        category=category,
        image_filename=image_filename
    )

    # Immediately apply penalty to graph
    apply_barrier(G, barrier_dict)

    return jsonify({
        'success': True,
        'message': 'Barrier report submitted successfully.',
        'barrier': barrier_dict
    }), 201


@app.route('/api/barriers/<int:barrier_id>', methods=['PATCH'])
def api_update_barrier(barrier_id):
    """Updates status of a barrier (e.g. resolve or deactivate)."""
    data = request.get_json() or {}
    new_status = data.get('status', 'resolved')

    if new_status == 'resolved':
        success = resolve_barrier(barrier_id)
        if success:
            # Recompute graph weights so resolved barrier penalty is removed
            refresh_graph_costs(G)
            return jsonify({
                'success': True,
                'message': f'Barrier #{barrier_id} marked as resolved.',
                'status': 'resolved'
            })
        else:
            return jsonify({'success': False, 'error': 'Barrier not found'}), 404

    return jsonify({'success': False, 'error': 'Unsupported status update'}), 400


@app.route('/api/route', methods=['GET', 'POST'])
def api_calculate_route():
    """
    Accepts start and destination coordinates or place queries via GET or POST.
    Computes an accessibility-prioritized wheelchair route and compares against standard shortest route.
    Validates spatial boundaries and network connectivity.
    """
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
    else:
        data = request.args.to_dict()

    # Support multiple input formats: start=[lat, lon] or start_lat, start_lon
    if 'start' in data and 'end' in data:
        start_point = data['start']
        end_point = data['end']
        if isinstance(start_point, str) and ',' in start_point:
            start_point = [float(p.strip()) for p in start_point.split(',')]
        if isinstance(end_point, str) and ',' in end_point:
            end_point = [float(p.strip()) for p in end_point.split(',')]
    elif 'start_lat' in data and 'start_lon' in data and 'end_lat' in data and 'end_lon' in data:
        start_point = (data['start_lat'], data['start_lon'])
        end_point = (data['end_lat'], data['end_lon'])
    else:
        return jsonify({
            'success': False,
            'error': 'Missing start or destination coordinates. Provide "start" and "end" [lat, lon] lists or start_lat, start_lon, end_lat, end_lon parameters.'
        }), 400

    try:
        start = (float(start_point[0]), float(start_point[1]))
        end = (float(end_point[0]), float(end_point[1]))
    except (ValueError, TypeError, IndexError):
        return jsonify({
            'success': False,
            'error': 'Coordinates must be valid numeric pairs: [latitude, longitude].'
        }), 400

    mode = str(data.get('mode', 'accessible')).lower()
    if mode not in ('accessible', 'shortest', 'both'):
        mode = 'accessible'

    # Dynamically resolve walking graph covering start and end coordinates
    try:
        route_graph, graph_info = get_graph_for_route(start, end)
        refresh_graph_costs(route_graph)
    except OutOfBoundsLocationError as bound_err:
        return jsonify({
            'success': False,
            'error_type': 'OUT_OF_BOUNDS',
            'error': str(bound_err),
            'loaded_area': get_area_name(),
            'bounds': bounds
        }), 400
    except ValueError as val_err:
        return jsonify({
            'success': False,
            'error_type': 'VALIDATION_ERROR',
            'error': str(val_err)
        }), 400
    except Exception as exc:
        return jsonify({
            'success': False,
            'error_type': 'COVERAGE_ERROR',
            'error': f'Could not retrieve walking network for selected area: {str(exc)}'
        }), 500

    try:
        route_data = get_route_details(route_graph, start, end, mode=mode)
        primary_route = route_data['shortest_route'] if mode == 'shortest' else route_data['accessible_route']
        return jsonify({
            'success': True,
            'route_mode': mode,
            'area_info': graph_info,
            'coordinates': primary_route['coordinates'],
            'distance': primary_route['distance_meters'],
            'duration_minutes': primary_route['duration_minutes'],
            'speed_basis': primary_route['speed_basis'],
            'start': start,
            'end': end,
            'guidance_steps': primary_route.get('guidance_steps', []),
            'accessible_route': route_data['accessible_route'],
            'shortest_route': route_data['shortest_route'],
            'reasons': route_data['reasons'],
            'warnings': route_data['warnings']
        })
    except OutOfBoundsLocationError as bound_err:
        return jsonify({
            'success': False,
            'error_type': 'OUT_OF_BOUNDS',
            'error': str(bound_err),
            'loaded_area': get_area_name(),
            'bounds': bounds
        }), 400

    except (nx.NetworkXNoPath, DisconnectedNetworkError) as net_err:
        return jsonify({
            'success': False,
            'error_type': 'DISCONNECTED_NETWORK',
            'error': str(net_err)
        }), 400
    except nx.NodeNotFound as node_err:
        return jsonify({
            'success': False,
            'error_type': 'NODE_NOT_FOUND',
            'error': str(node_err)
        }), 400
    except ValueError as val_err:
        return jsonify({
            'success': False,
            'error_type': 'VALIDATION_ERROR',
            'error': str(val_err)
        }), 400
    except Exception as exc:
        return jsonify({
            'success': False,
            'error_type': 'SERVER_ERROR',
            'error': f'Route calculation failed: {str(exc)}'
        }), 500


@app.route('/api/analyze-image', methods=['POST'])
def api_analyze_image():
    """Optionally analyzes an uploaded image through CLIP zero-shot classification."""
    if 'image' not in request.files:
        return jsonify({
            'success': False,
            'error': 'No image file provided in request.'
        }), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected image file.'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Unsupported file format. Please upload JPG, PNG, or WebP.'}), 400

    safe_name = secure_filename(file.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], f"ai_{safe_name}")
    file.save(save_path)

    try:
        label, confidence = vision.analyze(save_path)
        return jsonify({
            'success': True,
            'filename': safe_name,
            'predicted_label': label,
            'confidence': confidence,
            'confidence_percentage': f"{round(confidence * 100, 1)}%",
            'warning': 'AI classification is automated and can make mistakes. Images cannot measure ramp slope angle, exact path width, or surface friction.'
        })
    except RuntimeError as run_err:
        return jsonify({
            'success': False,
            'error': str(run_err),
            'ai_enabled': False,
            'warning': 'AI dependencies (transformers / torch) are not active in this environment. Manual barrier reporting is fully active.'
        }), 200
    except Exception as exc:
        return jsonify({
            'success': False,
            'error': f'Image analysis error: {str(exc)}'
        }), 500


# Legacy form endpoint matching Team Build Guide page 7
@app.route('/report', methods=['POST'])
def legacy_report():
    """Provides compatibility with the basic HTML form in Team Build Guide."""
    point = request.form.get('point', '')
    note = request.form.get('note', '')
    if point and ',' in point:
        try:
            parts = point.split(',')
            lat, lon = float(parts[0].strip()), float(parts[1].strip())
            add_barrier(lat, lon, note=note)
            refresh_graph_costs(G)
        except Exception as e:
            print(f"Legacy report error: {e}")
    return redirect('/')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
