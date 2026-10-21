from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from pc_store.forms import ArtistApplicationForm, TrackForm
from pc_store.models import Album, Artist, PlayEvent, Track
from pc_store.selectors import album_cards, track_cards
from pc_store.services.publication import prepare_submission, require_approved_artist


@login_required
def artist_application(request):
    artist = Artist.objects.filter(user=request.user).first()
    form = ArtistApplicationForm(request.POST or None, instance=artist)
    if request.method == 'POST' and (
        not artist or artist.moderation_status != 'approved'
    ) and form.is_valid():
        artist = form.save(commit=False)
        artist.user = request.user
        artist.moderation_status = 'pending'
        artist.moderation_note = ''
        artist.reviewed_at = None
        artist.save()
        messages.success(request, 'Заявка отправлена. Решение появится на этой странице.')
        return redirect('artist_application')
    return render(request, 'artist_application.html', {'form': form, 'application': artist})


@login_required
def artist_dashboard(request):
    try:
        artist = require_approved_artist(request.user)
    except ValidationError:
        return redirect('artist_application')
    period = 7 if request.GET.get('period') == '7' else 30
    start = timezone.localdate() - timedelta(days=period - 1)
    counts = dict(
        PlayEvent.objects.filter(
            track__artist=artist,
            created_at__date__gte=start
        ).annotate(day=TruncDate('created_at')).values('day').annotate(total=Count('pk')).order_by('day').values_list('day', 'total')
    )
    dates = [start + timedelta(days=index) for index in range(period)]
    values = [counts.get(day, 0) for day in dates]
    maximum = max(values, default=0)
    points = ' '.join(
        f'{index * 600 / max(period - 1, 1):.1f},{150 - value * 130 / (maximum or 1):.1f}' for index,
        value in enumerate(values)
    )
    return render(request, 'artist_dashboard.html', {
        'artist': artist, 'period': period, 'chart_points': points,
        'chart_values': values, 'chart_dates': dates, 'chart_total': sum(values), 'chart_max': maximum,
        'tracks': track_cards(request.user, artist.tracks.all()),
        'top_tracks': artist.tracks.order_by('-plays_count', '-pk')[:5],
        'albums': album_cards(Album.objects.filter(owner=request.user, is_public=True)),
        'followers_count': artist.followers.count(),
    })


@login_required
def track_editor(request, track_id=None):
    try:
        artist = require_approved_artist(request.user)
    except ValidationError:
        return redirect('artist_application')
    track = get_object_or_404(Track, pk=track_id, artist=artist) if track_id else Track(artist=artist)
    form = TrackForm(request.POST or None, request.FILES or None, instance=track)
    if request.method == 'POST' and form.is_valid():
        submit = request.POST.get('intent') == 'submit'
        with transaction.atomic():
            track = form.save(commit=False)
            prepare_submission(track, submit=submit)
            track.save()
        messages.success(request, 'Трек отправлен на проверку.' if submit else 'Черновик сохранён.')
        return redirect('artist_dashboard')
    return render(request, 'upload_track.html', {'form': form, 'track': track})
