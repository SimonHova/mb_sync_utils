import html
import os
import re
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


def fetch_isrchunt_tracks(spotify_album_url_or_id: str) -> dict:
    """Scrapes Spotify album metadata, tracks, and ISRCs from ISRCHunt."""
    match = re.search(r"([a-zA-Z0-9]{22})", spotify_album_url_or_id)
    if not match:
        raise ValueError("Invalid Spotify Album URL or ID")

    spotify_id = match.group(1)
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
    album_title = (
        album_title_elem.text.strip() if album_title_elem else "Unknown Album"
    )

    artist_p = soup.find(lambda tag: tag.name == "p" and "Artist:" in tag.text)
    artist_name = (
        artist_p.text.replace("Artist:", "").strip()
        if artist_p
        else "Unknown Artist"
    )

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


def process_isrcs_against_musicbrainz(album_data: dict, download_now: bool = False):
    """Queries MB by ISRC, filters strictly for music.youtube.com links, and categorizes results cleanly."""
    tracks = album_data["tracks"]
    album_name = album_data["album"]
    artist_name = album_data["artist"]

    list_1_downloadable = []
    list_2_ambiguous_recordings = []
    list_3_yt_link_issues = []

    print(f"\nProcessing {len(tracks)} ISRCs for '{album_name}' by '{artist_name}'...\n" + "=" * 70)

    for track in tracks:
        isrc = track["isrc"]
        title = track["title"]
        num = track["track_number"]

        print(f"[{num:02d}] Querying MB for ISRC: {isrc} ({title})...")

        try:
            time.sleep(1.0)  # MB Rate Limit

            # Query MB by ISRC
            isrc_res = musicbrainzngs.get_recordings_by_isrc(isrc)
            recording_list = isrc_res.get("isrc", {}).get("recording-list", [])

            if not recording_list:
                list_3_yt_link_issues.append(
                    {
                        "track_number": num,
                        "title": title,
                        "isrc": isrc,
                        "reason": "ISRC not found on MusicBrainz",
                        "yt_urls": [],
                    }
                )
                print("   ❌ ISRC not found on MusicBrainz")
                continue

            all_ytm_urls = []
            all_yt_urls = []
            rec_ids = [r["id"] for r in recording_list]

            # Collect URL relations from all matching recordings
            for rec in recording_list:
                time.sleep(1.0)  # MB Rate Limit
                rec_detail = musicbrainzngs.get_recording_by_id(
                    rec["id"], includes=["url-rels"]
                )
                relations = rec_detail.get("recording", {}).get("url-relation-list", [])

                for rel in relations:
                    target_url = rel.get("target", "")
                    if "music.youtube.com" in target_url:
                        all_ytm_urls.append(target_url)
                    elif "youtube.com" in target_url or "youtu.be" in target_url:
                        all_yt_urls.append(target_url)

            # Deduplicate strictly
            unique_ytm_urls = list(set(all_ytm_urls))
            unique_yt_urls = list(set(all_yt_urls))

            # --- CATEGORY 1: Exactly 1 YouTube Music Link Found ---
            if len(unique_ytm_urls) == 1:
                list_1_downloadable.append(
                    {
                        "track_number": num,
                        "title": title,
                        "artist": artist_name,
                        "album": album_name,
                        "isrc": isrc,
                        "mbid": rec_ids[0],
                        "yt_url": unique_ytm_urls[0],
                    }
                )
                print(f"   ✅ Single YTM Link Found: {unique_ytm_urls[0]}")

            # --- CATEGORY 3: Link Issues (0 or Multiple YTM Links) ---
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

                list_3_yt_link_issues.append(
                    {
                        "track_number": num,
                        "title": title,
                        "isrc": isrc,
                        "mbid": rec_ids[0],
                        "reason": reason,
                        "yt_urls": target_links,
                    }
                )
                print(f"   ⚠️ {reason}")

                # --- CATEGORY 2: Ambiguous Recordings (Only if NOT in List 1 AND has issues) ---
                if len(recording_list) > 1:
                    list_2_ambiguous_recordings.append(
                        {
                            "track_number": num,
                            "title": title,
                            "isrc": isrc,
                            "recording_count": len(recording_list),
                            "mbids": rec_ids,
                        }
                    )

        except musicbrainzngs.ResponseError as e:
            list_3_yt_link_issues.append(
                {
                    "track_number": num,
                    "title": title,
                    "isrc": isrc,
                    "reason": "ISRC error on MB",
                    "yt_urls": [],
                }
            )
            print(f"   ❌ MB Response Error: {e}")

    _print_summary(list_1_downloadable, list_2_ambiguous_recordings, list_3_yt_link_issues)

    if download_now and list_1_downloadable:
        download_album_with_ytdlp(album_name, artist_name, list_1_downloadable)


