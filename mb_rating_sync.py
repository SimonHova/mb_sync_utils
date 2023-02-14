from configparser import RawConfigParser
import argparse
import logging

import musicbrainzngs
import sys

import ampache

import mariadb

from bs4 import BeautifulSoup
from requests import get as r_get

from time import sleep

def ampRating_to_mbRating( _rating ):
    return int(_rating) * 20

def mbRating_to_ampRating( _rating ):
    return int(_rating) / 20

def get_release_group_by_release_id( _id ):
    logger.debug("Asking MB for release ID " + _id)
    return musicbrainzngs.get_release_by_id( id = _id, includes=[ 'release-groups' ])['release']['release-group']['id']

def get_releases_by_release_group_id( _id ):
    logger.debug(("Asking MB for release group ID " + _id))
    _release_ids = []
    
    for _release in musicbrainzngs.get_release_group_by_id( id = _id, includes=[ 'releases' ])['release-group']['release-list']:
        _release_ids.append(_release['id'])
    return _release_ids

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
        config['DEFAULT']['app_name'],
        config['DEFAULT']['app_version'],
        config['DEFAULT']['app_maintainer']
    )
    
    musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)
    
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
    args.MB_ID = config['musicbrainz']['username']
if not args.MB_PW:
    args.MB_PW = config['musicbrainz']['password']

if not args.Amp_URL:
    args.Amp_URL = config['ampache']['url']
if not args.Amp_API:
    args.Amp_API = config['ampache']['api']
if not args.Amp_ID:
    args.Amp_ID = config['ampache']['user']

if not args.Kodi_method:
    args.Kodi_method = config['kodi']['method']
if not args.Kodi_host:
    args.Kodi_host = config['kodi']['host']
if not args.Kodi_port:
    args.Kodi_port = int(config['kodi']['port'])
if not args.Kodi_db:
    args.Kodi_db = config['kodi']['database']
if not args.Kodi_user:
    args.Kodi_user = config['kodi']['user']
if not args.Kodi_pass:
    args.Kodi_pass = config['kodi']['password']

if args.verbose:
    logger.setLevel(level=logging.DEBUG)

if args.sync_from == 'MusicBrainz' or args.sync_to == 'MusicBrainz':
    musicbrainzngs = _get_MB()
if args.sync_from == 'Ampache' or args.sync_to == 'Ampache':
    ampacheConnection = _get_amp()
if args.sync_from == 'Kodi' or args.sync_to == 'Kodi':
    kodiConnection = _get_kodiConnection()

rules = [['myrating',4,1]]

# First, we will do the artists
artists_from = {}
artists_to = {}
_artists = {}
_mbid = ""
_rating=""

match args.sync_from:
    case 'Ampache':
        amp_results = ampacheConnection.advanced_search(rules, object_type='artist')
        
        for artist in amp_results:
            if artist.tag == 'artist':
                _mbid   = artist.find('mbid').text
                _rating = artist.find('rating').text
            if _mbid != "":
                artists_from.update( { _mbid : ampRating_to_mbRating( _rating ) } )
                logger.debug("Got " + str(len(amp_artists)) + " artists to sync from")
            
            _mbid=""
            _rating=""
    case 'Kodi':
        # Kodi does not currently support artist ratings. Need to return a blank array.
        artists_from = {}
    case 'MusicBrainz':
        mb_ratings_link = 'https://musicbrainz.org/user/{}/ratings/artist'.format(args.MB_ID)
        next_mb_ratings_link = ''
        while mb_ratings_link:
            r = r_get(mb_ratings_link)
            soup = BeautifulSoup(r.text, 'html.parser')
            for list in soup.find_all('li'):
                for link in list.find_all('a'):
                    if "/artist/" in link.get('href'):
                        _mbid = (link.get('href')[8:])
                    elif link.contents[0] == 'Next':
                        next_mb_ratings_link=link.get('href')
                for span in list.find_all('span'):
                    for subspan in span.find_all('span'):
                        if subspan.get('class')[0] == "current-rating":
                            _rating = subspan.contents[0]
                artists_from.update( { _mbid : _rating } )
                logger.debug("Got " + str(len(amp_artists)) + " artists to sync from")
                
                _mbid=""
                _rating=""
            if mb_ratings_link != next_mb_ratings_link:
                mb_ratings_link = next_mb_ratings_link
            else:
                mb_ratings_link = ''

