import argparse
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
REGISTRY_FILE = os.path.join(CACHE_DIR, "isrc_registry.json")
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


def parse_duration_to_seconds(dur_str: str) -> int:
    """Converts duration strings like '03:38', '1:03:38', or millisecond strings '234920' into total seconds."""
    if not dur_str:
        return 0
    dur_str = str(dur_str).strip()
    if ":" in dur_str:
        parts = dur_str.split(":")
        try:
            if len(parts) == 2:  # MM:SS
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:  # HH:MM:SS
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return 0
    elif dur_str.isdigit():
        val = int(dur_str)
        if val > 10000:  # Value is in milliseconds
            return val // 1000
        return val
    return 0


def resolve_ytdlp_path(custom_path: str = None) -> str:
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
    config_path = os.getenv("SPOTDL_CONFIG_PATH", DEFAULT_SPOTDL_CONFIG)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                output_str = config_data.get("output")
                if output_str:
                    return output_str
        except Exception as e:
            print(f"⚠️ Could not read SpotDL config at {config_path}: {e}")

    return "/media/Put/Downloads/yt-fetch/music/{album}/{artists} - {title}.{output-ext}"


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def build_output_path(template: str, album: str, artist: str, title: str, track_num: int, ext: str = "mp3") -> str:
    safe_album = sanitize_filename(album)
    safe_artist = sanitize_filename(artist)
    safe_title = sanitize_filename(title)
    formatted_num = f"{track_num:02d}"

    path = template
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


def load_isrc_registry() -> dict:
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_isrc_registry(registry: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)


