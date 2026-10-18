"""
AccessAI - Database and Models
Defines SQLite database setup and SQLAlchemy models for barrier reports.
"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()



def utc_now():
    return datetime.now(timezone.utc)


class BarrierReport(db.Model):
    __tablename__ = 'barrier_reports'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(64), nullable=False, default='Other obstacle')
    description = db.Column(db.String(512), nullable=True, default='')
    status = db.Column(db.String(32), nullable=False, default='active')  # 'active', 'resolved', 'inactive'
    image_filename = db.Column(db.String(256), nullable=True)
    verification_status = db.Column(db.String(32), nullable=False, default='unverified')
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def __init__(
        self,
        latitude,
        longitude,
        category='Other obstacle',
        description='',
        status='active',
        image_filename=None,
        verification_status='unverified',
        created_at=None
    ):
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.category = category
        self.description = description
        self.status = status
        self.image_filename = image_filename
        self.verification_status = verification_status
        if created_at is not None:
            self.created_at = created_at

    def to_dict(self):
        return {
            'id': self.id,
            'lat': self.latitude,
            'lon': self.longitude,
            'category': self.category,
            'note': self.description or '',
            'description': self.description or '',
            'status': self.status,
            'image_filename': self.image_filename,
            'verification_status': self.verification_status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    full_name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def __init__(self, full_name, email, password=None, password_hash=None, created_at=None):
        self.full_name = (full_name or '').strip()
        self.email = (email or '').strip().lower()
        if password:
            self.set_password(password)
        elif password_hash:
            self.password_hash = password_hash
        if created_at is not None:
            self.created_at = created_at

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash or not password:
            return False
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

