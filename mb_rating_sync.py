from configparser import RawConfigParser
import argparse
import logging
import time

import musicbrainzngs

import ampache

import mariadb

from bs4 import BeautifulSoup
from requests import get as r_get, exceptions as r_exceptions

def ampRating_to_mbRating( _rating ):
    return int(_rating) * 20

def mbRating_to_ampRating( _rating ):
    return int(_rating) / 20

def mbRating_to_KodiRating( _rating ):
    return int(_rating) / 10

def ampRating_to_KodiRating( _rating ):
    return int(_rating) * 2

def get_releases_from_rg(rg_mbid):
    """
    Finds Ampache album IDs associated with a Release Group MBID.
    Tries Ampache metadata first, falls back to MB API if necessary.
    """
    # 1. Ask Ampache first (Instant)
    # Most modern Ampache installs store the Release Group MBID
    # logger.debug(f"Searching Ampache for Release Group MBID: {rg_mbid}")
    # try:
        # Check if your Ampache API library supports filtering by mbid_group
        # amp_albums = ampacheConnection.get_albums(filter={'mbid_group': rg_mbid})
        # if amp_albums:
            # return [album.id for album in amp_albums]
    # except Exception as e:
        # logger.debug(f"Ampache RG search failed or unsupported: {e}")

    # 2. Fallback: Ask MusicBrainz (1s Delay)
    # If Ampache doesn't have the RG ID indexed, we find the specific 
    # Release IDs from MB and search Ampache for those instead.
    logger.debug(f"Falling back to MB API for RG: {rg_mbid}")
    try:
        # As discussed, include 'releases' to get the mapping in one trip
        result = get_releases_by_release_group_id( album )
        mb_release_ids = [rel['id'] for rel in result['release-group'].get('release-list', [])]
        
        found_amp_ids = []
        for rel_id in mb_release_ids:
			# Search Ampache for the specific Release MBID
			__album = ampacheConnection.advanced_search([['mbid',4,__album]], object_type='album')
			if __album:
				found_amp_ids.extend([a.id for a in a_album])
			
			return list(set(found_amp_ids)) # De-duplicate
        
    except Exception as e:
        logger.error(f"Failed to resolve RG {rg_mbid} via MusicBrainz: {e}")
        return []

def get_release_group_by_release_id( _id ):
    logger.debug("Asking MB for release ID " + _id)
    
    try:
        return musicbrainzngs.get_release_by_id( id = _id, includes=[ 'release-groups' ])['release']['release-group']['id']
    except:
        logger.debug('Release MBID {} is invalid!'.format(_id))
        return ""

def get_releases_by_release_group_id( _id ):
    logger.debug(("Asking MB for release group ID " + _id))
    _release_ids = []
    
    try:
        for _release in musicbrainzngs.get_release_group_by_id( id = _id, includes=[ 'releases' ])['release-group']['release-list']:
            _release_ids.append(_release['id'])
    except:
        logger.warning('Release group MBID {} is invalid!'.format(_id))
        _release_ids = []
    
    return _release_ids

