import os
import time
import sqlite3
import datetime
import requests
import json
import threading
from plexapi.server import PlexServer

# Global Control Flags
stop_event = threading.Event()
restart_event = threading.Event()

CONFIG_PATH = '/config/settings.json'
DB_PATH = '/config/history.db'

state = {
    'status': 'Idle',
    'current_file': '',
    'current_activity': '',
    'progress': 0,
    'total_items': 0,
    'scanned': 0,
    'failed': 0,
    'passed': 0,
    'skipped': 0,
    'subtitle_stats': {},
    'ignored_subtitle_stats': {},
    'failures': [],
    'last_scan_time': None
}

def load_settings():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS file_checks (
                    file_path TEXT PRIMARY KEY,
                    file_size INTEGER,
                    mtime REAL,
                    last_checked TIMESTAMP,
                    status TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS scan_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    libraries TEXT,
                    scanned INTEGER,
                    passed INTEGER,
                    failed INTEGER,
                    skipped INTEGER
                )''')
    conn.commit()
    return conn

def save_scan_history(conn, libraries, stats):
    try:
        c = conn.cursor()
        c.execute('''INSERT INTO scan_history (timestamp, libraries, scanned, passed, failed, skipped)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                     (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
                      ", ".join(libraries), 
                      stats['scanned'], 
                      stats['passed'], 
                      stats['failed'], 
                      stats['skipped']))
        c.execute("DELETE FROM scan_history WHERE id NOT IN (SELECT id FROM scan_history ORDER BY id DESC LIMIT 50)")
        conn.commit()
    except Exception as e:
        print(f"Error saving history: {e}")

def get_recent_history():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT timestamp, libraries, scanned, passed, failed, skipped FROM scan_history ORDER BY id DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        
        history = []
        for r in rows:
            history.append({
                'timestamp': r[0],
                'libraries': r[1],
                'scanned': r[2],
                'passed': r[3],
                'failed': r[4],
                'skipped': r[5]
            })
        return history
    except:
        return []

def get_file_fingerprint(part):
    return {
        'path': part.file,
        'size': part.size,
        'mtime': getattr(part, 'updatedAt', 0) 
    }

def should_skip(conn, fingerprint):
    c = conn.cursor()
    c.execute("SELECT file_size, mtime, status FROM file_checks WHERE file_path=?", (fingerprint['path'],))
    row = c.fetchone()
    if row:
        stored_size, stored_mtime, status = row
        if stored_size == fingerprint['size'] and status == 'PASS':
            return True
    return False

