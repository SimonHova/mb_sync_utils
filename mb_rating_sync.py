import argparse

import musicbrainzngs
import sys

import ampache

parser = argparse.ArgumentParser(description='Sync ratings from Ampache to MusicBrainz')
parser.add_argument('MB_ID', type=str)
parser.add_argument('MB_PW', type=str)

parser.add_argument('Amp_URL', type=str)
parser.add_argument('Amp_API', type=str)
parser.add_argument('Amp_ID', type=str)

args = parser.parse_args()

class interface:
    def __init__(self, args):
        pass
    
    def ampRating_to_mbRating( self, _rating ):
        return int(_rating) * 20
    
    def mbRating_to_ampRating( self, _rating ):
        return int(_rating) / 20
    
    def results(self, type):
        pass
    
    def submit_ratings(self, type, items):
        pass

class music_item:
    def __init__(self, interface, type):
        self._interface=interface
        self._type=type
        
        self._mbid=None
        self._rating=""
        
    @property
    def type(self):
        return self._type
    
    @property
    def mbid(self):
        return self._mbid
    
    @mbid.setter
    def mbid(self, value):
        self._mbid=value
    
    @property
    def rating(self):
        return self._rating
    
    @rating.setter
    def rating(self, value):
        self._rating=value

class int_amp(interface):
    def __init__(self, args):
        self._url = args.Amp_URL
        self._api = args.Amp_API
        self._id = args.Amp_ID
        
        self._encrypted_key = ampache.encrypt_string(self._api, self._id)
        self._ampache_api   = ampache.handshake(self._url, self._encrypted_key)
        
    def get_id_from_mbid(self, item):
        _amp_results = ampache.advanced_search(self._url, self._ampache_api, [['myrating',4,1]], object_type=type)
    
    def results(self, type):
        _amp_results = ampache.advanced_search(self._url, self._ampache_api, [['myrating',4,1]], object_type=type)
        
        __results = []
        i = music_item(self,type)
        
        for _item in _amp_results:
            for child in _item:
                if child.tag=="mbid":
                    if child.text != None:
                        if type=="album":
                            i.mbid=self.get_release_group_by_release_id(child.text)
                        else:
                            i.mbid=child.text
                elif child.tag=="rating":
                    i.rating=child.text
            
            if i._mbid != None:
                __results.append(i)
            
            i = music_item(self,type)
        
        print("Got " + str(len(__results)) + " " + type + "s from Ampache")
        return __results
    
    def submit_ratings(self,type,items):
        pass

class int_mb(interface):
    def __init__(self, args):
        self._id = args.MB_ID
        self._pw = args.MB_PW
        
        musicbrainzngs.auth(args.MB_ID, args.MB_PW)
        musicbrainzngs.set_useragent(
            "mb-ratings-sync",
            "0.1",
            "simon@hova.net",
        )
        musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)
    
    def _format_list(self,items):
        # take a list
        # return a dict
        
        _items={}
        for item in items:
            _items.update( { item.mbid : self.ampRating_to_mbRating( item.rating ) } )
        return _items
    
    def get_release_group_by_release_id( self, _id ):
        print ("Asking MB for release ID " + _id)
        return musicbrainzngs.get_release_by_id( id = _id, includes=[ 'release-groups' ])['release']['release-group']['id']
    
    def results(self, type, item):
        if type == "artist":
            print("Getting ratings for artist " + str( item.mbid ) + " from MusicBrainz")
            musicbrainzngs.get_artist_by_id(id=item.mbid,includes=['user-ratings'])
        elif type == "album":
            print("Getting ratings for album " + str( item.mbid ) + " from MusicBrainz")
            musicbrainzngs.get_release_group_by_id(id=item.mbid,includes=['user-ratings'])
        elif type == "song":
            print("Getting ratings for song " + str( item.mbid ) + " from MusicBrainz")
            musicbrainzngs.get_recording_group_by_id(id=item.mbid,includes=['user-ratings'])
        
        for child in _item:
            if child.tag=="rating":
                item.rating=child.text
        
        return item
    
    def submit_ratings(self,type,items):
        if type == "artist":
            print("Submitting ratings for " + str(len(items)) + " artists to MusicBrainz")
            musicbrainzngs.submit_ratings(artist_ratings=self._format_list(items))
        elif type == "album":
            print("Submitting ratings for " + str(len(items)) + " albums to MusicBrainz")
            musicbrainzngs.submit_ratings(release_group_ratings=self._format_list(items))
        elif type == "song":
            print("Submitting ratings for " + str(len(items)) + " songs to MusicBrainz")
            musicbrainzngs.submit_ratings(recording_ratings=self._format_list(items))

amp = int_amp(args)
mb = int_mb(args)

# First, we will do the artists
mb.submit_ratings("artist",amp.results("artist"))

# Then, the release groups
mb.submit_ratings("album",amp.results("album"))

# Last, the songs
mb.submit_ratings("song",amp.results("song"))