def get_cached_album(spotify_id: str) -> dict | None:
    cache_file = os.path.join(CACHE_DIR, f"{spotify_id}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_cached_album(spotify_id: str, data: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"{spotify_id}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def fetch_isrchunt_tracks(spotify_id: str) -> dict:
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
    album_artist_name = artist_p.text.replace("Artist:", "").strip() if artist_p else "Unknown Artist"

    table = soup.find("table", class_="table")
    if not table:
        return {"album": album_title, "artist": album_artist_name, "tracks": []}

    tracks = []
    rows = table.find_all("tr")[1:]

    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 4:
            track_num = cols[0].text.strip()
            spotify_title = html.unescape(cols[1].text.strip())
            dur_raw = cols[2].text.strip()
            spotify_isrc = cols[3].text.strip()

            dur_sec = parse_duration_to_seconds(dur_raw)

            if spotify_isrc and len(spotify_isrc) == 12:
                tracks.append(
                    {
                        "track_number": int(track_num) if track_num.isdigit() else 0,
                        "title": spotify_title,
                        "duration_sec": dur_sec,
                        "isrc": spotify_isrc,
                    }
                )

    return {"album": album_title, "artist": album_artist_name, "tracks": tracks}


def check_isrc_on_musicbrainz(
    isrc: str,
    title: str,
    num: int,
    fallback_artist: str,
    spotify_duration_sec: int = 0,
) -> tuple[dict | None, dict | None]:
    """Queries MusicBrainz for an ISRC, extracting track-level artist credits and verifying length."""
    print(f"[{num:02d}] Querying MB for ISRC: {isrc} ({title})...")
    try:
        time.sleep(1.0)  # Rate Limit
        isrc_res = musicbrainzngs.get_recordings_by_isrc(isrc, includes=["artist-credits"])
        recording_list = isrc_res.get("isrc", {}).get("recording-list", [])

        if not recording_list:
            return None, {
                "track_number": num,
                "title": title,
                "isrc": isrc,
                "duration_sec": spotify_duration_sec,
                "reason": "ISRC not found on MusicBrainz",
                "mb_url": f"https://musicbrainz.org/isrc/{isrc}",
                "yt_urls": [],
            }

        primary_mbid = recording_list[0]["id"]
        primary_mb_url = f"https://musicbrainz.org/recording/{primary_mbid}"

        # Duration Guard: 5 seconds tolerance
        TOLERANCE_SEC = 5
        valid_recordings = []

        for rec in recording_list:
            mb_ms = int(rec.get("length", 0)) if rec.get("length") else 0
            mb_sec = mb_ms // 1000

            if spotify_duration_sec > 0 and mb_sec > 0:
                diff = abs(spotify_duration_sec - mb_sec)
                if diff > TOLERANCE_SEC:
                    print(
                        f"   ⚠️ Duration mismatch on MBID {rec['id'][:8]}: "
                        f"Spotify ({spotify_duration_sec}s) vs MB ({mb_sec}s) - Skipping"
                    )
                    continue

            valid_recordings.append(rec)

        if not valid_recordings:
            print("   ❌ Duration check failed for all matching MB recordings.")
            return None, {
                "track_number": num,
                "title": title,
                "isrc": isrc,
                "duration_sec": spotify_duration_sec,
                "mbid": primary_mbid,
                "mb_url": primary_mb_url,
                "reason": f"Track duration mismatch against Spotify ({spotify_duration_sec}s)",
                "yt_urls": [],
            }

        # Evaluate valid recordings individually
        for rec in valid_recordings:
            time.sleep(1.0)  # Rate Limit
            rec_id = rec["id"]
            rec_detail = musicbrainzngs.get_recording_by_id(rec_id, includes=["url-rels", "artist-credits"])
            rec_data = rec_detail.get("recording", {})
            relations = rec_data.get("url-relation-list", [])

            # Pull actual Song Artist Credit from MB
            song_artist = rec_data.get("artist-credit-phrase") or fallback_artist

            ytm_strict_urls = []
            std_yt_urls = []

            for rel in relations:
                # SKIP ENDED RELATIONS
                is_ended = rel.get("ended")
                if is_ended == "true" or is_ended is True:
                    continue

                target_url = rel.get("target", "").strip()

                # ONLY literal music.youtube.com URLs are valid YTM links
                if "music.youtube.com" in target_url:
                    ytm_strict_urls.append(target_url)

                # Standard youtube links for error reporting
                elif "youtube.com" in target_url or "youtu.be" in target_url:
                    std_yt_urls.append(target_url)

            unique_ytm = list(dict.fromkeys(ytm_strict_urls))
            unique_std = list(dict.fromkeys(std_yt_urls))

            # Case A: Found EXACTLY 1 active music.youtube.com link
            if len(unique_ytm) == 1:
                print(f"   ✅ Single YTM Link Found on MBID {rec_id[:8]}: {unique_ytm[0]}")
                return {
                    "track_number": num,
                    "title": title,
                    "artist": song_artist,  # Track-level artist!
                    "isrc": isrc,
                    "mbid": rec_id,
                    "yt_url": unique_ytm[0],
                    "duration_sec": spotify_duration_sec,
                }, None

            # Case B: Multiple active music.youtube.com links
            elif len(unique_ytm) > 1:
                print(f"   ⚠️ Multiple YTM links on single recording MBID {rec_id[:8]}")
                return None, {
                    "track_number": num,
                    "title": title,
                    "isrc": isrc,
                    "duration_sec": spotify_duration_sec,
                    "mbid": rec_id,
                    "mb_url": f"https://musicbrainz.org/recording/{rec_id}",
                    "reason": f"Multiple competing YTM links on recording ({len(unique_ytm)})",
                    "yt_urls": unique_ytm,
                }

        # Case C: No active YTM link found across any duration-matched recording
        valid_mbid = valid_recordings[0]["id"]
        valid_mb_url = f"https://musicbrainz.org/recording/{valid_mbid}"

        if unique_std:
            reason = f"No YTM links found (Only standard YouTube links exist: {len(unique_std)})"
            urls_to_report = unique_std
        else:
            reason = "No YouTube links linked on MB"
            urls_to_report = []

        print(f"   ⚠️ {reason}")
        return None, {
            "track_number": num,
            "title": title,
            "isrc": isrc,
            "duration_sec": spotify_duration_sec,
            "mbid": valid_mbid,
            "mb_url": valid_mb_url,
            "reason": reason,
            "yt_urls": urls_to_report,
        }

    except musicbrainzngs.ResponseError as e:
        print(f"   ❌ MB Response Error: {e}")
        return None, {
            "track_number": num,
            "title": title,
            "isrc": isrc,
            "duration_sec": spotify_duration_sec,
            "reason": "ISRC error on MB",
            "mb_url": f"https://musicbrainz.org/isrc/{isrc}",
            "yt_urls": [],
        }


def process_album(spotify_id: str, refresh: bool = False, recheck_unresolved: bool = True) -> dict:
    registry = load_isrc_registry()
    cached_data = None if refresh else get_cached_album(spotify_id)

    if cached_data and not recheck_unresolved:
        return cached_data

    if not cached_data or refresh:
        album_data = fetch_isrchunt_tracks(spotify_id)
        tracks = album_data.get("tracks", [])
        album_name = album_data["album"]
        album_artist_name = album_data["artist"]
        downloadable = []
        unresolved = []
    else:
        tracks = []
        album_name = cached_data["album"]
        album_artist_name = cached_data["artist"]
        downloadable = cached_data.get("downloadable_tracks", [])
        unresolved = cached_data.get("issue_tracks", [])

    # Re-check unresolved tracks against global registry or MB
    if cached_data and recheck_unresolved and unresolved and not refresh:
        print(f"🔄 Re-checking {len(unresolved)} unresolved tracks on MusicBrainz...")
        updated_unresolved = []

        for item in unresolved:
            isrc = item["isrc"]

            # Load resolved track from Global Registry if available
            if isrc in registry and registry[isrc].get("status") == "resolved":
                print(f"[{item['track_number']:02d}] ⚡ Loaded ISRC {isrc} from Global Registry!")
                reg_item = dict(registry[isrc]["data"])
                reg_item["track_number"] = item["track_number"]
                reg_item["album"] = album_name  # Bind current album dynamically
                downloadable.append(reg_item)
                continue

            dl_item, issue_item = check_isrc_on_musicbrainz(
                isrc,
                item["title"],
                item["track_number"],
                fallback_artist=album_artist_name,
                spotify_duration_sec=item.get("duration_sec", 0),
            )
            if dl_item:
                dl_item["album"] = album_name
                downloadable.append(dl_item)

                # Store album-agnostic record in global registry
                reg_data = dict(dl_item)
                reg_data.pop("album", None)
                registry[isrc] = {"status": "resolved", "data": reg_data}

            if issue_item:
                updated_unresolved.append(issue_item)
                registry[isrc] = {"status": "unresolved", "data": issue_item}

        downloadable.sort(key=lambda x: x["track_number"])
        updated_unresolved.sort(key=lambda x: x["track_number"])

        result = {
            "spotify_id": spotify_id,
            "album": album_name,
            "artist": album_artist_name,
            "downloadable_tracks": downloadable,
            "issue_tracks": updated_unresolved,
        }
        save_isrc_registry(registry)
        save_cached_album(spotify_id, result)
        return result

    # Full fresh fetch
    print(f"\nProcessing {len(tracks)} ISRCs for '{album_name}' by '{album_artist_name}'...\n" + "=" * 70)

    for track in tracks:
        isrc = track["isrc"]
        num = track["track_number"]
        title = track["title"]
        dur = track["duration_sec"]

        # Check Global Registry
        if not refresh and isrc in registry and registry[isrc].get("status") == "resolved":
            print(f"[{num:02d}] ⚡ Found ISRC {isrc} in Global Registry ({title})")
            reg_item = dict(registry[isrc]["data"])
            reg_item["track_number"] = num
            reg_item["album"] = album_name  # Bind current album dynamically
            downloadable.append(reg_item)
            continue

        dl_item, issue_item = check_isrc_on_musicbrainz(
            isrc, title, num, fallback_artist=album_artist_name, spotify_duration_sec=dur
        )
        if dl_item:
            dl_item["album"] = album_name
            downloadable.append(dl_item)

            reg_data = dict(dl_item)
            reg_data.pop("album", None)
            registry[isrc] = {"status": "resolved", "data": reg_data}

        if issue_item:
            unresolved.append(issue_item)
            registry[isrc] = {"status": "unresolved", "data": issue_item}

    result = {
        "spotify_id": spotify_id,
        "album": album_name,
        "artist": album_artist_name,
        "downloadable_tracks": downloadable,
        "issue_tracks": unresolved,
    }
    save_isrc_registry(registry)
    save_cached_album(spotify_id, result)
    return result


def export_issues_file(album: str, artist: str, spotify_id: str, issue_tracks: list[dict]):
    filename = f"edit_list_{spotify_id}.txt"
    filepath = os.path.join(os.getcwd(), filename)
    issue_tracks_sorted = sorted(issue_tracks, key=lambda x: x["track_number"])

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("======================================================================\n")
        f.write(f" MUSICBRAINZ EDIT LIST: {artist} - {album}\n")
        f.write(f" Spotify Album ID: {spotify_id}\n")
        f.write(f" Total Unresolved Tracks: {len(issue_tracks_sorted)}\n")
        f.write("======================================================================\n\n")

        for item in issue_tracks_sorted:
            f.write(f"[{item['track_number']:02d}] {item['title']}\n")
            f.write(f"     ISRC:      {item['isrc']}\n")
            f.write(f"     MB URL:    {item['mb_url']}\n")
            f.write(f"     Issue:     {item['reason']}\n")
            if item.get("yt_urls"):
                f.write(f"     Found URLs: {', '.join(item['yt_urls'])}\n")
            f.write(f"{'-' * 60}\n")

    print(f"\n📝 Exported edit list for MusicBrainz to: {filepath}")


def download_album_with_ytdlp(album: str, artist: str, tracks: list[dict], ytdlp_binary: str, force_download: bool = False):
    output_template = get_spotdl_output_template()

    print("\n" + "=" * 70)
    print(f" STARTING YT-DLP ALBUM DOWNLOAD (Using: {ytdlp_binary}) ")
    print("=" * 70)

    for item in tracks:
        url = item["yt_url"]
        num = item["track_number"]
        title = item["title"]
        track_artist = item.get("artist", artist)  # Prefer song artist over album artist

        target_file_path = build_output_path(
            output_template,
            album=album,
            artist=track_artist,
            title=title,
            track_num=num,
            ext="mp3",
        )

        target_dir = os.path.dirname(target_file_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        if os.path.exists(target_file_path) and not force_download:
            print(f"\n⏭️ Skipping [{num:02d}] {title} by {track_artist} (File already exists)")
            print(f"   Location: {target_file_path}")
            continue

        cmd = [
            ytdlp_binary,
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--parse-metadata", f"title:{title}",
            "--parse-metadata", f"artist:{track_artist}",
            "--parse-metadata", f"album:{album}",
            "-o", target_file_path,
            url,
        ]

        print(f"\n📥 Downloading [{num:02d}] {title} by {track_artist}")
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
        track_artist = item.get("artist", "Unknown Artist")
        print(f"  [{item['track_number']:02d}] {item['title']} - {track_artist} (ISRC: {item['isrc']})")
        print(f"       URL:  {item['yt_url']}")

    print(f"\n2️⃣ YT LINK ISSUES ({len(list_2)} tracks):")
    print("-" * 50)
    for item in list_2:
        print(f"  [{item['track_number']:02d}] {item['title']} (ISRC: {item['isrc']})")
        print(f"       MB URL: {item['mb_url']}")
        print(f"       Issue:  {item['reason']}")
        if item["yt_urls"]:
            print(f"       URLs:   {', '.join(item['yt_urls'])}")


def main():
    load_env_file()

    parser = argparse.ArgumentParser(
        description="MusicBrainz Spotify ISRC to YouTube Music Importer & Downloader",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "url",
        metavar="SPOTIFY_URL_OR_ID",
        help="Spotify Album URL or 22-character Spotify Album ID",
    )
    parser.add_argument(
        "-d", "--download",
        action="store_true",
        help="Trigger yt-dlp to download all matched YouTube Music tracks",
    )
    parser.add_argument(
        "-e", "--export-issues",
        action="store_true",
        help="Export unresolved tracks/issues to a formatted text file (edit_list_<id>.txt)",
    )
    parser.add_argument(
        "-r", "--refresh",
        action="store_true",
        help="Bypass local cache completely and re-query ISRCHunt and MusicBrainz for all tracks",
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force re-downloading files with yt-dlp even if they already exist on disk",
    )
    parser.add_argument(
        "--yt-dlp-path",
        metavar="PATH",
        help="Explicit path to the yt-dlp binary (overrides PATH and .env)",
    )

    args = parser.parse_args()

    try:
        spotify_id = extract_spotify_id(args.url)
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    ytdlp_bin = resolve_ytdlp_path(args.yt_dlp_path)

    album_results = process_album(spotify_id, refresh=args.refresh, recheck_unresolved=True)

    _print_summary(album_results["downloadable_tracks"], album_results["issue_tracks"])

    if args.export_issues and album_results["issue_tracks"]:
        export_issues_file(
            album_results["album"],
            album_results["artist"],
            spotify_id,
            album_results["issue_tracks"],
        )

    if args.download and album_results["downloadable_tracks"]:
        download_album_with_ytdlp(
            album_results["album"],
            album_results["artist"],
            album_results["downloadable_tracks"],
            ytdlp_bin,
            force_download=args.force,
        )


if __name__ == "__main__":
    main()