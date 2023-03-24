#!/bin/bash
mysql -u xbmc -p < get_artists.sql > artists.txt
tail -n +2 "artists.txt" > "artists.tmp" && mv "artists.tmp" "artists.txt"
sed 's|^|http://ampache.video.18claypitts.hova.net:5006/artists.php?action=update_from_musicbrainz\&artist=|' artists.txt > artists.tmp && mv "artists.tmp" "artists.txt"
wget --load-cookies ampache-cookies.txt --debug --input-file artists.txt --output-file wget.log
rm artists.txt
