import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, F, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.utils import timezone
from .models import Album, Artist, Comment, Donation, Follow, ListeningHistory, PlayEvent, Profile, Track, Wallet
from .forms import DonationForm, ProfileForm, RegistrationForm, TrackFilterForm, TrackMetadataForm, TrackUploadForm, WalletTopUpForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .forms import AlbumForm

def track_list(request):
    filter_form = TrackFilterForm(request.GET or None)
    tracks = Track.objects.select_related('artist__user').all()

    if filter_form.is_valid():
        data = filter_form.cleaned_data
        search = data.get('search')
        if search:
            tracks = tracks.filter(
                Q(title__icontains=search)
                | Q(artist__user__username__icontains=search)
                | Q(contained_in__title__icontains=search)
            ).distinct()
        if data.get('genre'):
            tracks = tracks.filter(genre__icontains=data['genre'])
        if data.get('mood'):
            tracks = tracks.filter(mood__icontains=data['mood'])
        if data.get('release_year_from'):
            tracks = tracks.filter(release_year__gte=data['release_year_from'])
        if data.get('release_year_to'):
            tracks = tracks.filter(release_year__lte=data['release_year_to'])
        if data.get('release_type'):
            tracks = tracks.filter(release_type=data['release_type'])
        if data.get('duration') == 'short':
            tracks = tracks.filter(duration_seconds__lt=180)
        elif data.get('duration') == 'standard':
            tracks = tracks.filter(duration_seconds__gte=180, duration_seconds__lte=300)
        elif data.get('duration') == 'long':
            tracks = tracks.filter(duration_seconds__gt=300)
        if data.get('has_lyrics'):
            tracks = tracks.exclude(lyrics='')
        if data.get('explicit'):
            tracks = tracks.filter(is_explicit=True)

        sort = data.get('sort') or 'newest'
        if sort == 'popular':
            tracks = tracks.order_by('-plays_count', '-release_date')
        elif sort == 'liked':
            tracks = tracks.annotate(like_count=Count('likes')).order_by('-like_count', '-release_date')
        else:
            tracks = tracks.order_by('-release_date', '-id')
    else:
        tracks = tracks.order_by('-release_date', '-id')

    return render(request, 'index.html', {'tracks': tracks, 'filter_form': filter_form})


