#!/bin/bash

# --- Concurrency Control ---
# Use the SAME lock file if you want to block MusicBrainz syncs, 
# OR a NEW one (e.g., /tmp/ampache_catalog.lock) if they can run alongside MB syncs.
LOCK_FILE="/tmp/ampache_catalog.lock"

if ! command -v flock >/dev/null 2>&1; then
    echo "ERROR: 'flock' command not found."
    exit 1
fi

(
    # Attempt to lock (Exclusive, Non-blocking)
    flock -x -n 200 || {
        echo "ERROR: Ampache catalog update already in progress. Exiting."
        exit 1
    }

    echo "Starting Ampache Catalog Update..."

    # Task 1: Cleanup
    /usr/bin/php8.4 /opt/ampache/bin/cli run:updateCatalog --garbage --optimize
    
    # Task 2: Verify
    /usr/bin/php8.4 /opt/ampache/bin/cli run:updateCatalog --verify

    # Task 3: Update
    /usr/bin/php8.4 /opt/ampache/bin/cli run:updateCatalog --update


    echo "Ampache Catalog Update completed successfully."

) 200> "$LOCK_FILE"
