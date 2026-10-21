from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from pc_store.forms import TrackFilterForm
from pc_store.models import Album, Artist, Comment, Track
from pc_store.selectors import album_cards, filter_albums, filter_tracks, track_cards


def track_list(request):
    form = TrackFilterForm(request.GET)
    tracks = track_cards(request.user)
    if form.is_valid():
        tracks = filter_tracks(tracks, form.cleaned_data)
        sort = form.cleaned_data.get('sort')
        order = '-plays_count' if sort == 'popular' else '-like_count' if sort == 'liked' else '-created_at'
        tracks = tracks.order_by(order, '-pk')
    else:
        tracks = tracks.none()
    page = Paginator(tracks, 24).get_page(request.GET.get('page'))
    return render(request, 'index.html', {'page_obj': page, 'tracks': page.object_list, 'filter_form': form})


def release_list(request):
    form = TrackFilterForm(request.GET)
    albums = album_cards()
    if form.is_valid():
        albums = filter_albums(albums, form.cleaned_data)
        sort = form.cleaned_data.get('sort')
        if sort == 'liked':
            albums = albums.order_by('-total_likes', '-pk')
        else:
            albums = albums.order_by('-total_plays' if sort == 'popular' else '-published_at', '-pk')
    else:
        albums = albums.none()
    page = Paginator(albums, 24).get_page(request.GET.get('page'))
    return render(
        request,
        'releases.html',
        {'page_obj': page, 'albums': page.object_list, 'filter_form': form}
    )


def artist_list(request):
    query = request.GET.get('q', '')[:200].strip()
    artists = Artist.objects.filter(
        moderation_status='approved',
        user__is_active=True
    ).select_related('user__profile')
    if query:
        artists = artists.filter(user__username__icontains=query)
    page = Paginator(artists.order_by('user__username'), 24).get_page(request.GET.get('page'))
    return render(request, 'artists.html', {'artists': page.object_list, 'page_obj': page, 'search': query})


def artist_detail(request, artist_id):
    artist = get_object_or_404(
        Artist.objects.select_related('user__profile'),
        pk=artist_id,
        moderation_status='approved',
        user__is_active=True
    )
    tracks = track_cards(request.user, Track.objects.published().filter(artist=artist))
    return render(request, 'artist_detail.html', {
        'artist': artist, 'tracks': tracks,
        'albums': album_cards(Album.objects.published().filter(owner=artist.user)),
        'is_following': request.user.is_authenticated and artist.followers.filter(
            follower=request.user
        ).exists(),
    })


def album_detail(request, album_id):
    album = get_object_or_404(Album.objects.visible_to(request.user).select_related('owner'), pk=album_id)
    if album.is_favorite_folder:
        tracks = Track.objects.visible_to(request.user).filter(likes=album.owner)
    else:
        tracks = Track.objects.visible_to(request.user).filter(contained_in=album)
    return render(request, 'album_detail.html', {
        'album': album, 'tracks': track_cards(request.user, tracks),
        'is_saved': request.user.is_authenticated and album.saved_by.filter(pk=request.user.pk).exists(),
    })


def comment_page(request, track_id):
    track = get_object_or_404(track_cards(request.user, Track.objects.visible_to(request.user)), pk=track_id)
    comments = list(Comment.objects.filter(track=track, is_hidden=False).select_related('author__profile'))
    nodes = {comment.pk: {'comment': comment, 'children': []} for comment in comments}
    roots = []
    for comment in comments:
        node = nodes[comment.pk]
        if comment.parent_id is None:
            roots.append(node)
        elif comment.parent_id in nodes:
            nodes[comment.parent_id]['children'].append(node)
    return render(request, 'track_comments.html', {'track': track, 'comment_tree': roots})
