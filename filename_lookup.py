import musicbrainzngs
import sys

import re

from configparser import RawConfigParser
import argparse
import logging

from collections import defaultdict

def _get_MB():
    musicbrainzngs.auth(args.MB_ID, args.MB_PW)
    
    musicbrainzngs.set_useragent(
        config['DEFAULT']['app_name'],
        config['DEFAULT']['app_version'],
        config['DEFAULT']['app_maintainer']
    )
    
    musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)
    
    return musicbrainzngs

parser = argparse.ArgumentParser(description='Sync ratings between Ampache and MusicBrainz')

parser.add_argument('--config', type=str, help='location of a config file',default=None)

# parser.add_argument('--filename', type=str, help='location of the import file',default=None)
parser.add_argument('--username', type=str, help='name of the person the file is named after',default=None)

parser.add_argument('--verbose', action="store_true", default=False, help='Print extra information for debugging.')

parser.add_argument('--MB_ID', type=str, help='The ID used for MusicBrainz')
parser.add_argument('--MB_PW', type=str, help='The PW used for MusicBrainz')

args = parser.parse_args()
config = RawConfigParser(allow_no_value=True)

config['DEFAULT']['app_name'] = 'mb-info-sync'
config['DEFAULT']['app_version'] = '0.1'
config['DEFAULT']['app_maintainer'] = 'simon@hova.net'

args.MB_ID = 'SimonHova'
args.MB_PW = '2w*CxKzbXBnS'
args.MB_collection = '27076e46-3523-4605-8076-f289c5d923d2'

d1 = defaultdict(list)
_line = []

artists = []

file_in  = "/home/xbmc/ratings_{}.log".format(args.username)
file_out = "/home/xbmc/results_{}.log".format(args.username)

musicbrainzngs = _get_MB()

with open(file_in, 'r', encoding='UTF-8') as file:
    _reg = re.compile("""(?:.*?)Skipping (\w*) MBID (.*?); no matches!""")
    while line := file.readline():
        if _reg.match(line):
            _line.append([_reg.match(line)[1],_reg.match(line)[2]])

for k,v in _line:
    d1[k].append(v)

dictMB = dict((k,tuple(v)) for k, v in d1.items())

with open(file_out, 'w', encoding='UTF-8') as file:
    for song in dictMB.pop("song",""):
        a = musicbrainzngs.get_recording_by_id(song)
        print("https://musicbrainz.org/recording/{}\t{}\n".format(song,a['recording']['title']))
        file.write("https://musicbrainz.org/recording/{}\t{}\n".format(song,a['recording']['title']))

    for album in dictMB.pop("album",""):
        a = musicbrainzngs.get_release_group_by_id(album)
        file.write("https://musicbrainz.org/release-group/{}\t{}\n".format(album,a['release-group']['title']))

    for artist in dictMB.pop("artist",""):
        a = musicbrainzngs.get_artist_by_id(artist)
        file.write("https://musicbrainz.org/artist/{}\t{}\n".format(artist,a['artist']['name']))