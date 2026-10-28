from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from pc_store.http import api_endpoint, integer, json_body
from pc_store.models import Album, Artist, Comment, Follow, ListeningHistory, Track
from pc_store.selectors import album_cards, track_cards
from pc_store.templatetags.music import image_url


def desired_state(data, key, current):
    state = data.get(key, not current)
    if not isinstance(state, bool):
        raise ValidationError('Состояние должно быть true или false.')
    return state


@api_endpoint()
def toggle_like(request, track_id):
    data = json_body(request)
    track = get_object_or_404(Track.objects.published(), pk=track_id)
    with transaction.atomic():
        liked = desired_state(data, 'liked', track.likes.filter(pk=request.user.pk).exists())
        if liked:
            track.likes.add(request.user)
        else:
            track.likes.remove(request.user)
    return JsonResponse({'liked': liked, 'like_count': track.likes.count()})


@api_endpoint()
def toggle_follow(request, artist_id):
    data = json_body(request)
    artist = get_object_or_404(Artist, pk=artist_id, moderation_status='approved', user__is_active=True)
    if artist.user_id == request.user.pk:
        raise ValidationError('Нельзя подписаться на самого себя.')
    following = desired_state(
        data,
        'following',
        Follow.objects.filter(follower=request.user, artist=artist).exists()
    )
    if following:
        Follow(follower=request.user, artist=artist).clean()
        Follow.objects.get_or_create(follower=request.user, artist=artist)
    else:
        Follow.objects.filter(follower=request.user, artist=artist).delete()
    return JsonResponse({'following': following, 'followers_count': artist.followers.count()})


@login_required
def feed_view(request):
    followed = request.user.artist_follows.values_list('artist_id', flat=True)
    followed_artists = Artist.objects.filter(
        pk__in=followed, moderation_status='approved', user__is_active=True,
    ).select_related('user__profile').order_by('user__username', 'pk')
    albums = album_cards(Album.objects.published().filter(owner__artist__in=followed))
    tracks = track_cards(
        request.user,
        Track.objects.published().filter(
            artist__in=followed,
            release_type='single'
        ).exclude(contained_in__in=Album.objects.published())
    )
    entries = [
        {
            'item': item,
            'kind': 'album',
            'date': item.published_at or item.created_at
        } for item in albums
    ]
    entries.extend(
        {
            'item': item,
            'kind': 'track',
            'date': item.published_at or item.created_at
        } for item in tracks
    )
    entries.sort(key=lambda entry: (entry['date'], entry['item'].pk), reverse=True)
    page = Paginator(entries, 20).get_page(request.GET.get('page'))
    return render(request, 'feed.html', {
        'entries': page.object_list, 'page_obj': page, 'followed_artists': followed_artists,
    })


@api_endpoint(methods=('GET', 'POST'), authenticated=False)
def comments(request, track_id):
    track = get_object_or_404(Track.objects.published(), pk=track_id)
    if request.method == 'GET':
        visible = list(track.comments.filter(is_hidden=False).select_related('author__profile'))
        allowed = set()
        result = []
        for comment in visible:
            if comment.parent_id and comment.parent_id not in allowed:
                continue
            allowed.add(comment.pk)
            result.append({
                'id': comment.pk, 'parent_id': comment.parent_id,
                'author': comment.author.username, 'text': comment.text,
                'timestamp_seconds': comment.timestamp_seconds,
                'avatar': image_url(comment.author.profile.avatar),
                'created_at': comment.created_at.isoformat(),
            })
        return JsonResponse({'comments': result})
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                'error': 'authentication_required',
                'message': 'Войдите, чтобы написать комментарий.'
            },
            status=401
        )
    data = json_body(request)
    text = data.get('text', '')
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > 1000:
        raise ValidationError('Комментарий должен содержать от 1 до 1000 символов.')
    timestamp = integer(data.get('timestamp_seconds', 0), 'Таймкод', maximum=track.duration_seconds or 86400)
    parent = None
    if data.get('parent_id') is not None:
        parent = get_object_or_404(
            Comment,
            pk=integer(data['parent_id'], 'Комментарий', 1),
            track=track,
            is_hidden=False
        )
        ancestor, depth = parent, 1
        while ancestor.parent_id:
            ancestor = ancestor.parent
            if ancestor.is_hidden:
                raise ValidationError('Эта ветка комментариев скрыта.')
            depth += 1
        if depth > 3:
            raise ValidationError('Достигнута максимальная глубина ответов.')
        timestamp = parent.timestamp_seconds
    if track.duration_seconds and timestamp > track.duration_seconds:
        raise ValidationError('Таймкод находится за пределами трека.')
    comment = Comment.objects.create(
        author=request.user,
        track=track,
        parent=parent,
        text=text.strip(),
        timestamp_seconds=timestamp
    )
    return JsonResponse({
        'id': comment.pk, 'parent_id': comment.parent_id, 'author': request.user.username,
        'text': comment.text, 'timestamp_seconds': timestamp,
        'avatar': image_url(request.user.profile.avatar), 'created_at': comment.created_at.isoformat(),
    }, status=201)


@api_endpoint()
def add_to_history(request, track_id):
    track = get_object_or_404(Track.objects.published(), pk=track_id)
    recent = timezone.now() - timedelta(minutes=5)
    if not ListeningHistory.objects.filter(user=request.user, track=track, timestamp__gte=recent).exists():
        ListeningHistory.objects.create(user=request.user, track=track)
    return JsonResponse({'status': 'success'})