match args.sync_to:
    case 'Ampache':
        for artist,rating in artists_from.items():
            if artist != "":  # the first result seems to be null!
                amp_artist = ampacheConnection.advanced_search([['mbid',4,artist]], object_type='artist')
                if len(amp_artist) == 0: # no matches!
                    logger.info('Skipping artist MBID {}; no matches!'.format(artist))
                else:
                    try:
                        amp_rating = amp_artist[1].find('rating')
                    except:
                        logger.info('Skipping artist MBID {}; no matches!'.format(artist))
                    else:
                        if amp_rating == None:
                            logger.info('Artist had no rating. Setting rating {} for artist MBID {}'.format(rating,artist))
                            ampacheConnection.rate(object_id=int(amp_artist[1].attrib['id']), rating=int(rating), object_type='artist')
                        else:
                            if rating == amp_rating.text:
                                logger.info('Ratings match for artist MBID {}'.format(artist))
                            else:
                                logger.info('Ampache had rating of {}. Setting rating {} for artist MBID {}'.format(amp_rating.text,rating,artist))
                                amp_rated = ampacheConnection.rate(object_id=int(amp_artist[1].attrib['id']), rating=int(rating), object_type='artist')
                                # todo: check amp_rated for error
    case 'Kodi':
        # Kodi does not currently support artist ratings.
        
    case 'MusicBrainz':
        musicbrainzngs.submit_ratings(artist_ratings=artists_from)

# Then, the release groups
albums_from={}
albums_to={}
_mbid=None
_rating=""

match args.sync_from:
    case 'Ampache':
        amp_results = ampacheConnection.advanced_search(rules, object_type='album')
        
        for album in amp_results:
        if album.tag == 'album':
            _mbid   = album.find('mbid').text
            _rating = album.find('rating').text
            if _mbid != None:
                albums_from.update( { get_release_group_by_release_id( _mbid ) : ampRating_to_mbRating( _rating ) } )
                logger.debug("Got " + str(len(albums_from)) + " albums")

                logger.debug("Starting 1 second sleep after connecting to MB.")
                sleep(1)
                
                _mbid = None
                _rating = ""
    case 'Kodi':
    case 'MusicBrainz':
        mb_ratings_link = 'https://musicbrainz.org/user/{}/ratings/release_group'.format(args.MB_ID)
        next_mb_ratings_link = ''
        while mb_ratings_link:
            r = r_get(mb_ratings_link)
            soup = BeautifulSoup(r.text, 'html.parser')
            for list in soup.find_all('li'):
                for link in list.find_all('a'):
                    if "/release-group/" in link.get('href'):
                        _mbid = (link.get('href')[15:])
                    elif link.contents[0] == 'Next':
                        next_mb_ratings_link=link.get('href')
                for span in list.find_all('span'):
                    for subspan in span.find_all('span'):
                        if subspan.get('class')[0] == "current-rating":
                            _rating = subspan.contents[0]
                mb_albums.update( { _mbid : _rating } )
                logger.info("Got " + str(len(mb_albums)) + " albums")
                _mbid=""
                _rating=""
            if mb_ratings_link != next_mb_ratings_link:
                mb_ratings_link = next_mb_ratings_link
            else:
                mb_ratings_link = ''

match args.sync_to:
    case 'Ampache':
    case 'Kodi':
    case 'MusicBrainz':
        logger.info("Submitting ratings for " + str(len(albums_from)) + " albums")
        musicbrainzngs.submit_ratings(release_group_ratings=albums_from)

if args.sync_from == 'Ampache':
else:

    
    for album,rating in mb_albums.items():
        if album is not None and album != "":  # if the first result is not null!
            for __album in get_releases_by_release_group_id( album ):
                logger.info('Looking up release MBID {}'.format(__album))
                amp_album = ampacheConnection.advanced_search([['mbid',4,__album]], object_type='album')
                if len(amp_album) == 0: # no matches!
                    logger.info('Skipping album; no matches!')
                else:
                    if amp_album.tag == 'album':
                        try:
                            amp_rating = amp_album[1].find('rating')
                        except:
                            logger.info('Skipping album MBID {}; no matches!'.format(__album))
                        else:
                            if amp_rating.text is None:
                                logger.info('album had no rating. Setting rating {} for album MBID {}'.format(rating,__album))
                                amp_rated = ampacheConnection.rate(object_id=int(amp_album[1].attrib['id']), rating=int(rating), object_type='album')
                                # todo: check amp_rated for error
                            else:
                                if rating == amp_rating.text:
                                    logger.info('Ratings match for album MBID {}'.format(__album))
                                else:
                                    logger.info('Ampache had rating of {}. Setting rating {} for album MBID {}'.format(amp_rating.text,rating,__album))
                                    amp_rated = ampacheConnection.rate(object_id=int(amp_album.attrib['id']), rating=int(rating), object_type='album')
                                    # todo: check amp_rated for error

