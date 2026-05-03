import datetime
import logging
import re
from functools import wraps

from flask import flash, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.adapters.user_commands import UserCommandAdapter
from simple_safer_server.services.file_persistence import atomic_write_json, read_json
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.web.api import json_problem
from simple_safer_server.web.problems import ForbiddenProblem, UnauthorizedProblem

logger = logging.getLogger(__name__)


def _parse_user_timestamp(value):
    timestamp = datetime.datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        # Older user records stored UTC values without an offset; keep them
        # comparable with the aware timestamps written by current code.
        return timestamp.replace(tzinfo=datetime.timezone.utc)
    return timestamp


class PasswordPolicy:
    def __init__(self):
        self.min_length = 4

    def validate(self, password):
        if len(password) < self.min_length:
            return False, f"Password must be at least {self.min_length} characters long"
        return True, "Password is valid"


class UserManager:
    def __init__(self, runtime=None, command_adapter=None):
        self.runtime = runtime or get_runtime()
        self.command_adapter = command_adapter or UserCommandAdapter()
        self.users_file = self.runtime.config_dir / 'users.json'
        self.users = self._load_users()
        self._ensure_secure_permissions()

    def _ensure_secure_permissions(self):
        """Ensure secure file permissions"""
        try:
            # Ensure directory has correct permissions
            self.users_file.parent.mkdir(parents=True, exist_ok=True)
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
                return read_json(self.users_file, {})
            except Exception as e:
                logger.error(f"Error loading users: {e}")
                return {}
        return {}

    def reload_users(self):
        """Reload persisted user records into this manager."""
        self.users = self._load_users()

    def _save_users(self):
        """Save users to the JSON file"""
        try:
            # User records include password hashes and lockout counters, so the
            # replacement inode must be private before it is published.
            atomic_write_json(self.users_file, self.users, mode=0o600)
        except Exception as e:
            logger.error(f"Error saving users: {e}")
            raise

    def _sync_user_to_samba(self, username, password):
        """Sync a user to the Samba user database"""
        if self.runtime.is_fake:
            logger.info(f"Fake mode: skipping Samba sync for {username}")
            return True
        try:
            # First, ensure the user exists in the system
            if not self.command_adapter.system_user_exists(username):
                # User doesn't exist, create them
                logger.info(f"Creating system user {username}")
                self.command_adapter.create_system_user(username)

            # Check if user already exists in Samba
            existing_users = self.command_adapter.samba_users()

            if username in existing_users:
                # Update existing user password
                self.command_adapter.set_samba_password(username, password)
                logger.info(f"Updated Samba password for user {username}")
            else:
                # Create new Samba user
                self.command_adapter.set_samba_password(username, password)
                logger.info(f"Created Samba user {username}")

            return True
        except CalledProcessError as e:
            logger.error(f"Error syncing user {username} to Samba: {e}")
            return False

    def _remove_user_from_samba(self, username):
        """Remove a user from the Samba user database"""
        if self.runtime.is_fake:
            logger.info(f"Fake mode: skipping Samba removal for {username}")
            return True
        try:
            self.command_adapter.remove_samba_user(username)
            logger.info(f"Removed Samba user {username}")
            return True
        except CalledProcessError as e:
            logger.error(f"Error removing user {username} from Samba: {e}")
            return False

    def create_user(self, username, password, is_admin=False):
        """Create a new user with explicit admin elevation at call sites."""
        # Validate username
        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            return False, "Username may only contain letters, numbers, underscores, and hyphens"

        if username in self.users:
            return False, "Username already exists"

        # Validate password
        policy = PasswordPolicy()
        is_valid, message = policy.validate(password)
        if not is_valid:
            return False, message

        # Store user with additional security measures
        self.users[username] = {
            'password_hash': generate_password_hash(password),
            'is_admin': is_admin,
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'last_login': None,
            'failed_attempts': 0,
            'locked_until': None,
        }

        # Sync to Samba
        if not self._sync_user_to_samba(username, password):
            # Keep JSON and in-memory users aligned with Samba; callers retry
            # failed creates, so a half-created user would turn into "exists".
            self.users.pop(username, None)
            return False, "User creation failed: could not sync with Samba"

        self._save_users()
        return True, "User created successfully"

    def verify_user(self, username, password):
        """Verify user credentials with rate limiting"""
        if username not in self.users:
            return False

        user = self.users[username]
        now = datetime.datetime.now(datetime.timezone.utc)

        # Check if account is locked
        if user.get('locked_until'):
            if now < _parse_user_timestamp(user['locked_until']):
                return False
            # Reset lock if time has passed
            user['locked_until'] = None
            user['failed_attempts'] = 0

        # Successful login clears rate-limit state; password policy applies when credentials are created.
        if check_password_hash(user['password_hash'], password):
            # Reset failed attempts on successful login
            user['failed_attempts'] = 0
            user['last_login'] = now.isoformat()
            self._save_users()
            return True

        # Increment failed attempts
        user['failed_attempts'] = user.get('failed_attempts', 0) + 1

        # Lock account after 5 failed attempts
        if user['failed_attempts'] >= 5:
            user['locked_until'] = (now + datetime.timedelta(minutes=15)).isoformat()

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
                'last_login': user.get('last_login'),
            }
        return None

    def list_users(self):
        """List all users without password hashes or lockout internals."""
        return [self.get_user(username) for username in self.users]

    def _commit_password_record_after_samba_sync(self, username, password, user_record):
        """Persist a user record only after Samba accepts the same password."""
        if username not in self.users:
            return False

        previous_record = dict(self.users[username])
        next_record = dict(user_record)
        next_record['password_hash'] = generate_password_hash(password)

        # Samba password changes cannot be rolled back because the app does not
        # retain plaintext passwords. Sync first so a Samba failure leaves the
        # app login and SMB login on the previous usable password.
        if not self._sync_user_to_samba(username, password):
            self.users[username] = previous_record
            return False

        self.users[username] = next_record
        self._save_users()
        return True

    def reset_existing_admin_user(self, username, password):
        """Refresh an existing sole user into the migrated admin account."""
        if username not in self.users:
            return False

        user_record = dict(self.users[username])
        user_record['is_admin'] = True
        user_record['failed_attempts'] = 0
        user_record['locked_until'] = None
        user_record.setdefault(
            'created_at', datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        user_record.setdefault('last_login', None)
        return self._commit_password_record_after_samba_sync(username, password, user_record)

    def set_password(self, username, new_password):
        """Set a user's password from an admin flow and keep Samba in sync."""
        if username not in self.users:
            return False, "User does not exist"

        policy = PasswordPolicy()
        is_valid, message = policy.validate(new_password)
        if not is_valid:
            return False, message

        if not self._commit_password_record_after_samba_sync(
            username, new_password, self.users[username]
        ):
            return False, "Password change failed: could not sync with Samba"

        return True, "Password changed successfully"

    def update_admin_status(self, username, is_admin):
        """Persist an admin-role change for an existing user."""
        if username not in self.users:
            return False, "User does not exist"
        self.users[username]['is_admin'] = is_admin
        self._save_users()
        return True, "User updated successfully"

    def delete_user(self, username):
        """Delete a user"""
        if username not in self.users:
            return False, "User does not exist"

        # Remove from Samba first so a stale share account cannot outlive the
        # app account after the UI reports a successful delete.
        if not self._remove_user_from_samba(username):
            return False, "Failed to remove user from Samba"

        # Remove from JSON store
        del self.users[username]
        self._save_users()

        return True, "User deleted successfully"

    def get_preferred_admin_username(self, preferred_username=None):
        """Return the best admin user to auto-login for local fake mode."""
        if preferred_username and self.is_admin(preferred_username):
            return preferred_username

        for username, data in self.users.items():
            if data.get('is_admin', False):
                return username

        return None

    def user_exists_in_samba(self, username):
        """Check if user exists in Samba database"""
        if self.runtime.is_fake:
            return username in self.users
        try:
            return username in self.command_adapter.samba_users()
        except CalledProcessError:
            return False


def admin_required(f):
    """Require an administrator session for HTML management pages."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = session.get('username')
        if not username:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))

        # Web UI sessions are admin-only, but roles can change after a cookie is
        # issued. Re-check the user store on every protected request so demoted
        # accounts do not keep a stale management session.
        user_manager = UserManager()
        if not user_manager.is_admin(username):
            session.clear()
            flash('Admin privileges required', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def api_admin_required(f):
    """Require an administrator session for JSON API routes."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = session.get('username')
        if not username:
            return json_problem(
                UnauthorizedProblem("Please log in again.", slug="api-login-required")
            )

        # API callers need status codes and JSON instead of redirects; keep this
        # separate from admin_required so fetch() handlers can fail predictably.
        user_manager = UserManager()
        if not user_manager.is_admin(username):
            session.clear()
            return json_problem(
                ForbiddenProblem("Admin privileges required.", slug="api-admin-required")
            )
        return f(*args, **kwargs)

    return decorated_function