def get_mb_ratings(entity_type, username):
    results = {}
    url_entity = entity_type.replace('-', '_')
    url = f'https://musicbrainz.org/user/{username}/ratings/{url_entity}'
    
    while url:
        logger.info(f"Scraping from: {url}")
        try:
            # Added a more specific User-Agent
            headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            r = r_get(url, headers=headers, timeout=10)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"Request failed: {e}")
            break

        # Try 'lxml' if you have it, otherwise stick to 'html.parser'
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # DEBUG: Let's see if we're getting a "No ratings found" message
        if "has not rated any" in r.text:
            logger.warning(f"MusicBrainz reports no public ratings for {username} on this page.")
            break

        # Look for all links on the page
        all_links = soup.find_all('a', href=True)
        logger.debug(f"Scanning {len(all_links)} links for UUIDs...")

        for a in all_links:
            # RESET HERE: Ensure we start fresh for every link
            mbid = "" 
            
            href = a['href']
            parts = href.strip('/').split('/')
            potential_mbid = parts[-1]
            
            if len(potential_mbid) == 36 and potential_mbid.count('-') == 4:
                # We found a UUID. Now, let's make sure it's the right TYPE.
                # If we are looking for 'recording', don't grab the 'artist' link.
                if f"/{entity_type}/" not in href:
                    continue
                
                mbid = potential_mbid
                
                # Now look for the rating relative to THIS specific link
                parent = a.find_parent(['td', 'tr', 'li'])
                if parent:
                    rating_span = parent.select_one('span.current-rating')
                    if rating_span:
                        rating_val = rating_span.get_text(strip=True)
                        if rating_val and mbid not in results:
                            results[mbid] = rating_val
                            logger.debug(f"Captured {entity_type}: {mbid} -> {rating_val}")
							
        # Pagination
        next_link = soup.find('a', string=lambda t: t and 'Next' in t)
        if next_link and next_link.get('href'):
            next_path = next_link['href']
            url = f"https://musicbrainz.org{next_path}" if next_path.startswith('/') else next_path
            # Check for same-page loop
            if url == r.url: url = None
        else:
            url = None

        time.sleep(2)

    return results

def _get_kodiConnection():
    _kodiConnection = mariadb.connect(
            user=args.Kodi_user,
            password=args.Kodi_pass,
            host=args.Kodi_host,
            port=args.Kodi_port,
            database=args.Kodi_db )
    
    return _kodiConnection

def _get_MB():
    musicbrainzngs.auth(args.MB_ID, args.MB_PW)
    
    musicbrainzngs.set_useragent(
        config['DEFAULT']['App Name'],
        config['DEFAULT']['App Version'],
        config['DEFAULT']['App Maintainer']
    )
    
    musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)
    
    # restrict musicbrainzngs output to INFO messages
    logging.getLogger("musicbrainzngs").setLevel(logging.INFO)
    
    return musicbrainzngs

def _get_amp():
    _ampacheConnection = ampache.API()
    passphrase = _ampacheConnection.encrypt_string(args.Amp_API, args.Amp_ID)
    ampache_session = _ampacheConnection.handshake(args.Amp_URL, passphrase)
    
    return _ampacheConnection

# create logger
logger = logging.getLogger('mb_ratings_sync')

# Set the default logging level.
logger.setLevel(logging.INFO)

# create console handler
ch = logging.StreamHandler()

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)

parser = argparse.ArgumentParser(description='Sync ratings between Ampache and MusicBrainz')

parser.add_argument('--config', type=str, help='location of a config file',default=None)

parser.add_argument('--verbose', action="store_true", default=False, help='Print extra information for debugging.')

parser.add_argument('--sync_from',choices=['Ampache','MusicBrainz','Kodi'], default='Ampache', help='Which data source should we sync from')
parser.add_argument('--sync_to',choices=['Ampache','MusicBrainz','Kodi'], default='MusicBrainz', help='Which data source should we sync to')

parser.add_argument('--MB_ID', type=str, help='The ID used for MusicBrainz')
parser.add_argument('--MB_PW', type=str, help='The PW used for MusicBrainz')

parser.add_argument('--Amp_URL', type=str, help='The URL used for your local Ampache server')
parser.add_argument('--Amp_API', type=str, help='The API used for your local Ampache server')
parser.add_argument('--Amp_ID', type=str, help='The ID used for your local Ampache server')

parser.add_argument('--Kodi_method', choices=['mysql'], default='mysql', help='How to connect to Kodi')
parser.add_argument('--Kodi_host', type=str, help='The address for your Kodi DB')
parser.add_argument('--Kodi_port', type=int, help='Port number for your Kodi DB')
parser.add_argument('--Kodi_db', type=str, help='Kodi DB name')
parser.add_argument('--Kodi_user', type=str, help='Kodi DB username')
parser.add_argument('--Kodi_pass', type=str, help='Kodi DB password')