def download_album_with_ytdlp(album: str, artist: str, tracks: list[dict]):
    """Downloads tracks into 'Artist - Album/TrackNum - Title.ext' using yt-dlp."""
    print("\n" + "=" * 70)
    print(" STARTING YT-DLP ALBUM DOWNLOAD ")
    print("=" * 70)

    safe_artist = re.sub(r'[\\/*?:"<>|]', "", artist)
    safe_album = re.sub(r'[\\/*?:"<>|]', "", album)
    output_folder = f"./downloads/{safe_artist} - {safe_album}"

    os.makedirs(output_folder, exist_ok=True)

    for item in tracks:
        url = item["yt_url"]
        num = item["track_number"]
        title = item["title"]

        output_template = f"{output_folder}/{num:02d} - %(title)s.%(ext)s"

        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--parse-metadata", f"title:{title}",
            "--parse-metadata", f"artist:{artist}",
            "--parse-metadata", f"album:{album}",
            "-o", output_template,
            url,
        ]

        print(f"\nDownloading [{num:02d}] {title} ...")
        try:
            subprocess.run(cmd, check=True)
            print("   Done!")
        except Exception as e:
            print(f"   ❌ Download failed for {title}: {e}")


def _print_summary(list_1, list_2, list_3):
    print("\n" + "=" * 70)
    print(" SUMMARY REPORT ")
    print("=" * 70)

    print(f"\n1️⃣ READY FOR YT-DLP DOWNLOAD ({len(list_1)} tracks):")
    print("-" * 50)
    for item in list_1:
        print(f"  [{item['track_number']:02d}] {item['title']} (ISRC: {item['isrc']})")
        print(f"       URL:  {item['yt_url']}")

    print(f"\n2️⃣ UNRESOLVED AMBIGUOUS RECORDINGS ({len(list_2)} tracks):")
    print("-" * 50)
    if not list_2:
        print("  (None — all multi-recording ISRCs resolved cleanly to single YTM links!)")
    for item in list_2:
        print(f"  [{item['track_number']:02d}] {item['title']} (ISRC: {item['isrc']})")
        print(f"       Matches ({item['recording_count']}): {', '.join(item['mbids'])}")

    print(f"\n3️⃣ YT LINK ISSUES ({len(list_3)} tracks):")
    print("-" * 50)
    for item in list_3:
        print(f"  [{item['track_number']:02d}] {item['title']} (ISRC: {item['isrc']})")
        print(f"       Issue: {item['reason']}")
        if item["yt_urls"]:
            print(f"       URLs:  {', '.join(item['yt_urls'])}")


if __name__ == "__main__":
    album_url = "https://open.spotify.com/album/6wEh2L2nX5qVc7fDgCMGNn"
    download_flag = False

    if len(sys.argv) > 1:
        album_url = sys.argv[1]
    if "--download" in sys.argv:
        download_flag = True

    album_data = fetch_isrchunt_tracks(album_url)
    if album_data.get("tracks"):
        process_isrcs_against_musicbrainz(album_data, download_now=download_flag)
    else:
        print("No tracks found on ISRCHunt.")
