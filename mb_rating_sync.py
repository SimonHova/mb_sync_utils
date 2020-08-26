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
parser.add_argument('MB_ID', type=str)
parser.add_argument('MB_PW', type=str)

parser.add_argument('Amp_URL', type=str)
parser.add_argument('Amp_API', type=str)
parser.add_argument('Amp_ID', type=str)

args = parser.parse_args()

musicbrainzngs.auth(args.MB_ID, args.MB_PW)
musicbrainzngs.set_useragent(
    "mb-ratings-sync",
    "0.1",
    "simon@hova.net",
)
musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)

# user variables
ampache_url = args.Amp_URL
my_api_key  = args.Amp_API
user        = args.Amp_ID

# processed details
encrypted_key = ampache.encrypt_string(my_api_key, user)
ampache_api   = ampache.handshake(ampache_url, encrypted_key)

rules = [['myrating',4,1]]

# First, we will do the artists
amp_results = ampache.advanced_search(ampache_url, ampache_api, rules, object_type='artist')

amp_artists={}
_mbid=None
_rating=""

for artist in amp_results:
     for child in artist:
             if child.tag=="mbid":
                     _mbid=child.text
             elif child.tag=="rating":
                     _rating=child.text
     if _mbid != None:
        amp_artists.update( { _mbid : ampRating_to_mbRating( _rating ) } )
        print("Got " + str(len(amp_artists)) + " artists")
        
        _mbid=""
        _rating=""

print("Submitting ratings for " + str(len(amp_artists)) + " artists")
musicbrainzngs.submit_ratings(artist_ratings=amp_artists)

# Then, the release groups
amp_results = ampache.advanced_search(ampache_url, ampache_api, rules, object_type='album')

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
amp_results = ampache.advanced_search(ampache_url, ampache_api, rules, object_type='song')

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
