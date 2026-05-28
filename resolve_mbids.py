import sys
import requests
import time

# To avoid being rate-limited by MusicBrainz (1 request per second)
def get_mb_info(mbid):
    # MusicBrainz identifies entities via specific endpoints. 
    # We will try the most common ones in order.
    entities = ['artist', 'recording', 'release-group', 'release']
    
    headers = {'User-Agent': 'MyAmpacheFixer/1.0 ( simon@hova.net )'}
    
    for entity in entities:
        url = f"https://musicbrainz.org/ws/2/{entity}/{mbid}?fmt=json"
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # Return the type and the name/title
                return entity.capitalize(), data.get('name') or data.get('title')
            time.sleep(1) # Respect the rate limit
        except Exception:
            continue
    return "Unknown", "No match found"

if __name__ == "__main__":
    # Get IDs from stdin (piped from your journalctl command)
    mbids = sys.stdin.read().splitlines()
    unique_ids = sorted(list(set(mbids)))

    print(f"{'TYPE':<15} | {'NAME/TITLE':<40} | {'MBID'}")
    print("-" * 80)

    for mbid in unique_ids:
        if not mbid.strip(): continue
        etype, name = get_mb_info(mbid.strip())
        print(f"{etype:<15} | {name:<40} | {mbid}")