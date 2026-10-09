#!/bin/bash

# --- Concurrency Control ---
LOCK_FILE="/tmp/mb_sync_all.lock"

if ! command -v flock >/dev/null 2>&1; then
    echo "ERROR: 'flock' command not found. Cannot ensure exclusivity."
    exit 1
fi

# Run in subshell and capture its exit code
(
    flock -x -n 200 || {
        echo "ERROR: Another MusicBrainz sync process is already running."
        exit 1
    }

    if [ -z "$PYTHON_BIN" ] || [ -z "$SCRIPT_PATH" ] || [ -z "$BASE_CONFIG_DIR" ] || [ -z "$COMMON_PY_ARGS" ] || [ -z "$USER_ID" ]; then
        echo "ERROR: One or more required environment variables are missing."
        exit 1
    fi

    echo "Starting exclusive MusicBrainz sync for user: $USER_ID"

    CONFIG_FILE="${BASE_CONFIG_DIR}/${USER_ID}.ini"

    "$PYTHON_BIN" "$SCRIPT_PATH" \
        $COMMON_PY_ARGS \
        "--config" "$CONFIG_FILE"

    if [ $? -ne 0 ]; then
        echo "ERROR: Sync for $USER_ID FAILED!"
        exit 1
    else
        echo "Sync for $USER_ID completed successfully."
    fi

) 200> "$LOCK_FILE"

RC=$?
exit $RC
