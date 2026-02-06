#!/bin/bash

# Default to 1000 if no environment variable is set
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Starting with PUID: $PUID and PGID: $PGID"

# Update the 'appuser' and 'appgroup' inside the container to match the requested IDs
groupmod -o -g "$PGID" appgroup
usermod -o -u "$PUID" appuser

# Fix permissions on the config folder so the app can write to it
echo "Fixing permissions on /config..."
chown -R appuser:appgroup /config
chown -R appuser:appgroup /app

# Step down from root and run the command (gunicorn) as 'appuser'
exec gosu appuser "$@"