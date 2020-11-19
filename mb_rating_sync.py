import configparser
import argparse

import musicbrainzngs
import sys

import ampache

def ampRating_to_mbRating( _rating ):
    return int(_rating) * 20
    
def mbRating_to_ampRating( _rating ):
    return int(_rating) / 20

def get_release_group_by_release_id( _id ):
    print ("Asking MB for release ID " + _id)
    return musicbrainzngs.get_release_by_id( id = _id, includes=[ 'release-groups' ])['release']['release-group']['id']

parser = argparse.ArgumentParser(description='Sync ratings from Ampache to MusicBrainz')

parser.add_argument('--config', type=str, help='location of a config file')

parser.add_argument('--MB_ID', type=str, help='The ID used for MusicBrainz')
parser.add_argument('--MB_PW', type=str, help='The PW used for MusicBrainz')

parser.add_argument('--Amp_URL', type=str, help='The URL used for your local Ampache server')
parser.add_argument('--Amp_API', type=str, help='The API used for your local Ampache server')
parser.add_argument('--Amp_ID', type=str, help='The ID used for your local Ampache server')

args = parser.parse_args()

config = configparser.ConfigParser(allow_no_value=True)

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

musicbrainzngs.auth(args.MB_ID, args.MB_PW)
musicbrainzngs.set_useragent(
    config['DEFAULT']['app_name'],
    config['DEFAULT']['app_version'],
    config['DEFAULT']['app_maintainer']
)
musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)

# processed details
encrypted_key = ampache.encrypt_string(args.Amp_API, args.Amp_ID)
Amp_key       = ampache.handshake(args.Amp_URL, encrypted_key)

rules = [['myrating',4,1]]

# First, we will do the artists
amp_results = ampache.advanced_search(args.Amp_URL, Amp_key, rules, object_type='artist')

amp_artists={}
_mbid=""
_rating=""

for artist in amp_results:
     for child in artist:
             if child.tag=="mbid":
                     _mbid=child.text
             elif child.tag=="rating":
                     _rating=child.text
     if _mbid != "":
        amp_artists.update( { _mbid : ampRating_to_mbRating( _rating ) } )
        print("Got " + str(len(amp_artists)) + " artists")
        
        _mbid=""
        _rating=""

print("Submitting ratings for " + str(len(amp_artists)) + " artists")
musicbrainzngs.submit_ratings(artist_ratings=amp_artists)

# Then, the release groups
amp_results = ampache.advanced_search(args.Amp_URL, Amp_key, rules, object_type='album')

amp_albums={}
_mbid=None
_rating=""

for album in amp_results:
     for child in album:
             if child.tag=="mbid":
                     _mbid=child.text
             elif child.tag=="rating":
                     _rating=child.text
     if _mbid != None:
        amp_albums.update( { get_release_group_by_release_id( _mbid ) : ampRating_to_mbRating( _rating ) } )
        print("Got " + str(len(amp_albums)) + " albums")
        
        _mbid = None
        _rating = ""

print("Submitting ratings for " + str(len(amp_albums)) + " albums")
musicbrainzngs.submit_ratings(release_group_ratings=amp_albums)

# Last, the songs
amp_results = ampache.advanced_search(args.Amp_URL, Amp_key, rules, object_type='song')

amp_songs={}
_mbid=None
_rating=""

for song in amp_results:
     for child in song:
             if child.tag=="mbid":
                     _mbid=child.text
             elif child.tag=="rating":
                     _rating=child.text
     if _mbid!=None:
        amp_songs.update( { _mbid : ampRating_to_mbRating( _rating ) } )
        
        print("Got " + str(len(amp_songs)) + " songs")
        
        _mbid=None
        _rating=""

print("Submitting ratings for " + str(len(amp_songs)) + " songs")
musicbrainzngs.submit_ratings(recording_ratings=amp_songs)