args = parser.parse_args()

config = RawConfigParser(allow_no_value=True)

if args.config:
    config.read(args.config)

if not args.MB_ID:
    args.MB_ID = config['MusicBrainz']['username']
if not args.MB_PW:
    args.MB_PW = config['MusicBrainz']['password']

if not args.Amp_URL:
    args.Amp_URL = config['Ampache']['URL']
if not args.Amp_API:
    args.Amp_API = config['Ampache']['API']
if not args.Amp_ID:
    args.Amp_ID = config['Ampache']['user']

if not args.Kodi_method:
    args.Kodi_method = config['Kodi']['Method']
if not args.Kodi_host:
    args.Kodi_host = config['Kodi']['host']
if not args.Kodi_port:
    args.Kodi_port = int(config['Kodi']['port'])
if not args.Kodi_db:
    args.Kodi_db = config['Kodi']['database']
if not args.Kodi_user:
    args.Kodi_user = config['Kodi']['user']
if not args.Kodi_pass:
    args.Kodi_pass = config['Kodi']['pass']

if args.verbose:
    logger.setLevel(level=logging.DEBUG)

if args.sync_from == 'MusicBrainz' or args.sync_to == 'MusicBrainz':
    musicbrainzngs = _get_MB()

if args.sync_from == 'Ampache' or args.sync_to == 'Ampache':
    ampacheConnection = _get_amp()

if args.sync_from == 'Kodi' or args.sync_to == 'Kodi':
    kodiConnection = _get_kodiConnection()
    kodiCursor = kodiConnection.cursor()
    kodiCursor.autocommit = False

rules = [['myrating',4,1]]

# First, we will do the artists
artists_from = {}
artists_to = {}
_artists = {}
_mbid = ""
_rating=""

if args.sync_from == 'Ampache':
    amp_results = ampacheConnection.advanced_search(rules, object_type='artist')

    if amp_results is None:
        logger.error("Failed to get artists from Ampache. 'advanced_search' returned None.")
        amp_results = []
    
    for artist in amp_results:
        if artist.tag == 'artist':
            _mbid   = artist.find('mbid').text
            _rating = artist.find('rating').text
            if _mbid and _rating:
                artists_from.update( { _mbid : ampRating_to_mbRating( _rating ) } )
                logger.debug("Got " + str(len(artists_from)) + " artists to sync from")
        
        _mbid=""
        _rating=""
elif args.sync_from == 'Kodi':
    # Kodi does not currently support artist ratings. Need to return a blank array.
    artists_from = {}
elif args.sync_from == 'MusicBrainz':
    artists_from = get_mb_ratings('artist', args.MB_ID)

if args.sync_to == 'Ampache':
    for artist,rating in artists_from.items():
        if artist != "":  # the first result seems to be null!
            amp_artist = ampacheConnection.advanced_search([['mbid',4,artist]], object_type='artist')
            if len(amp_artist) == 0: # no matches!
                logger.warning('Skipping artist MBID {}; no matches!'.format(artist))
            else:
                try:
                    amp_rating = amp_artist[2].find('rating')
                except:
                    logger.warning('Skipping artist MBID {}; no matches!'.format(artist))
                else:
                    if amp_rating == None:
                        logger.debug('Artist had no rating. Setting rating {} for artist MBID {}'.format(rating,artist))
                        ampacheConnection.rate(object_id=int(amp_artist[2].attrib['id']), rating=int(rating), object_type='artist')
                    else:
                        if rating == amp_rating.text:
                            logger.debug('Ratings match for artist MBID {}'.format(artist))
                        else:
                            logger.debug('Ampache had rating of {}. Setting rating {} for artist MBID {}'.format(amp_rating.text,rating,artist))
                            amp_rated = ampacheConnection.rate(object_id=int(amp_artist[2].attrib['id']), rating=int(rating), object_type='artist')
                            # todo: check amp_rated for error
elif args.sync_to == 'Kodi':
    # Kodi does not currently support artist ratings.
    pass
