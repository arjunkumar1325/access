"""
AccessAI — Authentication and Security Test Suite
Tests login, registration, password hashing, duplicate detection,
session lifecycle, and regression safety for existing map features.
"""

import unittest
import os
import sys

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from models import db, User


class AccessAIAuthTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

        with app.app_context():
            db.create_all()
            # Clean up test user if left over
            User.query.filter(User.email.like('%@testaccessai.local')).delete()
            db.session.commit()

            # Pre-seed a known test user
            self.test_user = User(
                full_name="Sarah Connor",
                email="sarah@testaccessai.local",
                password="SafePassword123!"
            )
            db.session.add(self.test_user)
            db.session.commit()
            self.test_user_id = self.test_user.id

    def tearDown(self):
        with app.app_context():
            User.query.filter(User.email.like('%@testaccessai.local')).delete()
            db.session.commit()
            db.session.remove()

    def test_login_page_renders(self):
        """GET /login returns 200 with all required form controls and branding."""
        resp = self.client.get('/login')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Check required fields & labels
        self.assertIn('Sign In', html)
        self.assertIn('Email Address', html)
        self.assertIn('Password', html)
        self.assertIn('btn-toggle-password', html)
        self.assertIn('Remember me', html)
        self.assertIn('Forgot password?', html)
        self.assertIn('Create Account', html)

        # Check branding and tagline
        self.assertIn('AccessAI', html)
        self.assertIn('Accessible journeys. Greater independence.', html)
        self.assertIn('auth-background', html)

    def test_register_page_renders(self):
        """GET /register returns 200 with registration form and password strength controls."""
        resp = self.client.get('/register')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn('Create Account', html)
        self.assertIn('Full Name', html)
        self.assertIn('Email Address', html)
        self.assertIn('Password', html)
        self.assertIn('Confirm Password', html)
        self.assertIn('password-strength-wrapper', html)
        self.assertIn('Sign In', html)

    def test_registration_validation_and_success(self):
        """POST /register validates fields and creates hashed account securely."""
        new_email = "newuser@testaccessai.local"

        # 1. Reject missing or short password
        resp = self.client.post('/register', data={
            'full_name': 'New User',
            'email': new_email,
            'password': 'short',
            'confirm_password': 'short'
        })
        self.assertEqual(resp.status_code, 400)

        # 2. Reject password mismatch
        resp = self.client.post('/register', data={
            'full_name': 'New User',
            'email': new_email,
            'password': 'ValidPassword123!',
            'confirm_password': 'DifferentPassword123!'
        })
        self.assertEqual(resp.status_code, 400)

        # 3. Successful registration
        resp = self.client.post('/register', data={
            'full_name': 'New User',
            'email': new_email,
            'password': 'ValidPassword123!',
            'confirm_password': 'ValidPassword123!'
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)  # Redirects to index

        # Verify password is NEVER stored as plain text
        with app.app_context():
            created_user = User.query.filter_by(email=new_email).first()
            self.assertIsNotNone(created_user)
            self.assertEqual(created_user.full_name, 'New User')
            self.assertNotEqual(created_user.password_hash, 'ValidPassword123!')
            self.assertTrue(created_user.check_password('ValidPassword123!'))
            self.assertFalse(created_user.check_password('WrongPassword!'))

    def test_duplicate_email_registration_rejected(self):
        """POST /register rejects duplicate email addresses."""
        resp = self.client.post('/register', data={
            'full_name': 'Duplicate User',
            'email': 'sarah@testaccessai.local',
            'password': 'ValidPassword123!',
            'confirm_password': 'ValidPassword123!'
        })
        self.assertEqual(resp.status_code, 409)

    def test_login_success_and_session(self):
        """POST /login sets authenticated session and redirects."""
        resp = self.client.post('/login', data={
            'email': 'sarah@testaccessai.local',
            'password': 'SafePassword123!',
            'remember_me': 'true'
        }, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('user_id'), self.test_user_id)
            self.assertEqual(sess.get('user_name'), 'Sarah Connor')

    def test_login_invalid_credentials_rejected(self):
        """POST /login rejects incorrect password or non-existent email."""
        # Bad password
        resp = self.client.post('/login', data={
            'email': 'sarah@testaccessai.local',
            'password': 'WrongPassword123!'
        })
        self.assertEqual(resp.status_code, 401)

        # Unknown email
        resp = self.client.post('/login', data={
            'email': 'nobody@testaccessai.local',
            'password': 'SafePassword123!'
        })
        self.assertEqual(resp.status_code, 401)

    def test_logout(self):
        """POST /logout clears session and redirects to /login."""
        # First log in
        self.client.post('/login', data={
            'email': 'sarah@testaccessai.local',
            'password': 'SafePassword123!'
        })

        # Then logout
        resp = self.client.post('/logout', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('user_id'))

    def test_homepage_reflects_auth_state(self):
        """GET / displays Sign In button when logged out, and user badge when logged in."""
        # Unauthenticated:
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('btn-nav-login', html)
        self.assertIn('Sign In', html)

        # Authenticate:
        self.client.post('/login', data={
            'email': 'sarah@testaccessai.local',
            'password': 'SafePassword123!'
        })

        # Authenticated:
        resp2 = self.client.get('/')
        self.assertEqual(resp2.status_code, 200)
        html2 = resp2.get_data(as_text=True)
        self.assertIn('Sarah', html2)
        self.assertIn('Sign Out', html2)

    def test_existing_map_endpoints_still_healthy(self):
        """Verify core AccessAI map and health endpoints are unaffected by auth additions."""
        resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('graph', data)

        resp_map = self.client.get('/api/map-info')
        self.assertEqual(resp_map.status_code, 200)
        self.assertTrue(resp_map.get_json()['success'])


if __name__ == '__main__':
    unittest.main()
