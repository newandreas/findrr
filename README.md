# Findrr of Bad Files

**Findrr of Bad Files** is a self-hosted health check tool for Plex Media Server. It acts as a virtual client, attempting to transcode and stream every item in your library to ensure file integrity.

This app was coded with an LLM/AI (Google Gemini), I am not a professional coder. Don't trust the administrator password to be safe enough to expose the WebUI to the internet without a reverse proxy with authentication on top!

Unlike simpler video integrity checks using ffmpeg, Findrr forces Plex to transcode the video and burn in subtitles, catching stuff that only appears during real user playback.

---

## Features

* **Real-World Playback Test:** Forces Plex to transcode the start of your videos, catching corrupt files that standard scans miss.
* **Subtitle Testing:** Automatically detects subtitle languages and forces a burn-in transcode to verify subtitle file integrity.
* **WebUI:** A clean Web UI for first time setup, viewing live progress, scan history, and managing settings.
* **Smart Caching:** Uses a local SQLite database to track file fingerprints. Only re-scans files that have changed or are new 
* **Priority Queueing:** Want to test a specific movie or show first? Set a "Priority Title" to jump it to the front of the scan queue.

## **Granular Discord Notifications:**
* **Immediate Alerts:** Get pinged the second a corruption is found.
* **Failure Reports:** Get a summary of all broken files when the scan finishes.
* **Success Reports:** Summary when periodic scans finish clean.
* **Supports mentions:** Add your UserID to get pinged directly.



---

## 🛠️ Installation

### Docker Compose

Create a `docker-compose.yml` file:

```yaml
services:
  findrr:
    container_name: findrr
    image: ghcr.io/newandreas/findrr:latest
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./config:/config
    environment:
      - PUID=1000 # User ID (run 'id -u' on host)
      - PGID=1000 # Group ID (run 'id -g' on host)
      - PYTHONUNBUFFERED=1 # Ensures logs show up instantly

```

Run the container:

```bash
docker compose up -d

```

### Accessing the UI

Open your browser and navigate to:
`http://YOUR_SERVER_IP:5000`

On the first run, you will be asked to create an **Admin Password**.

---

## ⚙️ Configuration

Once logged in, navigate to **Settings** to configure Findrr.

### 1. Server Connection

* **Plex URL:** The local IP of your Plex server (e.g., `http://192.168.1.100:32400`).
* **Plex Token:** Your X-Plex-Token. [How to find your token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

### 2. Scan Settings

* **Target Languages:** Comma-separated list of subtitle languages to test.

* **Priority Title:** If set (e.g., "Futurama"), this show or movie will be scanned before anything else.

### 3. Notifications (Discord)

You can configure exactly how much noise Findrr makes:

* **📢 Immediate Alert:** Sends a message (and tags the user if userID is added) immediately when a *new* fault is found.
* **❌ Summary Report (Faults):** Sends a summary list of failed items when the scan loop finishes. (and tags the user if userID is added)
* **✅ Summary Report (Success):** Sends a clean health report even if no errors were found. (can be spammy if you don't change the default 1 hour scan interval)

---

##  How It Works

1. **Fingerprinting:** When the scanner starts, it looks at the file size and modification time of your media.
2. **Database Check:** It checks `history.db`. If the file matches a previous "PASS" record, it is skipped (shown as "⏩ Passed & cached in DB" in UI).
3. **Video Test:** If the file is new or changed, it requests a transcoded stream from Plex.
4. **Subtitle Test:** If the video passes, it iterates through the subtitle streams matching your requested languages and attempts to burn them in.
5. **Reporting:**
* **PASS:** The file fingerprint is saved to the DB.
* **FAIL:** The file is marked as failed, added to the "Active Failures" list, and a Discord notification is triggered based on your settings.



---

## 📄 License

[MIT](https://www.google.com/search?q=LICENSE)
