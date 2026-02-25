import os
import json
import threading
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_babel import Babel, gettext, ngettext, lazy_gettext as _l
from werkzeug.security import generate_password_hash, check_password_hash
import scanner

# Version
__version__ = '1.0.1'

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))

# Supported languages
LANGUAGES = {
    'en': 'English',
    'es': 'Español',
    'fr': 'Français',
    'de': 'Deutsch',
    'it': 'Italiano',
    'pt': 'Português',
    'ru': 'Русский',
    'ja': '日本語',
    'zh': '中文',
    'ko': '한국어',
    'ar': 'العربية',
    'no': 'Norsk',
}

# Initialize Babel without app (will be bound later with init_app)
babel = Babel()

CONFIG_DIR = '/config'
CONFIG_PATH = os.path.join(CONFIG_DIR, 'settings.json')

if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

# --- AUTHENTICATION SETUP ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

def load_settings():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {}

def save_settings(data):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(data, f, indent=4)

def is_auth_disabled():
    """Check if authentication is disabled in settings."""
    return load_settings().get('auth_disabled', False)

def optional_login_required(f):
    """Decorator that requires login unless auth_disabled is True."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if is_auth_disabled():
            # Auth is disabled, bypass login requirement
            return f(*args, **kwargs)
        else:
            # Auth is enabled, require login
            if current_user.is_authenticated:
                return f(*args, **kwargs)
            else:
                return login_manager.unauthorized()
    return decorated_function

@app.before_request
def before_request():
    """Handle locale selection and auto-login for disabled auth."""
    from flask import g
    
    # Set locale based on settings or browser preference
    settings = load_settings()
    if settings.get('language') and settings.get('language') in LANGUAGES:
        locale = settings.get('language')
    else:
        locale = request.accept_languages.best_match(LANGUAGES.keys()) or 'en'
    g.locale = locale
    
    # Auto-login user if auth is disabled
    if is_auth_disabled() and not current_user.is_authenticated:
        login_user(User(1))

# Define locale selector function
def get_locale():
    """Get locale from settings or browser preference."""
    from flask import g
    if hasattr(g, 'locale'):
        return g.locale
    return 'en'

# Initialize Babel with app and locale selector
babel.init_app(app, locale_selector=get_locale)

# Mark common status strings for translation (used in API responses)
# These are extracted by pybabel to ensure they're available in all languages
_l("Idle")
_l("Scanning")
_l("Complete")
_l("Error")
_l("Sleeping")

# --- ROUTES ---

@app.route('/')
@optional_login_required
def index():
    settings = load_settings()
    if not settings.get('plex_url') or not settings.get('plex_token'):
        return render_template('settings.html', settings=settings, first_run=True, auth_enabled=not is_auth_disabled(), languages=LANGUAGES)
    return render_template('index.html', auth_enabled=not is_auth_disabled(), languages=LANGUAGES)

@app.route('/settings')
@optional_login_required
def settings_page():
    settings = load_settings()
    display_settings = settings.copy()
    
    if settings.get('plex_token'):
        # If a token exists, replace it with a mask.
        # The browser isn't served the plex token.
        display_settings['plex_token'] = '********'
    
    return render_template('settings.html', settings=display_settings, first_run=False, auth_enabled=not is_auth_disabled(), languages=LANGUAGES)

# --- LOGIN FLOW ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    settings = load_settings()
    
    # If auth is disabled, redirect to index
    if is_auth_disabled():
        return redirect(url_for('index'))
    
    stored_hash = settings.get('admin_password_hash')

    # If no password is set, force them to the setup page
    if not stored_hash:
        return redirect(url_for('setup_auth'))

    if request.method == 'POST':
        password = request.form.get('password')
        if check_password_hash(stored_hash, password):
            login_user(User(1), remember=True)
            return redirect(url_for('index'))
        else:
            flash('Invalid Password')

    return render_template('login.html', title="Login", btn_text="Sign In", is_setup=False)

@app.route('/setup', methods=['GET', 'POST'])
def setup_auth():
    settings = load_settings()
    
    # If auth is disabled, skip setup and go to index
    if is_auth_disabled():
        return redirect(url_for('index'))
    
    if settings.get('admin_password_hash'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Check if user chose to disable auth during setup
        auth_disabled = request.form.get('auth_disabled') == 'on'
        
        if auth_disabled:
            # User chose to skip auth setup
            settings['auth_disabled'] = True
            save_settings(settings)
            login_user(User(1))
            return redirect(url_for('index'))
        
        pw = request.form.get('password')
        confirm = request.form.get('confirm_password')
        
        if pw != confirm:
            flash("Passwords do not match")
        elif len(pw) < 4:
            flash("Password is too short")
        else:
            settings['admin_password_hash'] = generate_password_hash(pw)
            save_settings(settings)
            login_user(User(1))
            return redirect(url_for('index'))

    return render_template('login.html', title="Create Admin Password", btn_text="Set Password", is_setup=True)

@app.route('/logout')
@optional_login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/set_language/<lang>', methods=['POST'])
@optional_login_required
def set_language(lang):
    """Set the user's preferred language."""
    if lang not in LANGUAGES:
        return jsonify({'success': False, 'error': 'Invalid language'}), 400
    
    settings = load_settings()
    settings['language'] = lang
    save_settings(settings)
    
    return jsonify({'success': True})