def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            
            role = form.cleaned_data.get('role')
            profile = user.profile
            profile.role = role
            profile.save()

            if role == 'artist':
                Artist.objects.create(user=user)
            
            login(request, user)
            return redirect('home')
    else:
        form = RegistrationForm()
    return render(request, 'register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


def artist_list(request):
    artists = Artist.objects.filter(moderation_status='approved').select_related('user').order_by('user__username')
    return render(request, 'artists.html', {'artists': artists})


def artist_detail(request, artist_id):
    artist = get_object_or_404(
        Artist.objects.select_related('user'),
        id=artist_id,
        moderation_status='approved',
    )
    tracks = artist.tracks.order_by('-release_date', '-id')
    albums = Album.objects.filter(owner=artist.user, is_public=True).order_by('-created_at')
    is_following = request.user.is_authenticated and Follow.objects.filter(
        follower=request.user,
        artist=artist,
    ).exists()
    return render(request, 'artist_detail.html', {
        'artist': artist,
        'tracks': tracks,
        'albums': albums,
        'is_following': is_following,
    })


@login_required
def feed_view(request):
    followed_artist_ids = Follow.objects.filter(
        follower=request.user,
    ).values_list('artist_id', flat=True)
    releases = Album.objects.filter(
        owner__artist__id__in=followed_artist_ids,
        is_public=True,
    ).select_related('owner').prefetch_related('tracks').order_by('-created_at')
    return render(request, 'feed.html', {'releases': releases})


def toggle_follow(request, artist_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    artist = get_object_or_404(Artist, id=artist_id, moderation_status='approved')
    if artist.user_id == request.user.id:
        return JsonResponse({'error': 'You cannot follow yourself'}, status=400)

    follow, created = Follow.objects.get_or_create(follower=request.user, artist=artist)
    if not created:
        follow.delete()
    return JsonResponse({
        'following': created,
        'followers_count': artist.followers.count(),
    })


def staff_required(view):
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff and not request.user.is_superuser:
            return render(request, '403.html', status=403)
        return view(request, *args, **kwargs)
    return wrapped


@login_required
def artist_dashboard(request):
    artist = Artist.objects.filter(user=request.user).first()
    if not artist or artist.moderation_status != 'approved':
        return render(request, '403.html', status=403)
    top_tracks = artist.tracks.order_by('-plays_count', '-release_date')[:5]
    today = timezone.localdate()
    start_date = today - timedelta(days=29)
    daily_counts = {
        row['day']: row['count']
        for row in artist.tracks.filter(
            play_events__created_at__date__gte=start_date,
        ).annotate(day=TruncDate('play_events__created_at')).values('day').annotate(
            count=Count('play_events'),
        ).order_by('day')
    }
    chart_labels = [(start_date + timedelta(days=offset)).isoformat() for offset in range(30)]
    chart_values = [daily_counts.get(start_date + timedelta(days=offset), 0) for offset in range(30)]
    return render(request, 'artist_dashboard.html', {
        'artist': artist,
        'top_tracks': top_tracks,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
    })


@login_required
def edit_track(request, track_id):
    track = get_object_or_404(
        Track,
        id=track_id,
        artist__user=request.user,
        artist__moderation_status='approved',
    )
    if request.method == 'POST':
        form = TrackMetadataForm(request.POST, request.FILES, instance=track)
        if form.is_valid():
            form.save()
            return redirect('artist_dashboard')
    else:
        form = TrackMetadataForm(instance=track)
    return render(request, 'edit_track.html', {'form': form, 'track': track})


@login_required
def support_artist(request, artist_id):
    artist = get_object_or_404(Artist, id=artist_id, moderation_status='approved')
    if request.method == 'POST':
        form = DonationForm(request.POST)
        if form.is_valid():
            amount_cents = int(form.cleaned_data['amount'] * 100)
            if artist.user_id == request.user.id:
                form.add_error(None, 'Нельзя поддержать самого себя.')
            else:
                with transaction.atomic():
                    donor_wallet, _ = Wallet.objects.select_for_update().get_or_create(user=request.user)
                    artist_wallet, _ = Wallet.objects.select_for_update().get_or_create(user=artist.user)
                    if donor_wallet.balance_cents < amount_cents:
                        form.add_error(None, 'Недостаточно средств на балансе.')
                    else:
                        donor_wallet.balance_cents -= amount_cents
                        artist_wallet.balance_cents += amount_cents
                        donor_wallet.save(update_fields=['balance_cents', 'updated_at'])
                        artist_wallet.save(update_fields=['balance_cents', 'updated_at'])
                        Donation.objects.create(
                            donor=request.user,
                            artist=artist,
                            amount_cents=amount_cents,
                            idempotency_key=uuid4().hex,
                        )
                        return redirect('support_artist', artist_id=artist.id)
    else:
        form = DonationForm()
    donations = Donation.objects.filter(donor=request.user, artist=artist)[:10]
    wallet = Wallet.objects.get_or_create(user=request.user)[0]
    return render(request, 'support_artist.html', {
        'artist': artist,
        'form': form,
        'wallet': wallet,
        'donations': donations,
    })


@staff_required
def moderation_dashboard(request):
    users = User.objects.select_related('profile', 'artist', 'wallet').order_by('username')
    for account in users:
        Wallet.objects.get_or_create(user=account)
    context = {
        'pending_artists_count': Artist.objects.filter(moderation_status='pending').count(),
        'users': users,
    }
    return render(request, 'moderation/dashboard.html', context)


@staff_required
def moderation_users(request):
    users = User.objects.select_related('profile', 'artist', 'wallet').order_by('username')
    for account in users:
        Wallet.objects.get_or_create(user=account)
    return render(request, 'moderation/users.html', {'users': users})


@staff_required
def moderation_user_detail(request, user_id):
    account = get_object_or_404(User.objects.select_related('profile', 'wallet'), id=user_id)
    context = {
        'account': account,
        'albums': account.albums.all().prefetch_related('tracks'),
        'tracks': Track.objects.filter(artist__user=account),
        'follows': account.artist_follows.select_related('artist__user'),
        'comments': account.track_comments.select_related('track'),
        'wallet': Wallet.objects.get_or_create(user=account)[0],
    }
    return render(request, 'moderation/user_detail.html', context)


def comment_page(request, track_id):
    track = get_object_or_404(Track.objects.select_related('artist__user'), id=track_id)
    comments = track.comments.filter(
        is_hidden=False,
        parent__isnull=True,
    ).select_related('author__profile').prefetch_related(
        'replies__author__profile',
        'replies__replies__author__profile',
    )
    return render(request, 'track_comments.html', {
        'track': track,
        'comments': comments,
    })


@staff_required
def adjust_user_balance(request, user_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    account = get_object_or_404(User, id=user_id)
    try:
        amount_cents = int(Decimal(request.POST.get('amount_usd', '')) * 100)
    except (TypeError, ValueError, InvalidOperation):
        return JsonResponse({'error': 'Введите сумму в USD'}, status=400)
    wallet = Wallet.objects.get_or_create(user=account)[0]
    if wallet.balance_cents + amount_cents < 0:
        return JsonResponse({'error': 'Баланс не может быть отрицательным'}, status=400)
    wallet.balance_cents += amount_cents
    wallet.save(update_fields=['balance_cents', 'updated_at'])
    return redirect('moderation_user_detail', user_id=account.id)


@staff_required
def delete_moderated_track(request, track_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    track = get_object_or_404(Track, id=track_id)
    user_id = track.artist.user_id
    track.delete()
    return redirect('moderation_user_detail', user_id=user_id)


@staff_required
def delete_moderated_album(request, album_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    album = get_object_or_404(Album, id=album_id)
    user_id = album.owner_id
    if not album.is_favorite_folder:
        album.delete()
    return redirect('moderation_user_detail', user_id=user_id)


@staff_required
def delete_moderated_comment(request, comment_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    comment = get_object_or_404(Comment, id=comment_id)
    user_id = comment.author_id
    comment.delete()
    return redirect('moderation_user_detail', user_id=user_id)


@staff_required
def moderation_applications(request):
    applications = Artist.objects.filter(
        moderation_status='pending',
    ).select_related('user').order_by('user__date_joined')
    return render(request, 'moderation/applications.html', {'applications': applications})


@staff_required
def moderation_comments(request):
    comments = Comment.objects.select_related('author', 'track').order_by('-created_at')[:100]
    return render(request, 'moderation/comments.html', {'comments': comments})


@staff_required
def toggle_comment_visibility(request, comment_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    comment = get_object_or_404(Comment, id=comment_id)
    comment.is_hidden = not comment.is_hidden
    comment.save(update_fields=['is_hidden'])
    return redirect('moderation_comments')


@staff_required
def review_artist_application(request, artist_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    artist = get_object_or_404(Artist, id=artist_id)
    decision = request.POST.get('decision')
    if decision not in {'approved', 'rejected'}:
        return JsonResponse({'error': 'Invalid decision'}, status=400)

    artist.moderation_status = decision
    artist.moderation_note = request.POST.get('note', '').strip()[:2000]
    artist.reviewed_at = timezone.now()
    artist.save(update_fields=['moderation_status', 'moderation_note', 'reviewed_at'])
    return redirect('moderation_applications')


@login_required 
def profile_view(request):
    my_albums = Album.objects.filter(owner=request.user)
    my_tracks = None
    
    if request.user.profile.role == 'artist':
        my_tracks = Track.objects.filter(artist__user=request.user)

    history = ListeningHistory.objects.filter(user=request.user)[:10]

    favorite_album = Album.objects.filter(owner=request.user, is_favorite_folder=True).first()
    favorite_tracks = favorite_album.tracks.all() if favorite_album else Track.objects.none()
    saved_albums = Album.objects.filter(
        is_public=True,
        tracks__in=favorite_tracks,
    ).exclude(owner=request.user).select_related('owner').distinct()
    context = {
        'my_albums': my_albums,
        'saved_albums': saved_albums,
        'my_tracks': my_tracks,
        'history': history,  
        'profile': request.user.profile, 
        'wallet': Wallet.objects.get_or_create(user=request.user)[0],
    }
    return render(request, 'profile.html', context)


@login_required
def profile_edit(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = ProfileForm(instance=request.user.profile)
    return render(request, 'profile_edit.html', {'form': form})


@login_required
def wallet_top_up(request):
    if request.method == 'POST':
        form = WalletTopUpForm(request.POST)
        if form.is_valid():
            wallet = Wallet.objects.get_or_create(user=request.user)[0]
            wallet.balance_cents += int(form.cleaned_data['amount'] * 100)
            wallet.save(update_fields=['balance_cents', 'updated_at'])
            return redirect('profile')
    else:
        form = WalletTopUpForm()
    wallet = Wallet.objects.get_or_create(user=request.user)[0]
    return render(request, 'wallet_top_up.html', {'form': form, 'wallet': wallet})


@login_required
def toggle_favorite(request, track_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    track = get_object_or_404(Track, id=track_id)
    favorite_album, created = Album.objects.get_or_create(
        owner=request.user, 
        is_favorite_folder=True,
        defaults={'title': 'Любимое'}
    )
    
    if track in favorite_album.tracks.all():
        favorite_album.tracks.remove(track)
    else:
        favorite_album.tracks.add(track)
        
    return redirect(request.META.get('HTTP_REFERER', 'home'))


@login_required
def add_album_to_favorites(request, album_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    album = get_object_or_404(Album, id=album_id, is_public=True)
    favorite_album = Album.objects.get_or_create(
        owner=request.user,
        is_favorite_folder=True,
        defaults={'title': 'Любимое'},
    )[0]
    favorite_album.tracks.add(*album.tracks.all())
    return redirect('profile')


def toggle_like(request, track_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    track = get_object_or_404(Track, id=track_id)
    if track.likes.filter(id=request.user.id).exists():
        track.likes.remove(request.user)
        liked = False
    else:
        track.likes.add(request.user)
        liked = True

    return JsonResponse({
        'liked': liked,
        'like_count': track.likes.count(),
    })


def add_comment(request, track_id):
    if not request.user.is_authenticated:
        if request.method == 'GET':
            track = get_object_or_404(Track, id=track_id)
            comments = track.comments.filter(is_hidden=False).select_related('author')
            return JsonResponse({'comments': [
                {
                    'id': comment.id,
                    'author': comment.author.username,
                    'text': comment.text,
                    'timestamp_seconds': comment.timestamp_seconds,
                }
                for comment in comments
            ]})
        return JsonResponse({'error': 'Authentication required'}, status=401)
    if request.method == 'GET':
        track = get_object_or_404(Track, id=track_id)
        comments = track.comments.filter(is_hidden=False).select_related('author')
        return JsonResponse({'comments': [
            {
                'id': comment.id,
                'author': comment.author.username,
                'text': comment.text,
                'timestamp_seconds': comment.timestamp_seconds,
            }
            for comment in comments
        ]})
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = _json_body(request)
    if not data:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    text = str(data.get('text', '')).strip()
    track = get_object_or_404(Track, id=track_id)
    parent = None
    parent_id = data.get('parent_id')
    if parent_id:
        parent = get_object_or_404(Comment, id=parent_id, track=track)
    try:
        timestamp_seconds = int(data.get('timestamp_seconds', 0))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid timestamp'}, status=400)

    if not text or len(text) > 1000:
        return JsonResponse({'error': 'Comment text is required'}, status=400)
    if parent:
        timestamp_seconds = parent.timestamp_seconds
    if timestamp_seconds < 0:
        return JsonResponse({'error': 'Timestamp cannot be negative'}, status=400)

    if track.duration_seconds and timestamp_seconds > track.duration_seconds:
        return JsonResponse({'error': 'Timestamp is outside the track'}, status=400)

    comment = Comment.objects.create(
        author=request.user,
        track=track,
        parent=parent,
        text=text,
        timestamp_seconds=timestamp_seconds,
    )
    return JsonResponse({
        'id': comment.id,
        'parent_id': comment.parent_id,
        'author': request.user.username,
        'text': comment.text,
        'timestamp_seconds': comment.timestamp_seconds,
        'created_at': comment.created_at.isoformat(),
    }, status=201)


def record_play(request, track_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = _json_body(request)
    if not data or not isinstance(data.get('playback_token'), str):
        return JsonResponse({'error': 'playback_token is required'}, status=400)

    playback_token = data['playback_token'].strip()
    if not playback_token or len(playback_token) > 64:
        return JsonResponse({'error': 'Invalid playback_token'}, status=400)

    track = get_object_or_404(Track, id=track_id)
    play_event, created = PlayEvent.objects.get_or_create(
        playback_token=playback_token,
        defaults={
            'track': track,
            'user': request.user if request.user.is_authenticated else None,
        },
    )
    if created:
        Track.objects.filter(id=track.id).update(plays_count=F('plays_count') + 1)

    return JsonResponse({'status': 'counted' if created else 'already_counted'})


def album_detail(request, album_id):
    album = get_object_or_404(Album, id=album_id)
    
    if not album.is_public and album.owner != request.user:
        return render(request, '403.html', status=403) 

    return render(request, 'album_detail.html', {
        'album': album,
        'tracks': album.tracks.all()
    })




@login_required
def upload_track(request):
    artist = Artist.objects.filter(user=request.user).first()
    if request.user.profile.role != 'artist' or not artist or artist.moderation_status != 'approved':
        return render(request, '403.html', status=403) 

    if request.method == 'POST':
        form = TrackUploadForm(request.POST, request.FILES)
        if form.is_valid():
            track = form.save(commit=False)
            track.artist = artist
            track.save()
            return redirect('profile')
    else:
        form = TrackUploadForm()
    
    return render(request, 'upload_track.html', {'form': form})




@login_required
def create_album(request):
    if request.method == 'POST':
        form = AlbumForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            album = form.save(commit=False)
            album.owner = request.user
            album.save()
            
            selected_tracks = form.cleaned_data['tracks']
            if album.is_public:
                final_tracks = selected_tracks.filter(artist__user=request.user)
                album.tracks.set(final_tracks)
            else:
                album.tracks.set(selected_tracks)
                
            return redirect('profile')
    else:
        form = AlbumForm(user=request.user)
    return render(request, 'create_album.html', {'form': form})


@login_required
def delete_album(request, album_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    album = get_object_or_404(Album, id=album_id, owner=request.user)

    if not album.is_favorite_folder:
        album.delete()
        
    return redirect('profile')


def _json_body(request):
    try:
        return json.loads(request.body or '{}')
    except (TypeError, json.JSONDecodeError):
        return None

@login_required
def add_track_to_album(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = _json_body(request)
    if not data:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    track_id = data.get('track_id')
    album_id = data.get('album_id')
    if not track_id or not album_id:
        return JsonResponse({'error': 'track_id and album_id are required'}, status=400)

    track = get_object_or_404(Track, id=track_id)
    album = get_object_or_404(Album, id=album_id, owner=request.user)

    if track in album.tracks.all():
        return JsonResponse({'status': 'exists'})

    album.tracks.add(track)
    return JsonResponse({'status': 'added'})


@login_required
def remove_track_from_album(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = _json_body(request)
    if not data:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    track_id = data.get('track_id')
    album_id = data.get('album_id')
    if not track_id or not album_id:
        return JsonResponse({'error': 'track_id and album_id are required'}, status=400)

    album = get_object_or_404(Album, id=album_id, owner=request.user)
    track = get_object_or_404(Track, id=track_id)

    album.tracks.remove(track)
    return JsonResponse({'status': 'removed'})



def add_to_history(request, track_id):
    if request.user.is_authenticated:
        track = get_object_or_404(Track, id=track_id)
        ListeningHistory.objects.create(user=request.user, track=track)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'not_authenticated'}, status=401)