elif args.sync_to == 'MusicBrainz':
    musicbrainzngs.submit_ratings(artist_ratings=artists_from)

# Then, the release groups
albums_from={}
albums_to={}
_mbid=None
_rating=""

if args.sync_from == 'Ampache':
    amp_results = ampacheConnection.advanced_search(rules, object_type='album')

    if amp_results is None:
        logger.error("Failed to get albums from Ampache. 'advanced_search' returned None.")
        amp_results = []

    for album in amp_results[:100]:
        if album.tag == 'album':
            _mbid   = album.find('mbid').text
            _rating = album.find('rating').text
            if _mbid != None:
                albums_from.update( { get_release_group_by_release_id( _mbid ) : ampRating_to_mbRating( _rating ) } )
                logger.debug("Got " + str(len(albums_from)) + " albums")
                
                _mbid = None
                _rating = ""
elif args.sync_from == 'Kodi':
    pass
elif args.sync_from == 'MusicBrainz':
    albums_from = get_mb_ratings('release-group', args.MB_ID)

if args.sync_to == 'Ampache':
	for rg_mbid, rating in albums_from.items():
	    amp_album_ids = get_releases_from_rg(rg_mbid)
	    
	    if not amp_album_ids:
	        # Add to that skipped_report we talked about!
	        # skipped_report['release-group'].append(f"https://musicbrainz.org/release-group/{rg_mbid}")
	        continue
	        
	    for a_id in amp_album_ids:
	        # Apply the rating to the Ampache Album ID
	        sync_rating_to_ampache('album', a_id, rating)
elif args.sync_to == 'Kodi':
    for album,rating in albums_from.items():
        if album is not None and album != "":  # skip null results
            logger.debug('Setting rating {} for album MBID {}'.format( ampRating_to_KodiRating( rating ),album))
            kodiCursor.execute("""UPDATE album SET iUserrating = (%s) WHERE strReleaseGroupMBID = %s;""",( ampRating_to_KodiRating( rating ),album))
    kodiConnection.commit()
elif args.sync_to == 'MusicBrainz':
    try:
        logger.debug("Submitting ratings for " + str(len(albums_from)) + " albums")
        musicbrainzngs.submit_ratings(release_group_ratings=albums_from)
    except Exception as e:
        logger.error(f"Error submitting album ratings to MusicBrainz: {e}")
    else:
        logger.debug("Ratings submitted successfully")

# Last, the songs
_offset = 0
_limit = 5000

songs_from = {}
_mbid = ""
_rating = ""
_chunk = 0

if args.sync_from == 'Ampache':
    def get_ampache_songs_recursively(rules, object_type, limit, offset):
        """
        Recursively fetches songs from Ampache, splitting the request if it fails,
        to isolate problematic records.
        """
        amp_results = ampacheConnection.advanced_search(rules, object_type=object_type, limit=limit, offset=offset)
        
        if amp_results is False:
            if limit > 1:
                logger.debug(f"Advanced search failed for offset {offset} with limit {limit}. Splitting.")
                mid_point = limit // 2
                
                results1 = get_ampache_songs_recursively(rules, object_type, mid_point, offset)
                results2 = get_ampache_songs_recursively(rules, object_type, limit - mid_point, offset + mid_point)

                all_results = []
                if results1:
                    all_results.extend(results1)
                if results2:
                    all_results.extend(results2)
                return all_results
            else:
                logger.error(f"Failed to get song at offset {offset}. This record may be corrupt in Ampache.")
                return [] # Return empty list for the failed record
        
        return amp_results if amp_results is not None else []

    all_amp_results = []
    while(True):
        logger.debug(f"Fetching songs with limit {_limit} and offset {_offset * _limit}")
        amp_results = ampacheConnection.advanced_search(rules, object_type='song', limit=_limit, offset=_offset * _limit)
        
        if amp_results is False:
            logger.warning(f"Batch fetch failed for offset {_offset * _limit} with limit {_limit}. Splitting to find bad records.")
            amp_results = get_ampache_songs_recursively(rules, 'song', _limit, _offset * _limit)

        if amp_results is None:
            # This can mean an error or just no results. The recursive function handles 'False' for error.
            # 'None' from the API usually means no more items.
            logger.debug("advanced_search returned None, assuming end of songs.")
            break
        
        logger.debug('Page {}: got {} songs'.format(_offset+1,len(amp_results)))
        if len(amp_results) > 0:
            all_amp_results.extend(amp_results)
        
        if len(amp_results) < _limit:
            # Last page
            logger.debug("Got fewer songs than limit, assuming end of list.")
            break

        _offset += 1

    logger.info(f"Total songs fetched from Ampache: {len(all_amp_results)}")
    songs_from = {}
    for song in all_amp_results:
        if song.tag == 'song':
            _mbid   = song.find('mbid').text
            _rating = song.find('rating').text
            if _mbid:
                songs_from.update( { _mbid : ampRating_to_mbRating( _rating ) } )
            else:
                title_elem = song.find('title')
                artist_elem = song.find('artist')
                title = title_elem.text if title_elem is not None else "Unknown Title"
                artist = artist_elem.text if artist_elem is not None else "Unknown Artist"
                logger.warning(f'Song ID not found for song {title} by {artist}')
