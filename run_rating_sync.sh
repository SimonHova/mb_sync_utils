#!/bin/bash

# --- Concurrency Control ---
# Define a single, shared lock file for ALL sync processes
LOCK_FILE="/tmp/mb_sync_all.lock"

# Attempt to acquire the lock. 
# -x: Exclusive lock
# -n: Non-blocking (exit immediately if locked)
# -c: Create the file if it doesn't exist
# -w 0: Wait time of 0 (non-blocking)
if ! command -v flock >/dev/null 2>&1; then
    echo "ERROR: 'flock' command not found. Cannot ensure exclusivity."
    exit 1
fi

(
    # Attempt to lock the file descriptor 200
    flock -x -n 200 || {
        echo "ERROR: Another MusicBrainz sync process is already running. Exiting gracefully."
        exit 1
    }

    # --- MAIN SCRIPT LOGIC (Only runs if lock is acquired) ---
    
    # Check Required Variables
    if [ -z "$PYTHON_BIN" ] || [ -z "$SCRIPT_PATH" ] || [ -z "$BASE_CONFIG_DIR" ] || [ -z "$COMMON_PY_ARGS" ] || [ -z "$USER_ID" ]; then
        echo "ERROR: One or more required environment variables are missing."
        exit 1
    fi

    echo "Starting exclusive MusicBrainz sync for user: $USER_ID"
    
    CONFIG_FILE="${BASE_CONFIG_DIR}/${USER_ID}.ini"
    
    # Execute the Python script
    "$PYTHON_BIN" "$SCRIPT_PATH" \
        $COMMON_PY_ARGS \
        "--config" "$CONFIG_FILE"
    
    # Check exit status
    if [ $? -ne 0 ]; then
        echo "ERROR: Sync for $USER_ID FAILED!"
        exit 1
    else
        echo "Sync for $USER_ID completed successfully."
    fi

) 200> "$LOCK_FILE"  # Associates file descriptor 200 with the lock file

exit 0 # Script always exits 0 unless flock fails or required vars are missing
