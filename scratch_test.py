import musicbrainzngs

musicbrainzngs.set_useragent("Ampache Ratings Sync", "0.2.0", "simon@hova.net")
musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)

mbid = "b10bb2e9-1d7e-471a-907b-f139f53c352b"

entities = ['artist', 'recording', 'release_group', 'release', 'work', 'area', 'label', 'place', 'event', 'series', 'url', 'instrument']

for entity in entities:
    try:
        fn = getattr(musicbrainzngs, f"get_{entity}_by_id")
        res = fn(mbid)
        print(f"Success with {entity}!")
        print(res)
        break
    except Exception as e:
        print(f"Failed {entity}: {e}")
