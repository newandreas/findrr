import os
import json
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import scanner

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))

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

# --- ROUTES ---

@app.route('/')
@login_required
def index():
    settings = load_settings()
    if not settings.get('plex_url') or not settings.get('plex_token'):
        return render_template('settings.html', settings=settings, first_run=True)
    return render_template('index.html')

@app.route('/settings')
@login_required
def settings_page():
    settings = load_settings()
    display_settings = settings.copy()
    
    if settings.get('plex_token'):
        # If a token exists, replace it with a mask.
        # The browser isn't served the plex token.
        display_settings['plex_token'] = '********'
    
    return render_template('settings.html', settings=display_settings, first_run=False)

# --- LOGIN FLOW ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    settings = load_settings()
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
    if settings.get('admin_password_hash'):
        return redirect(url_for('login'))

    if request.method == 'POST':
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
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/status')
@login_required
def get_status():
    return jsonify(scanner.state)

@app.route('/api/test_connection', methods=['POST'])
@login_required
def test_connection():
    from plexapi.server import PlexServer
    data = request.json
    try:
        plex = PlexServer(data.get('plex_url'), data.get('plex_token'))
        libs = [s.title for s in plex.library.sections() if s.type in ['movie', 'show']]
        return jsonify({'success': True, 'libraries': libs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/history')
@login_required
def get_history():
    return jsonify(scanner.get_recent_history())

@app.route('/api/save_settings', methods=['POST'])
@login_required
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
    
    save_settings(new_data)
    scanner.restart_event.set()
    
    return jsonify({'success': True})


scanner.start_background_thread()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6580)