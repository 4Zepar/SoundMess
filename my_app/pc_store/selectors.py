from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from .models import Album, Track


def track_cards(user, queryset=None):
    tracks = queryset if queryset is not None else Track.objects.published()
    tracks = tracks.select_related('artist__user', 'artist__user__profile').annotate(
        like_count=Count('likes', distinct=True)
    )
    if user.is_authenticated:
        tracks = tracks.annotate(
            is_liked=Exists(
                Track.likes.through.objects.filter(track_id=OuterRef('pk'), user_id=user.pk)
            )
        )
    return tracks


def album_cards(queryset=None):
    albums = queryset if queryset is not None else Album.objects.published()
    return albums.select_related('owner').annotate(track_count=Count('tracks', distinct=True))


def filter_tracks(tracks, data, *, search=True):
    if search and data.get('search'):
        text = data['search']
        tracks = tracks.filter(
            Q(title__icontains=text) | Q(artist__user__username__icontains=text) | Q(
                contained_in__is_public=True,
                contained_in__moderation_status='approved',
                contained_in__title__icontains=text
            )
        )
    for field in ('genre', 'mood', 'tempo', 'release_type'):
        if data.get(field):
            tracks = tracks.filter(**{field: data[field]})
    if data.get('release_year_from'):
        tracks = tracks.filter(release_year__gte=data['release_year_from'])
    if data.get('release_year_to'):
        tracks = tracks.filter(release_year__lte=data['release_year_to'])
    duration = data.get('duration')
    if duration == 'short':
        tracks = tracks.filter(duration_seconds__lt=180)
    elif duration == 'standard':
        tracks = tracks.filter(duration_seconds__gte=180, duration_seconds__lte=300)
    elif duration == 'long':
        tracks = tracks.filter(duration_seconds__gt=300)
    if data.get('has_lyrics'):
        tracks = tracks.exclude(lyrics='')
    if data.get('explicit'):
        tracks = tracks.filter(is_explicit=True)
    return tracks.distinct()


def filter_albums(albums, data):
    if data.get('search'):
        text = data['search']
        albums = albums.filter(Q(title__icontains=text) | Q(owner__username__icontains=text))
    if data.get('release_type'):
        albums = albums.filter(release_type=data['release_type'])
    if data.get('release_year_from'):
        albums = albums.filter(release_year__gte=data['release_year_from'])
    if data.get('release_year_to'):
        albums = albums.filter(release_year__lte=data['release_year_to'])
    track_filters = {
        key: value for key, value in data.items()
        if key in {'genre', 'mood', 'tempo', 'has_lyrics', 'explicit'}
    }
    if any(track_filters.values()):
        matching = filter_tracks(Track.objects.published(), track_filters)
        albums = albums.filter(tracks__in=matching)
    contents = Track.objects.filter(contained_in=OuterRef('pk')).order_by().values('contained_in')
    albums = albums.distinct().annotate(
        total_duration=Coalesce(
            Subquery(contents.annotate(total=Sum('duration_seconds')).values('total')),
            Value(0),
            output_field=IntegerField()
        ),
        total_plays=Coalesce(
            Subquery(contents.annotate(total=Sum('plays_count')).values('total')),
            Value(0),
            output_field=IntegerField()
        ),
        total_likes=Coalesce(
            Subquery(contents.annotate(total=Count('likes')).values('total')),
            Value(0),
            output_field=IntegerField()
        ),
    )
    if data.get('duration') == 'short':
        albums = albums.filter(total_duration__gt=0, total_duration__lt=180)
    elif data.get('duration') == 'standard':
        albums = albums.filter(total_duration__gte=180, total_duration__lte=300)
    elif data.get('duration') == 'long':
        albums = albums.filter(total_duration__gt=300)
    return albums