# Last, the songs
_offset = 0
_limit = 5000

mb_songs = {}
_mbid = ""
_rating = ""
_chunk = 0

if args.sync_from == 'Ampache':
    while(True):
        amp_results = ampacheConnection.advanced_search(rules, object_type='song', limit=_limit, offset=_offset * _limit)
        logger.debug('Run {}: {} songs'.format(_offset+1,len(amp_results)))
        if(len(amp_results)>1):
            amp_songs = {}
            for song in amp_results:
                if song.tag == 'song':
                    _mbid   = song.find('mbid').text
                    _rating = song.find('rating').text
                    if _mbid != None:
                        amp_songs.update( { _mbid : ampRating_to_mbRating( _rating ) } )
                        # logger.debug("Got " + str(len(amp_songs)) + " songs")
                        _mbid=None
                        _rating=""
                    else:
                        logger.info('Song ID not found for song {} by {}'.format(song.find('title'),song.find('artist')))
        else:
            break
        logger.debug("Submitting ratings for " + str(len(amp_songs)) + " songs")
    
        _chunk_offset = 1
        for chunk in [ dict(list(amp_songs.items()) [_chunk:_chunk + 1000]) for _chunk in range(0, len(amp_songs), 1000) ]:
            logger.debug("Submitting chunk " + str(_chunk_offset))
            musicbrainzngs.submit_ratings(recording_ratings=chunk)
            
            _chunk_offset+=1
        _offset+=1
else:
    mb_ratings_link = 'https://musicbrainz.org/user/{}/ratings/recording'.format(args.MB_ID)
    next_mb_ratings_link = ''
    while mb_ratings_link:
        r = r_get(mb_ratings_link)
        soup = BeautifulSoup(r.text, 'html.parser')
        for list in soup.find_all('li'):
            for link in list.find_all('a'):
                if "/recording/" in link.get('href'):
                    _mbid = (link.get('href')[11:])
                elif link.contents[0] == 'Next':
                    next_mb_ratings_link=link.get('href')
            for span in list.find_all('span'):
                for subspan in span.find_all('span'):
                    if subspan.get('class')[0] == "current-rating":
                        _rating = subspan.contents[0]
            mb_songs.update( { _mbid : _rating } )
            # logger.debug("Got " + str(len(mb_songs)) + " songs")
            _mbid=""
            _rating=""
        if mb_ratings_link != next_mb_ratings_link:
            mb_ratings_link = next_mb_ratings_link
        else:
            mb_ratings_link = ''

    logger.info("Got " + str(len(mb_songs)) + " songs")
    for song,rating in mb_songs.items():
        if song != "":  # the first result seems to be null!
            amp_songs = ampacheConnection.advanced_search([['mbid',4,song]], object_type='song')
            if len(amp_songs) == 0: # no matches!
                logger.info('Skipping song; no matches!')
            else:
                for amp_song in amp_songs:
                    if amp_song.tag == 'song':
                        try:
                            amp_rating = amp_song.find('rating')
                        except:
                            logger.info('Skipping song MBID {}; no matches!'.format(song))
                        else:
                            if amp_rating == None:
                                logger.info('song had no rating. Setting rating {} for song MBID {}'.format(rating,song))
                                ampacheConnection.rate(object_id=int(amp_song.attrib['id']), rating=int(rating), object_type='song')
                            else:
                                if rating == amp_rating.text:
                                    logger.info('Ratings match for song MBID {}'.format(song))
                                else:
                                    logger.info('Ampache had rating of {}. Setting rating {} for song MBID {}'.format(amp_rating.text,rating,song))
                                    if int(ampacheConnection.rate(object_id=int(amp_song.attrib['id']), rating=int(rating), object_type='song')[0].attrib['code']) != 1:
                                        logger.info('Broke at song MBID {}'.format(song))
                                        break
