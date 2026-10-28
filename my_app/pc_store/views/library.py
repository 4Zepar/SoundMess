from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from pc_store.forms import AlbumForm
from pc_store.http import api_endpoint, integer, json_body
from pc_store.models import Album, Track
from pc_store.selectors import album_cards, track_cards
from pc_store.services.albums import add_album_track
from pc_store.services.publication import prepare_submission, require_approved_artist, validate_release


@login_required
def profile_view(request):
    visible_tracks = Track.objects.visible_to(request.user)
    return render(request, 'profile.html', {
        'profile': request.user.profile,
        'favorite_tracks': track_cards(request.user, visible_tracks.filter(likes=request.user)),
        'my_albums': album_cards(
            Album.objects.filter(owner=request.user, is_public=False, is_favorite_folder=False)
        ),
        'saved_albums': album_cards(request.user.saved_albums.published()),
        'my_tracks': track_cards(request.user, Track.objects.filter(artist__user=request.user)),
        'history': request.user.history.filter(
            track__in=visible_tracks
        ).select_related('track__artist__user')[:20],
        'wallet': request.user.wallet,
    })


@login_required
def album_editor(request, album_id=None, public=False):
    if public:
        try:
            require_approved_artist(request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return redirect('artist_application')
    album = get_object_or_404(
        Album,
        pk=album_id,
        owner=request.user,
        is_favorite_folder=False,
        is_public=public
    ) if album_id else Album(owner=request.user, is_public=public)
    form = AlbumForm(
        request.POST or None,
        request.FILES or None,
        user=request.user,
        public=public,
        instance=album
    )
    if request.method == 'POST' and form.is_valid():
        if public and album.pk and album.moderation_status == 'approved' and not form.has_changed():
            messages.info(request, 'Релиз уже опубликован. Изменений нет — повторная проверка не нужна.')
            return redirect('artist_dashboard')
        submit = public and request.POST.get('intent') == 'submit'
        try:
            if submit:
                validate_release(form.instance, form.cleaned_data['tracks'])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            with transaction.atomic():
                album = form.save(commit=False)
                if public:
                    prepare_submission(album, submit=submit)
                album.save()
                form.save_m2m()
            messages.success(request, 'Релиз отправлен на проверку.' if submit else 'Изменения сохранены.')
            return redirect('artist_dashboard' if public else 'profile')
    return render(request, 'create_album.html', {'form': form, 'album': album, 'public': public})


@login_required
@require_POST
def delete_album(request, album_id):
    album = get_object_or_404(Album, pk=album_id, owner=request.user, is_favorite_folder=False)
    album.delete()
    messages.success(request, 'Альбом удалён.')
    return redirect('profile')


@api_endpoint()
def add_track_to_album(request):
    data = json_body(request)
    track = get_object_or_404(
        Track.objects.visible_to(request.user),
        pk=integer(data.get('track_id'), 'Трек', 1)
    )
    album = get_object_or_404(
        Album,
        pk=integer(data.get('album_id'), 'Альбом', 1),
        owner=request.user,
        is_favorite_folder=False
    )
    if album.is_public:
        require_approved_artist(request.user)
        if track.artist.user_id != request.user.pk:
            raise PermissionDenied
        if track.moderation_status != 'approved':
            raise ValidationError('Трек ещё не одобрен.')
        if album.release_type == 'single' and album.tracks.exclude(pk=track.pk).exists():
            raise ValidationError('Сингл должен содержать один трек.')
    with transaction.atomic():
        added = add_album_track(album, track)
        if added:
            if album.is_public:
                prepare_submission(album, submit=True)
                album.save()
    return JsonResponse({'status': 'added' if added else 'exists'})


@api_endpoint()
def remove_track_from_album(request):
    data = json_body(request)
    album = get_object_or_404(
        Album,
        pk=integer(data.get('album_id'), 'Альбом', 1),
        owner=request.user,
        is_favorite_folder=False
    )
    track_id = integer(data.get('track_id'), 'Трек', 1)
    with transaction.atomic():
        if album.tracks.filter(pk=track_id).exists():
            album.tracks.remove(track_id)
            if album.is_public:
                prepare_submission(album, submit=False)
                album.save()
    return JsonResponse({'status': 'removed'})


@login_required
@require_POST
def add_album_to_favorites(request, album_id):
    album = get_object_or_404(Album.objects.published(), pk=album_id)
    if request.POST.get('saved') == 'false':
        album.saved_by.remove(request.user)
        messages.success(request, 'Релиз убран из медиатеки.')
    else:
        album.saved_by.add(request.user)
        messages.success(request, 'Релиз сохранён в медиатеку.')
    return redirect(album)