elif args.sync_from == 'MusicBrainz':
    songs_from = get_mb_ratings('recording', args.MB_ID)

if args.sync_to == 'Ampache':
    for song,rating in songs_from.items():
        if song != "":  # the first result seems to be null!
            songs_to = ampacheConnection.advanced_search([['mbid',4,song]], object_type='song')
            if len(songs_to) == 0: # no matches!
                logger.warning('Skipping song MBID {}; no matches!'.format(song))
            else:
                for song_to in songs_to:
                    if song_to.tag == 'song':
                        try:
                            amp_rating = song_to.find('rating')
                        except:
                            logger.warning('Skipping song MBID {}; no matches!'.format(song))
                        else:
                            if amp_rating == None:
                                logger.debug('song had no rating. Setting rating {} for song MBID {}'.format(rating,song))
                                ampacheConnection.rate(object_id=int(song_to.attrib['id']), rating=int(rating), object_type='song')
                            else:
                                if rating == amp_rating.text:
                                    logger.debug('Ratings match for song MBID {}'.format(song))
                                else:
                                    logger.debug('Ampache had rating of {}. Setting rating {} for song MBID {}'.format(amp_rating.text,rating,song))
                                    if int(ampacheConnection.rate(object_id=int(song_to.attrib['id']), rating=int(rating), object_type='song')[0].attrib['code']) != 1:
                                        logger.error('Broke at song MBID {}'.format(song))
                                        break
elif args.sync_to == 'MusicBrainz':
    try:
        logger.debug("Submitting ratings for " + str(len(songs_from)) + " songs")
        
        _chunk_offset = 1
        for chunk in [ dict(list(songs_from.items()) [_chunk:_chunk + 1000]) for _chunk in range(0, len(songs_from), 1000) ]:
            logger.debug("Submitting chunk " + str(_chunk_offset))
            musicbrainzngs.submit_ratings(recording_ratings=chunk)
            
            _chunk_offset+=1
        _offset+=1
    except Exception as e:
        logger.error(f"Error submitting album ratings to MusicBrainz: {e}")
elif args.sync_to == 'Kodi':
    for song,rating in songs_from.items():
        if song is not None and song != "":  # skip null results
            logger.debug('Setting rating {} for song MBID {}'.format( ampRating_to_KodiRating( rating ),song))
            kodiCursor.execute("""UPDATE album SET iUserrating = (%s) WHERE strReleaseGroupMBID = %s;""",( ampRating_to_KodiRating( rating ),song))
    kodiConnection.commit()

# for song,rating in songs_from.items():
#     print("Submitting ratings for MBID:" + song)

#     musicbrainzngs.submit_ratings( recording_ratings={ song:rating } )

