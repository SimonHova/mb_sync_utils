#!/bin/bash

# --- Configuration ---
# Set the starting directory for the recursive search
SEARCH_DIR="/media/Take/Music"
# Target Bitrate for MP3 conversion
TARGET_BITRATE="192k" 
# FFmpeg logging options for clean output
FFMPEG_LOGS="-hide_banner -loglevel warning"

# --- Conversion Logic ---

# Check if the starting directory exists
if [ ! -d "$SEARCH_DIR" ]; then
    echo "Error: Directory '$SEARCH_DIR' not found."
    exit 1
fi

echo "Starting conversion of M4A to MP3 @ $TARGET_BITRATE in $SEARCH_DIR..."
echo "---"

# Find all .m4a files recursively and execute the conversion inside a sub-shell.
# {} is a placeholder for the found filename.
# \+ allows find to pass multiple files to a single command execution if possible.
find "$SEARCH_DIR" -type f -name "*.m4a" -exec bash -c '
    input_file="$1"
    output_file="${input_file%.m4a}.mp3"
    
    echo "Processing: $input_file"
    echo "Outputting to: $output_file"
    
    # Run FFmpeg command using the robustly handled variables
    ffmpeg $FFMPEG_LOGS -i "$input_file" -codec:a libmp3lame -b:a $2 -vn -y "$output_file"
    
    # Check if ffmpeg conversion was successful (exit code 0)
    if [ $? -eq 0 ]; then
        echo "Conversion successful. Deleting original file: $input_file"
        rm -f "$input_file"
    else
        echo "Error: Conversion failed for $input_file. Keeping original file."
    fi
    echo "---"

' bash {} "$TARGET_BITRATE" \;

echo "Script finished."
