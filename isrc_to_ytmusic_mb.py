import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import musicbrainzngs
import requests
from bs4 import BeautifulSoup

# Initialize MusicBrainz (User-Agent required by MB policy)
musicbrainzngs.set_useragent(
    "MBSyncUtils",
    "1.0",
    "https://github.com/yourusername/mb_sync_utils",
)

CACHE_DIR = "./.cache"
DEFAULT_SPOTDL_CONFIG = os.path.expanduser("~/.config/spotdl/config.json")


def load_env_file():
    """Simple parser for .env file if present in the current working directory."""
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip('"\''))


def resolve_ytdlp_path(custom_path: str = None) -> str:
    """Finds the yt-dlp executable path via argument, env var, or system search."""
    if custom_path and os.path.exists(custom_path):
        return custom_path

    env_path = os.getenv("YTDLP_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    home = os.path.expanduser("~")
    candidates = [
        "yt-dlp",
        f"{home}/.local/bin/yt-dlp",
        f"{home}/.local/share/uv/tools/spotdl/bin/yt-dlp",
        "/usr/local/bin/yt-dlp",
        "/usr/bin/yt-dlp",
    ]

    for candidate in candidates:
        if candidate == "yt-dlp":
            if shutil.which("yt-dlp"):
                return "yt-dlp"
        elif os.path.exists(candidate):
            return candidate

    return "yt-dlp"


def get_spotdl_output_template() -> str:
    """Reads ~/.config/spotdl/config.json to get the user's preferred output path template."""
    config_path = os.getenv("SPOTDL_CONFIG_PATH", DEFAULT_SPOTDL_CONFIG)

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                output_str = config_data.get("output")
                if output_str:
                    print(f"⚙️ Loaded output template from SpotDL config: {output_str}")
                    return output_str
        except Exception as e:
            print(f"⚠️ Could not read SpotDL config at {config_path}: {e}")

    # Fallback template if config file doesn't exist
    return "/media/Put/Downloads/yt-fetch/music/{album}/{artists} - {title}.{output-ext}"


def sanitize_filename(name: str) -> str:
    """Removes invalid path characters."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def build_output_path(template: str, album: str, artist: str, title: str, track_num: int, ext: str = "mp3") -> str:
    """Replaces SpotDL placeholders with sanitized track metadata for yt-dlp."""
    safe_album = sanitize_filename(album)
    safe_artist = sanitize_filename(artist)
    safe_title = sanitize_filename(title)
    formatted_num = f"{track_num:02d}"

    path = template

    # SpotDL placeholder mapping
    replacements = {
        "{album}": safe_album,
        "{artists}": safe_artist,
        "{artist}": safe_artist,
        "{title}": safe_title,
        "{track-number}": formatted_num,
        "{track_number}": formatted_num,
        "{disc-number}": "01",
        "{disc_number}": "01",
        "{output-ext}": ext,
        "{ext}": ext,
    }

    for key, value in replacements.items():
        path = path.replace(key, value)

    return path


def extract_spotify_id(url_or_id: str) -> str:
    match = re.search(r"([a-zA-Z0-9]{22})", url_or_id)
    if not match:
        raise ValueError("Invalid Spotify Album URL or ID")
    return match.group(1)


def get_cached_data(spotify_id: str) -> dict | None:
    cache_file = os.path.join(CACHE_DIR, f"{spotify_id}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_cache_data(spotify_id: str, data: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"{spotify_id}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def fetch_isrchunt_tracks(spotify_id: str) -> dict:
    """Scrapes Spotify album metadata, tracks, and ISRCs from ISRCHunt."""
    target_url = f"https://isrchunt.com/spotify/importisrc?releaseId={spotify_id}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    res = requests.get(target_url, headers=headers)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    album_title_elem = soup.find("h1", class_="card-title")
    album_title = album_title_elem.text.strip() if album_title_elem else "Unknown Album"

    artist_p = soup.find(lambda tag: tag.name == "p" and "Artist:" in tag.text)
    artist_name = artist_p.text.replace("Artist:", "").strip() if artist_p else "Unknown Artist"

    table = soup.find("table", class_="table")
    if not table:
        return {"album": album_title, "artist": artist_name, "tracks": []}

    tracks = []
    rows = table.find_all("tr")[1:]

    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 4:
            track_num = cols[0].text.strip()
            spotify_title = html.unescape(cols[1].text.strip())
            spotify_isrc = cols[3].text.strip()

            if spotify_isrc and len(spotify_isrc) == 12:
                tracks.append(
                    {
                        "track_number": int(track_num) if track_num.isdigit() else 0,
                        "title": spotify_title,
                        "isrc": spotify_isrc,
                    }
                )

    return {"album": album_title, "artist": artist_name, "tracks": tracks}


def process_isrcs_against_musicbrainz(album_data: dict, spotify_id: str, download_now: bool = False, ytdlp_binary: str = "yt-dlp"):
    """Queries MB by ISRC, filters strictly for music.youtube.com links, and saves output to cache."""
    tracks = album_data["tracks"]
    album_name = album_data["album"]
    artist_name = album_data["artist"]

    list_1_downloadable = []
    list_2_yt_link_issues = []

    print(f"\nProcessing {len(tracks)} ISRCs for '{album_name}' by '{artist_name}'...\n" + "=" * 70)

    for track in tracks:
        isrc = track["isrc"]
        title = track["title"]
        num = track["track_number"]

        print(f"[{num:02d}] Querying MB for ISRC: {isrc} ({title})...")

        try:
            time.sleep(1.0)  # MB Rate Limit

            isrc_res = musicbrainzngs.get_recordings_by_isrc(isrc)
            recording_list = isrc_res.get("isrc", {}).get("recording-list", [])

            if not recording_list:
                mb_isrc_url = f"https://musicbrainz.org/isrc/{isrc}"
                list_2_yt_link_issues.append(
                    {
                        "track_number": num,
                        "title": title,
                        "isrc": isrc,
                        "reason": "ISRC not found on MusicBrainz",
                        "mb_url": mb_isrc_url,
                        "yt_urls": [],
                    }
                )
                print("   ❌ ISRC not found on MusicBrainz")
                continue

            all_ytm_urls = []
            all_yt_urls = []
            primary_mbid = recording_list[0]["id"]
            mb_recording_url = f"https://musicbrainz.org/recording/{primary_mbid}"

            for rec in recording_list:
                time.sleep(1.0)  # MB Rate Limit
                rec_detail = musicbrainzngs.get_recording_by_id(rec["id"], includes=["url-rels"])
                relations = rec_detail.get("recording", {}).get("url-relation-list", [])

                for rel in relations:
                    target_url = rel.get("target", "")
                    if "music.youtube.com" in target_url:
                        all_ytm_urls.append(target_url)
                    elif "youtube.com" in target_url or "youtu.be" in target_url:
                        all_yt_urls.append(target_url)

            unique_ytm_urls = list(set(all_ytm_urls))
            unique_yt_urls = list(set(all_yt_urls))

            if len(unique_ytm_urls) == 1:
                list_1_downloadable.append(
                    {
                        "track_number": num,
                        "title": title,
                        "artist": artist_name,
                        "album": album_name,
                        "isrc": isrc,
                        "mbid": primary_mbid,
                        "yt_url": unique_ytm_urls[0],
                    }
                )
                print(f"   ✅ Single YTM Link Found: {unique_ytm_urls[0]}")

            else:
                if len(unique_ytm_urls) > 1:
                    reason = f"Multiple competing YTM links found ({len(unique_ytm_urls)})"
                    target_links = unique_ytm_urls
                elif len(unique_yt_urls) > 0:
                    reason = f"No YTM links found (Only standard YouTube links exist: {len(unique_yt_urls)})"
                    target_links = unique_yt_urls
                else:
                    reason = "No YouTube links linked on MB"
                    target_links = []

                list_2_yt_link_issues.append(
                    {
                        "track_number": num,
                        "title": title,
                        "isrc": isrc,
                        "mbid": primary_mbid,
                        "mb_url": mb_recording_url,
                        "reason": reason,
                        "yt_urls": target_links,
                    }
                )
                print(f"   ⚠️ {reason}")

        except musicbrainzngs.ResponseError as e:
            mb_isrc_url = f"https://musicbrainz.org/isrc/{isrc}"
            list_2_yt_link_issues.append(
                {
                    "track_number": num,
                    "title": title,
                    "isrc": isrc,
                    "reason": "ISRC error on MB",
                    "mb_url": mb_isrc_url,
                    "yt_urls": [],
                }
            )
            print(f"   ❌ MB Response Error: {e}")

    processed_output = {
        "spotify_id": spotify_id,
        "album": album_name,
        "artist": artist_name,
        "downloadable_tracks": list_1_downloadable,
        "issue_tracks": list_2_yt_link_issues,
    }
    save_cache_data(spotify_id, processed_output)

    _print_summary(list_1_downloadable, list_2_yt_link_issues)

    if download_now and list_1_downloadable:
        download_album_with_ytdlp(album_name, artist_name, list_1_downloadable, ytdlp_binary)


def download_album_with_ytdlp(album: str, artist: str, tracks: list[dict], ytdlp_binary: str):
    """Downloads tracks using the output path structure defined in spotdl's config.json."""
    output_template = get_spotdl_output_template()

    print("\n" + "=" * 70)
    print(f" STARTING YT-DLP ALBUM DOWNLOAD (Using: {ytdlp_binary}) ")
    print("=" * 70)

    for item in tracks:
        url = item["yt_url"]
        num = item["track_number"]
        title = item["title"]

        # Calculate exact target output path from SpotDL template
        target_file_path = build_output_path(
            output_template,
            album=album,
            artist=artist,
            title=title,
            track_num=num,
            ext="mp3",
        )

        target_dir = os.path.dirname(target_file_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        cmd = [
            ytdlp_binary,
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--parse-metadata", f"title:{title}",
            "--parse-metadata", f"artist:{artist}",
            "--parse-metadata", f"album:{album}",
            "-o", target_file_path,
            url,
        ]

        print(f"\nDownloading [{num:02d}] {title}")
        print(f"   Destination: {target_file_path}")

        try:
            subprocess.run(cmd, check=True)
            print("   Done!")
        except Exception as e:
            print(f"   ❌ Download failed for {title}: {e}")


def _print_summary(list_1, list_2):
    print("\n" + "=" * 70)
    print(" SUMMARY REPORT ")
    print("=" * 70)

    print(f"\n1️⃣ READY FOR YT-DLP DOWNLOAD ({len(list_1)} tracks):")
    print("-" * 50)
    for item in list_1:
        print(f"  [{item['track_number']:02d}] {item['title']} (ISRC: {item['isrc']})")
        print(f"       URL:  {item['yt_url']}")

    print(f"\n2️⃣ YT LINK ISSUES ({len(list_2)} tracks):")
    print("-" * 50)
    for item in list_2:
        print(f"  [{item['track_number']:02d}] {item['title']} (ISRC: {item['isrc']})")
        print(f"       MB URL: {item['mb_url']}")
        print(f"       Issue:  {item['reason']}")
        if item["yt_urls"]:
            print(f"       URLs:   {', '.join(item['yt_urls'])}")


if __name__ == "__main__":
    load_env_file()

    album_url = "https://open.spotify.com/album/6wEh2L2nX5qVc7fDgCMGNn"
    download_flag = False
    refresh_flag = False
    custom_ytdlp = None

    for idx, arg in enumerate(sys.argv):
        if arg.startswith("http") or (len(arg) == 22 and arg.isalnum() and idx > 0):
            album_url = arg
        elif arg == "--download":
            download_flag = True
        elif arg == "--refresh":
            refresh_flag = True
        elif arg == "--yt-dlp-path" and idx + 1 < len(sys.argv):
            custom_ytdlp = sys.argv[idx + 1]

    spotify_id = extract_spotify_id(album_url)
    ytdlp_bin = resolve_ytdlp_path(custom_ytdlp)

    cached_data = None if refresh_flag else get_cached_data(spotify_id)

    if cached_data:
        print(f"⚡ Loaded cached results for album '{cached_data['album']}' by '{cached_data['artist']}' (.cache/{spotify_id}.json)")
        _print_summary(cached_data["downloadable_tracks"], cached_data["issue_tracks"])

        if download_flag and cached_data["downloadable_tracks"]:
            download_album_with_ytdlp(
                cached_data["album"],
                cached_data["artist"],
                cached_data["downloadable_tracks"],
                ytdlp_bin,
            )
    else:
        album_data = fetch_isrchunt_tracks(spotify_id)
        if album_data.get("tracks"):
            process_isrcs_against_musicbrainz(
                album_data,
                spotify_id,
                download_now=download_flag,
                ytdlp_binary=ytdlp_bin,
            )
        else:
            print("No tracks found on ISRCHunt.")