@app.route('/api/status')
@optional_login_required
def get_status():
    return jsonify(scanner.state)

@app.route('/api/test_connection', methods=['POST'])
@optional_login_required
def test_connection():
    from plexapi.server import PlexServer
    data = request.json
    
    # Load existing settings to find the real token if the UI sent a mask
    current_settings = load_settings() 
    token = data.get('plex_token')
    url = data.get('plex_url')

    # If the UI sent the mask, use the actual token from the file
    if token == '********':
        token = current_settings.get('plex_token')

    try:
        # Use the 'token' variable we just validated instead of data['plex_token']
        plex = PlexServer(url, token)
        libs = [s.title for s in plex.library.sections() if s.type in ['movie', 'show']]
        return jsonify({'success': True, 'libraries': libs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/search_plex', methods=['POST'])
@optional_login_required
def search_plex():
    from plexapi.server import PlexServer
    settings = load_settings()
    query = request.json.get('query')
    
    if not query or not settings.get('plex_url') or not settings.get('plex_token'):
        return jsonify({'results': []})

    try:
        plex = PlexServer(settings['plex_url'], settings['plex_token'])
        # Search and filter for Movies and Episodes only
        results = plex.search(query)
        output = []
        for item in results:
            if item.type == 'movie':
                output.append({
                    'id': item.ratingKey,
                    'title': f"{item.title} ({item.year})",
                    'type': 'Movie'
                })
            elif item.type == 'episode':
                title = f"{item.grandparentTitle} - {item.seasonEpisode} - {item.title}"
                output.append({
                    'id': item.ratingKey,
                    'title': title,
                    'type': 'Episode'
                })
        return jsonify({'results': output})
    except Exception as e:
        return jsonify({'error': str(e), 'results': []})

@app.route('/api/history')
@optional_login_required
def get_history():
    return jsonify(scanner.get_recent_history())


# Serve favicon files placed under templates/favicon at /favicon/*
@app.route('/favicon/<path:filename>')
def favicon_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'templates', 'favicon'), filename)

@app.route('/api/save_settings', methods=['POST'])
@optional_login_required
def save_settings_route():
    new_data = request.json
    old_settings = load_settings()
    
    # Check if the user sent the 'mask' or left it empty.
    # If they did, we keep the REAL token from the old settings file.
    if new_data.get('plex_token') == '********' or not new_data.get('plex_token'):
        new_data['plex_token'] = old_settings.get('plex_token')

    # Preserve the password hash (don't let the UI overwrite it)
    if 'admin_password_hash' in old_settings:
        new_data['admin_password_hash'] = old_settings['admin_password_hash']
    
    # Preserve auth_disabled setting if not explicitly set (for backward compatibility)
    if 'auth_disabled' not in new_data and 'auth_disabled' in old_settings:
        new_data['auth_disabled'] = old_settings['auth_disabled']
    
    save_settings(new_data)
    scanner.restart_event.set()
    
    return jsonify({'success': True})

@app.route('/api/change_password', methods=['POST'])
@optional_login_required
def change_password():
    data = request.json
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    settings = load_settings()
    stored_hash = settings.get('admin_password_hash')
    
    # If no password is set, they can't change it
    if not stored_hash:
        return jsonify({'success': False, 'error': 'No password is currently set'})
    
    # Verify current password
    if not check_password_hash(stored_hash, current_password):
        return jsonify({'success': False, 'error': 'Current password is incorrect'})
    
    # Validate new password
    if not new_password or len(new_password) < 4:
        return jsonify({'success': False, 'error': 'Password must be at least 4 characters'})
    
    # Update the password hash
    settings['admin_password_hash'] = generate_password_hash(new_password)
    save_settings(settings)
    
    return jsonify({'success': True, 'message': 'Password changed successfully'})

scanner.start_background_thread()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6580)