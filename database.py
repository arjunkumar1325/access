"""
AccessAI - Database Configuration & Helpers
Handles SQLite initialization, session management, and configuration settings
allowing simple future migration to PostgreSQL/PostGIS.
"""

import os
from models import db, BarrierReport, User

# Allow configuring database URL via environment, defaulting to local SQLite database
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)

DEFAULT_SQLITE_PATH = os.path.join(INSTANCE_DIR, 'accessai.db').replace('\\', '/')
DATABASE_URL = os.environ.get('DATABASE_URL', f'sqlite:///{DEFAULT_SQLITE_PATH}')



def init_db(app):
    """Configures the Flask app and initializes database tables."""
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        # Seed initial sample barriers if database is empty
        _seed_initial_barriers_if_empty()


def _seed_initial_barriers_if_empty():
    """Seeds standard demo barriers for initial testing if none exist."""
    if BarrierReport.query.count() == 0:
        sample_reports = [
            BarrierReport(
                latitude=12.9723,
                longitude=77.5948,
                category='Stairs',
                description='Outdoor flight of 12 steep stone steps without a ramp or handrail.',
                status='active',
                verification_status='community_reported'
            ),
            BarrierReport(
                latitude=12.9708,
                longitude=77.5935,
                category='Construction',
                description='Footpath blocked due to utility pavement repair. Wheelchairs must detour.',
                status='active',
                verification_status='verified'
            ),
            BarrierReport(
                latitude=12.9735,
                longitude=77.5962,
                category='Broken ramp',
                description='Damaged ramp curb with deep cracks and high lip edge (>5cm).',
                status='active',
                verification_status='community_reported'
            )
        ]
        db.session.bulk_save_objects(sample_reports)
        db.session.commit()
