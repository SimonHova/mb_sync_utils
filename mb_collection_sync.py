from configparser import ConfigParser
import argparse
import logging

import musicbrainzngs
import sys

import ampache

# Set the default logging level.
logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser(description='Sync collections between Ampache and MusicBrainz')

parser.add_argument('--config', type=str, help='location of a config file',default=None)

parser.add_argument('--verbose', action="store_true", default=False, help='Print extra information for debugging.')

parser.add_argument('--sync_from',choices=['Ampache','MusicBrainz'], default='Ampache', help='Which data source should we sync from')

parser.add_argument('--MB_ID', type=str, help='The ID used for MusicBrainz')
parser.add_argument('--MB_PW', type=str, help='The PW used for MusicBrainz')
parser.add_argument('--MB_collection', type=str, help='The MBID for your MusicBrainz album collection', default=None)

parser.add_argument('--Amp_URL', type=str, help='The URL used for your local Ampache server')
parser.add_argument('--Amp_API', type=str, help='The API used for your local Ampache server')
parser.add_argument('--Amp_ID', type=str, help='The ID used for your local Ampache server')

args = parser.parse_args()

config = ConfigParser(allow_no_value=True)

if args.config:
    config.read(args.config)

if not args.MB_ID:
    args.MB_ID = config['musicbrainz']['username']
if not args.MB_PW:
    args.MB_PW = config['musicbrainz']['password']
if not args.MB_collection:
    args.MB_collection = config['musicbrainz']['collection']
if not args.Amp_URL:
    args.Amp_URL = config['ampache']['url']
if not args.Amp_API:
    args.Amp_API = config['ampache']['api']
if not args.Amp_ID:
    args.Amp_ID = config['ampache']['user']

if args.verbose:
    logging.basicConfig(level=logging.DEBUG)

musicbrainzngs.auth(args.MB_ID, args.MB_PW)
musicbrainzngs.set_useragent(
    config['DEFAULT']['app_name'],
    config['DEFAULT']['app_version'],
    config['DEFAULT']['app_maintainer']
)
musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)

# connect to the server
ampacheConnection = ampache.API()

# processed details
passphrase = ampacheConnection.encrypt_string(args.Amp_API, args.Amp_ID)
Amp_key = ampacheConnection.handshake(args.Amp_URL, passphrase)

_offset = 0
_limit = 5000

if args.sync_from == 'Ampache':
    while True:
        # Collect the releases from Ampache
        amp_results = ampacheConnection.albums(offset=_offset * _limit)
        
        if len(amp_results) <= 1: break

        amp_albums=[]
        _mbid=None

        for album in amp_results:
            if album.tag == 'album':
                _mbid   = album.find('mbid').text
                if _mbid != None:
                    amp_albums.append( _mbid )
                    logging.info("Got " + str(len(amp_albums)) + " albums")
                    
                    _mbid = None

        # Push them to MusicBrainz
        for chunk in [ amp_albums [i:i + 200] for i in range(0, len(amp_albums), 200) ]:
            musicbrainzngs.add_releases_to_collection(args.MB_collection, releases=chunk)
        _offset += 1
else:
    mb_albums  = []
    amp_albums = []
    
    while True:
        # Collect the releases from MusicBrainz
        mb_results = musicbrainzngs.get_releases_in_collection(collection=args.MB_collection, limit=_limit, offset=_offset * _limit)['collection']['release-list']
        logging.debug("Grabbed " + str(len(mb_results)) + " albums from MB.")
        _limit = len(mb_results)
        
        for mb_album in mb_results:
            if len(ampacheConnection.advanced_search([['mbid_album',4,mb_album['id']]])) == 0:
                logging.debug("Removing release " + str(mb_album['id']) + ".")
                musicbrainzngs.remove_releases_from_collection(collection=args.MB_collection,releases=[mb_album['id']])
        _offset += 1
        logging.debug("Loop number " + str(_offset) + ".")
