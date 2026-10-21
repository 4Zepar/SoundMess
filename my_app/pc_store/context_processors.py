from .permissions import can_manage_users, can_moderate


def navigation(request):
    artist = None
    if request.user.is_authenticated:
        artist = getattr(request.user, 'artist', None)
    return {
        'playlist_options': list(
            request.user.albums.filter(is_public=False, is_favorite_folder=False).values('id', 'title')
        ) if request.user.is_authenticated else [],
        'current_artist': artist,
        'can_moderate': can_moderate(request.user),
        'can_manage_users': can_manage_users(request.user),
    }
