from django.db import connection, transaction
from django.db.models import F

from pc_store.models import Album, AlbumTrack


@transaction.atomic
def set_album_tracks(album, tracks):
    """Keep retained tracks in place and append new ones in the supplied order."""
    if connection.vendor == 'sqlite':
        Album.objects.filter(pk=album.pk).update(title=F('title'))
    Album.objects.select_for_update().get(pk=album.pk)
    track_ids = list(dict.fromkeys(track.pk if hasattr(track, 'pk') else int(track) for track in tracks))
    entries = AlbumTrack.objects.filter(album=album)
    entries.exclude(track_id__in=track_ids).delete()
    existing = dict(entries.values_list('track_id', 'position'))
    position = max(existing.values(), default=0)
    added = []
    for track_id in track_ids:
        if track_id not in existing:
            position += 1
            added.append(AlbumTrack(album=album, track_id=track_id, position=position))
    AlbumTrack.objects.bulk_create(added)


@transaction.atomic
def add_album_track(album, track):
    if connection.vendor == 'sqlite':
        Album.objects.filter(pk=album.pk).update(title=F('title'))
    Album.objects.select_for_update().get(pk=album.pk)
    entries = AlbumTrack.objects.filter(album=album)
    if entries.filter(track=track).exists():
        return False
    last = entries.order_by('-position').values_list('position', flat=True).first() or 0
    entries.create(album=album, track=track, position=last + 1)
    return True