def update_db(conn, fingerprint, status):
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO file_checks (file_path, file_size, mtime, last_checked, status)
                 VALUES (?, ?, ?, ?, ?)''', 
                 (fingerprint['path'], fingerprint['size'], fingerprint['mtime'], datetime.datetime.now(), status))
    conn.commit()

def verify_stream(media_item, subtitle_stream=None):
    params = {
        'videoResolution': '720x480',
        'maxVideoBitrate': 2000,
        'quality': 5
    }
    if subtitle_stream:
        params['subtitleStreamID'] = subtitle_stream.id
        params['subtitles'] = 'burn' 

    try:
        url = media_item.getStreamURL(**params)
        with requests.get(url, stream=True, timeout=15) as r:
            if r.status_code == 200:
                bytes_read = 0
                for chunk in r.iter_content(chunk_size=1024*1024):
                    bytes_read += len(chunk)
                    if bytes_read >= 10 * 1024 * 1024:
                        return True
            return False
    except:
        return False

def send_canary_alert(settings, title, status_type, message, detail_field=None):
    """
    Sends a specialized alert for Canary Test events.
    status_type: "OUTAGE" (Red), "RECOVERED" (Green), "MISSING" (Orange), "CHANGED" (Blue)
    """
    webhook = settings.get('discord_webhook')
    if not webhook: return

    userid = settings.get('discord_userid', '').strip()
    mention = f"<@{userid}> " if userid else ""

    if status_type == "OUTAGE":
        color = 0xFF0000  # Red
        embed_title = "🚨 SYSTEM OUTAGE DETECTED"
        desc = "**The Canary File Test failed.** The Plex Transcoder may be down."
    elif status_type == "RECOVERED":
        color = 0x00FF00  # Green
        embed_title = "✅ SYSTEM RESTORED"
        desc = "**The Canary File Test passed.** The Plex Transcoder appears to be working again."
    elif status_type == "MISSING":
        color = 0xFFA500  # Orange
        embed_title = "⚠️ CANARY CONFIGURATION WARNING"
        desc = "**A Canary File Test item is missing.** It may have been deleted from Plex."
        mention = "" # Don't ping for missing files, just log it
    elif status_type == "CHANGED":
        color = 0x0099FF # Blue
        embed_title = "ℹ️ CANARY FILE UPDATED"
        desc = "**The Canary File Test file has changed.** A new scan was performed."
        mention = "" 
    else:
        color = 0xCCCCCC
        embed_title = "Canary Notification"
        desc = message

    fields = [
        {"name": "File/Title", "value": title, "inline": False},
        {"name": "Status", "value": message, "inline": False}
    ]
    
    if detail_field:
        fields.append(detail_field)

    embed = {
        "title": embed_title,
        "description": desc,
        "color": color,
        "fields": fields,
        "footer": {"text": "Canary File Test • Findrr"}
    }

    try:
        requests.post(webhook, json={"content": mention, "embeds": [embed]})
    except Exception as e:
        print(f"Discord Error: {e}")

def send_immediate_alert(settings, failure_data):
    webhook = settings.get('discord_webhook')
    if not webhook: return
    time.sleep(2) 

    userid = settings.get('discord_userid', '').strip()
    mention = f"<@{userid}> " if userid else ""

    embed = {
        "title": "❌ New Transcode Failure Detected",
        "color": 0xFF9900, 
        "fields": [
            {"name": "Title", "value": failure_data['title'], "inline": True},
            {"name": "Reason", "value": failure_data['reason'], "inline": True},
            {"name": "File", "value": f"`{failure_data['file']}`", "inline": False}
        ],
        "footer": {"text": "Findrr of Bad Files"}
    }
    
    try:
        requests.post(webhook, json={"content": mention, "embeds": [embed]})
    except Exception as e:
        print(f"Discord Error: {e}")

def send_discord_report(settings, stats, failures):
    webhook = settings.get('discord_webhook')
    if not webhook: return

    userid = settings.get('discord_userid', '').strip()
    mention = f"<@{userid}> " if userid else ""

    color = 0x00FF00
    if failures:
        color = 0xFF0000
    elif stats['failed'] > 0:
        color = 0xFF9900 

    sub_text = ""
    if stats['subtitle_stats']:
        sub_text = "\n\n**Subtitles Checked:**\n" + "\n".join([f"• {k}: {v}" for k,v in stats['subtitle_stats'].items()])

    description = (
        f"**Scanned:** {stats['scanned']}\n"
        f"**Passed:** {stats['passed']}\n"
        f"**Failed:** {stats['failed']} " + (f"(All previously reported)" if stats['failed'] > 0 and not failures else "") + "\n"
        f"**Skipped:** {stats['skipped']}"
        f"{sub_text}"
    )

    embeds = [{
        "title": "✅ Scan Complete" if not failures else "❌ New Failures Detected",
        "description": description,
        "color": color,
        "footer": {"text": "Findrr of Bad Files"}
    }]

    if failures:
        failure_text = ""
        for f in failures[:10]:
            failure_text += f"• **{f['title']}**\n   `{f['file']}` - {f['reason']}\n"
        if len(failures) > 10:
            failure_text += f"\n*...and {len(failures) - 10} more items.*"
        embeds[0]["fields"] = [{"name": "New Failed Items", "value": failure_text, "inline": False}]

    try:
        msg_content = mention if failures else ""
        requests.post(webhook, json={"content": msg_content, "embeds": embeds})
    except Exception as e:
        print(f"Discord Error: {e}")

def run_scan_loop():
    while not stop_event.is_set():
        if restart_event.is_set():
            restart_event.clear()

        settings = load_settings()
        
        notify_immediate = settings.get('notify_immediate', False)
        notify_on_failure = settings.get('notify_on_failure', True)
        notify_on_success = settings.get('notify_on_success', False)
        
        if not settings.get('plex_url') or not settings.get('plex_token'):
            state['status'] = 'Not Configured'
            time.sleep(5)
            continue

        try:
            state['status'] = 'Scanning'
            state['current_activity'] = 'Starting...'
            state['scanned'] = 0
            state['skipped'] = 0
            state['failed'] = 0
            state['passed'] = 0
            state['failures'] = [] 
            state['subtitle_stats'] = {} 
            state['ignored_subtitle_stats'] = {}
            
            new_discord_failures = []
            
            conn = init_db()
            plex = PlexServer(settings['plex_url'], settings['plex_token'])
            
            lang_setting = settings.get('target_languages', 'en, eng')
            user_langs = [x.strip().lower() for x in lang_setting.split(',') if x.strip()]
            EXPANSION_MAP = {
                'en': ['en', 'eng'],
                'no': ['no', 'nor', 'nob', 'nno'],
                'sv': ['sv', 'swe'],
                'da': ['da', 'dan'],
                'de': ['de', 'ger', 'deu'],
                'fr': ['fr', 'fre', 'fra'],
                'es': ['es', 'spa'],
                'it': ['it', 'ita'],
                'ja': ['ja', 'jpn'],
                'zh': ['zh', 'chi', 'zho']
            }
            target_languages = set(user_langs)
            for code in user_langs:
                if code in EXPANSION_MAP:
                    target_languages.update(EXPANSION_MAP[code])
            target_languages = list(target_languages)
            
            libraries = settings.get('libraries', [])
            
            # Canary file setup
            canary_file = settings.get('canary_files', [])
            canary_ids = [str(x['id']) for x in canary_file]
            found_canary_ids = set()

            items_to_process = []
            
            for lib_name in libraries:
                if restart_event.is_set(): break 
                try:
                    lib = plex.library.section(lib_name)
                    if lib.type == 'show':
                        for show in lib.all():
                            items_to_process.extend(show.episodes())
                    elif lib.type == 'movie':
                        items_to_process.extend(lib.all())
                except:
                    pass

            state['total_items'] = len(items_to_process)
            
            priority = settings.get('priority_title', '').strip().lower()
            if priority:
                def priority_sort_key(item):
                    if item.title and priority in item.title.lower(): return 0
                    if hasattr(item, 'grandparentTitle') and item.grandparentTitle:
                        if priority in item.grandparentTitle.lower(): return 0
                    return 1
                items_to_process.sort(key=priority_sort_key)

            for idx, item in enumerate(items_to_process):
                if restart_event.is_set(): 
                    state['status'] = 'Restarting...'
                    break
                if stop_event.is_set(): break
                
                state['progress'] = int((idx / max(1, len(items_to_process))) * 100)
                display_title = item.title
                if item.type == 'episode':
                    display_title = f"{item.grandparentTitle} - {item.seasonEpisode} - {item.title}"
                elif item.type == 'movie':
                    display_title = f"{item.title} ({item.year})"
                state['current_file'] = display_title

                for media in item.media:
                    for part in media.parts:
                        fingerprint = get_file_fingerprint(part)
                        
                        # Canary file Check
                        is_canary = str(item.ratingKey) in canary_ids
                        file_changed = False
                        
                        c = conn.cursor()
                        c.execute("SELECT file_size, mtime, status FROM file_checks WHERE file_path=?", (fingerprint['path'],))
                        row = c.fetchone()
                        previous_status = row[2] if row else None
                        
                        if is_canary:
                            found_canary_ids.add(str(item.ratingKey))
                            print(f"   [CANARY] Forcing scan on {display_title}")
                            
                            # Check for file changes
                            if row:
                                stored_size, stored_mtime, _ = row
                                if stored_size != fingerprint['size'] or stored_mtime != fingerprint['mtime']:
                                    file_changed = True
                                    print(f"   [CANARY] File changed detected for {display_title}")

                        if not is_canary and should_skip(conn, fingerprint):
                            state['skipped'] += 1
                            continue
                            
                        state['scanned'] += 1
                        state['current_activity'] = "Video Stream"
                        
                        success = verify_stream(item)
                        reason = "Video Transcode Failed"

                        if success:
                            item.reload()
                            for sub in item.subtitleStreams():
                                lang_code = sub.languageCode or 'unknown'
                                if lang_code in target_languages:
                                    state['current_activity'] = f"Subtitle: {lang_code}"
                                    if not verify_stream(item, subtitle_stream=sub):
                                        success = False
                                        reason = f"Subtitle Failed: {sub.language}"
                                        break
                                    else:
                                        state['subtitle_stats'][lang_code] = state['subtitle_stats'].get(lang_code, 0) + 1
                                else:
                                    state['ignored_subtitle_stats'][lang_code] = state['ignored_subtitle_stats'].get(lang_code, 0) + 1

                        status = 'PASS' if success else 'FAIL'
                        update_db(conn, fingerprint, status)

                        if success:
                            state['passed'] += 1
                            if is_canary:
                                if file_changed:
                                    send_canary_alert(settings, display_title, "CHANGED", "The file was updated and PASSED the scan.")
                                elif previous_status == 'FAIL':
                                    send_canary_alert(settings, display_title, "RECOVERED", "The file failed previously but is now playable.")
                        else:
                            state['failed'] += 1
                            failure_data = {'title': display_title, 'file': os.path.basename(part.file), 'reason': reason}
                            state['failures'].append(failure_data)
                            
                            is_new_failure = (previous_status != 'FAIL')
                            
                            if is_canary:
                                if file_changed:
                                    send_canary_alert(settings, display_title, "CHANGED", f"The file was updated and FAILED the scan.\nReason: {reason}")
                                elif is_new_failure:
                                    send_canary_alert(settings, display_title, "OUTAGE", reason)
                                    print(f"   [CANARY FILE FAIL] {display_title} (New)")
                                else:
                                    print(f"   [CANARY FILE FAIL] {display_title} (Known)")
                            else:
                                if is_new_failure:
                                    if notify_immediate:
                                        send_immediate_alert(settings, failure_data)
                                    new_discord_failures.append(failure_data)
                                    print(f"   [FAIL] {display_title} (New)")
                                else:
                                    print(f"   [FAIL] {display_title} (Known)")
                        
                        time.sleep(1)

            # --- END OF LOOP ---
            if not restart_event.is_set() and not stop_event.is_set():
                state['last_scan_time'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_scan_history(conn, libraries, state)
                
                # Check for Missing Canary Files
                missing_ids = set(canary_ids) - found_canary_ids
                if missing_ids and len(items_to_process) > 0: # Ensure scan actually ran
                    missing_titles = []
                    for m_id in missing_ids:
                        # Find title from settings
                        t = next((x['title'] for x in canary_files if str(x['id']) == m_id), f"ID: {m_id}")
                        missing_titles.append(t)
                    
                    list_text = "\n".join([f"• {t}" for t in missing_titles])
                    send_canary_alert(settings, "Multiple Files" if len(missing_titles)>1 else missing_titles[0], 
                                      "MISSING", 
                                      "The following configured Canary files were not found in Plex:", 
                                      detail_field={"name": "Missing Files", "value": list_text, "inline": False})

                # Summary Notifications
                should_send = False
                work_done = (state['scanned'] > 0 or state['skipped'] > 0 or state['failed'] > 0)
                
                if work_done:
                    has_failures = state['failed'] > 0
                    if has_failures:
                        if notify_on_failure: should_send = True
                    else:
                        if notify_on_success: should_send = True
                
                if should_send:
                    send_discord_report(settings, state, new_discord_failures)
                
            conn.close()
            
            if restart_event.is_set():
                continue

            if not stop_event.is_set():
                state['status'] = 'Sleeping'
                state['current_file'] = ''
                state['current_activity'] = ''
                state['progress'] = 100
                
                sleep_time = int(settings.get('scan_interval', 3600))
                for _ in range(sleep_time):
                    if stop_event.is_set(): break
                    if restart_event.is_set(): break
                    time.sleep(1)

        except Exception as e:
            print(f"CRITICAL ERROR: {e}") 
            state['status'] = f"Error: {str(e)}"
            time.sleep(60)

_thread_started = False
def start_background_thread():
    global _thread_started
    if _thread_started: return
    _thread_started = True
    t = threading.Thread(target=run_scan_loop)
    t.daemon = True
    t.start()