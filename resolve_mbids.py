import sys
import time
import musicbrainzngs

# Set up standard MusicBrainz user agent matching other scripts in this project
musicbrainzngs.set_useragent("Ampache Ratings Sync", "0.2.0", "simon@hova.net")

# Restrict rate limit to 1 request per second as requested by MusicBrainz API terms
musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)

def get_mb_info(mbid):
    # MusicBrainz identifies entities via specific endpoints. 
    # We will try the most common ones in order.
    
    # 1. Try Artist
    try:
        res = musicbrainzngs.get_artist_by_id(mbid)
        return "Artist", res['artist'].get('name')
    except musicbrainzngs.ResponseError:
        pass
    except Exception:
        pass

    # 2. Try Recording
    try:
        res = musicbrainzngs.get_recording_by_id(mbid)
        return "Recording", res['recording'].get('title')
    except musicbrainzngs.ResponseError:
        pass
    except Exception:
        pass

    # 3. Try Release Group
    try:
        res = musicbrainzngs.get_release_group_by_id(mbid)
        return "Release-group", res['release-group'].get('title')
    except musicbrainzngs.ResponseError:
        pass
    except Exception:
        pass

    # 4. Try Release
    try:
        res = musicbrainzngs.get_release_by_id(mbid)
        return "Release", res['release'].get('title')
    except musicbrainzngs.ResponseError:
        pass
    except Exception:
        pass

    return "Unknown", "No match found"

if __name__ == "__main__":
    # Get IDs from stdin (piped from your journalctl command)
    mbids = sys.stdin.read().splitlines()
    unique_ids = sorted(list(set(mbids)))

    print(f"{'TYPE':<15} | {'NAME/TITLE':<40} | {'MBID'}")
    print("-" * 80)

    for mbid in unique_ids:
        mbid_clean = mbid.strip()
        if not mbid_clean:
            continue
        etype, name = get_mb_info(mbid_clean)
        print(f"{etype:<15} | {name:<40} | {mbid_clean}")
