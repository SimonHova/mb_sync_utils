from mb_rating_sync import args, config, logger, musicbrainzngs


import musicbrainzngs


def ampRating_to_mbRating( _rating ):
    return int(_rating) * 20


def mbRating_to_ampRating( _rating ):
    return int(_rating) / 20


def mbRating_to_KodiRating( _rating ):
    return int(_rating) / 10


def ampRating_to_KodiRating( _rating ):
    return int(_rating) * 2


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

    # restrict musicbrainzngs output to INFO messages
    logging.getLogger("musicbrainzngs").setLevel(logging.INFO)

    return musicbrainzngs


def _get_amp():
    _ampacheConnection = ampache.API()
    passphrase = _ampacheConnection.encrypt_string(args.Amp_API, args.Amp_ID)
    ampache_session = _ampacheConnection.handshake(args.Amp_URL, passphrase)

    return _ampacheConnection