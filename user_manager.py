from werkzeug.security import generate_password_hash, check_password_hash
import json
from pathlib import Path
import logging
from functools import wraps
from flask import session, redirect, url_for, flash
import re
import secrets
import os
import datetime
import subprocess

logger = logging.getLogger(__name__)

class PasswordPolicy:
    def __init__(self):
        self.min_length = 4

    def validate(self, password):
        if len(password) < self.min_length:
            return False, f"Password must be at least {self.min_length} characters long"
        return True, "Password is valid"

class UserManager:
    def __init__(self):
        self.users_file = Path('/etc/SimpleSaferServer/users.json')
        self.users = self._load_users()
        self._ensure_secure_permissions()

    def _ensure_secure_permissions(self):
        """Ensure secure file permissions"""
        try:
            # Ensure directory has correct permissions
            self.users_file.parent.chmod(0o700)
            
            # Ensure file has correct permissions
            if self.users_file.exists():
                self.users_file.chmod(0o600)
        except Exception as e:
            logger.error(f"Error setting secure permissions: {e}")
            raise

    def _load_users(self):
        """Load users from the JSON file"""
        if self.users_file.exists():
            try:
                return json.loads(self.users_file.read_text())
            except Exception as e:
                logger.error(f"Error loading users: {e}")
                return {}
        return {}

    def _save_users(self):
        """Save users to the JSON file"""
        try:
            # Create directory if it doesn't exist
            self.users_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to temporary file first
            temp_file = self.users_file.with_suffix('.tmp')
            temp_file.write_text(json.dumps(self.users, indent=2))
            
            # Set secure permissions on temp file
            temp_file.chmod(0o600)
            
            # Atomic rename
            temp_file.rename(self.users_file)
            
            # Ensure secure permissions
            self._ensure_secure_permissions()
        except Exception as e:
            logger.error(f"Error saving users: {e}")
            raise

    def _sync_user_to_samba(self, username, password):
        """Sync a user to the Samba user database"""
        try:
            # First, ensure the user exists in the system
            try:
                # Check if user exists in system
                subprocess.run(['id', username], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                # User doesn't exist, create them
                logger.info(f"Creating system user {username}")
                subprocess.run(['sudo', 'useradd', '-m', '-s', '/bin/bash', username], check=True)
            
            # Check if user already exists in Samba
            result = subprocess.run(['sudo', 'pdbedit', '-L'], capture_output=True, text=True)
            existing_users = result.stdout.splitlines()
            
            if username in existing_users:
                # Update existing user password
                subprocess.run(['sudo', 'smbpasswd', '-s', '-a', username], 
                             input=f"{password}\n{password}\n", text=True, check=True)
                logger.info(f"Updated Samba password for user {username}")
            else:
                # Create new Samba user
                subprocess.run(['sudo', 'smbpasswd', '-s', '-a', username], 
                             input=f"{password}\n{password}\n", text=True, check=True)
                logger.info(f"Created Samba user {username}")
            
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error syncing user {username} to Samba: {e}")
            return False

    def _remove_user_from_samba(self, username):
        """Remove a user from the Samba user database"""
        try:
            subprocess.run(['sudo', 'smbpasswd', '-x', username], check=True)
            logger.info(f"Removed Samba user {username}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error removing user {username} from Samba: {e}")
            return False

    def create_user(self, username, password):
        """Create a new user"""
        # Validate username
        if not re.match(r'^[a-zA-Z0-9_-]{3,32}$', username):
            return False, "Username must be 3-32 characters and contain only letters, numbers, underscores, and hyphens"
        
        if username in self.users:
            return False, "Username already exists"
        
        # Validate password
        policy = PasswordPolicy()
        is_valid, message = policy.validate(password)
        if not is_valid:
            return False, message
        
        # Generate a unique salt for this user
        salt = secrets.token_hex(16)
        
        # Store user with additional security measures
        self.users[username] = {
            'password_hash': generate_password_hash(password),
            'is_admin': True,  # First user is always admin
            'created_at': str(datetime.datetime.utcnow()),
            'last_login': None,
            'failed_attempts': 0,
            'locked_until': None
        }
        
        self._save_users()
        
        # Sync to Samba
        if not self._sync_user_to_samba(username, password):
            return False, "User created but failed to sync with Samba"
        
        return True, "User created successfully"

    def verify_user(self, username, password):
        """Verify user credentials with rate limiting"""
        if username not in self.users:
            return False
        
        user = self.users[username]
        
        # Check if account is locked
        if user.get('locked_until'):
            if datetime.datetime.utcnow() < datetime.datetime.fromisoformat(user['locked_until']):
                return False
            # Reset lock if time has passed
            user['locked_until'] = None
            user['failed_attempts'] = 0
        
        # Verify password
        policy = PasswordPolicy()
        if check_password_hash(user['password_hash'], password):
            # Reset failed attempts on successful login
            user['failed_attempts'] = 0
            user['last_login'] = str(datetime.datetime.utcnow())
            self._save_users()
            return True
        
        # Increment failed attempts
        user['failed_attempts'] = user.get('failed_attempts', 0) + 1
        
        # Lock account after 5 failed attempts
        if user['failed_attempts'] >= 5:
            user['locked_until'] = str(datetime.datetime.utcnow() + datetime.timedelta(minutes=15))
        
        self._save_users()
        return False

    def is_admin(self, username):
        """Check if user is admin"""
        return self.users.get(username, {}).get('is_admin', False)

    def get_user(self, username):
        """Get user information (excluding sensitive data)"""
        user = self.users.get(username, {})
        if user:
            return {
                'username': username,
                'is_admin': user.get('is_admin', False),
                'created_at': user.get('created_at'),
                'last_login': user.get('last_login')
            }
        return None

    def change_password(self, username, current_password, new_password):
        """Change user password"""
        if not self.verify_user(username, current_password):
            return False, "Current password is incorrect"
        
        # Validate new password
        policy = PasswordPolicy()
        is_valid, message = policy.validate(new_password)
        if not is_valid:
            return False, message
        
        # Update password
        self.users[username]['password_hash'] = generate_password_hash(new_password)
        self._save_users()
        
        # Sync to Samba
        if not self._sync_user_to_samba(username, new_password):
            return False, "Password changed but failed to sync with Samba"
        
        return True, "Password changed successfully"

    def delete_user(self, username):
        """Delete a user"""
        if username not in self.users:
            return False, "User does not exist"
        
        # Remove from Samba first
        self._remove_user_from_samba(username)
        
        # Remove from JSON store
        del self.users[username]
        self._save_users()
        
        return True, "User deleted successfully"

    def get_all_users(self):
        """Get all users (excluding sensitive data)"""
        return [self.get_user(username) for username in self.users.keys()]

    def user_exists_in_samba(self, username):
        """Check if user exists in Samba database"""
        try:
            result = subprocess.run(['sudo', 'pdbedit', '-L'], capture_output=True, text=True)
            return username in result.stdout.splitlines()
        except subprocess.CalledProcessError:
            return False

    def user_exists_in_system(self, username):
        """Check if user exists in system user database"""
        try:
            subprocess.run(['id', username], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        
        user_manager = UserManager()
        if not user_manager.is_admin(session['username']):
            flash('Admin privileges required', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function 