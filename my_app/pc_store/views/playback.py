import mimetypes
import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from pc_store.http import api_endpoint, json_body
from pc_store.models import PlayEvent, Track


@api_endpoint(authenticated=False)
def record_play(request, track_id):
    data = json_body(request)
    token = data.get('playback_token')
    if not isinstance(token, str) or not token.strip() or len(token) > 64:
        raise ValidationError('Некорректный идентификатор прослушивания.')
    track = get_object_or_404(Track.objects.published(), pk=track_id)
    with transaction.atomic():
        event, created = PlayEvent.objects.get_or_create(
            playback_token=token,
            defaults={
                'track': track,
                'user': request.user if request.user.is_authenticated else None
            }
        )
        if event.track_id != track.pk:
            raise ValidationError('Идентификатор уже используется для другого трека.')
        if created:
            Track.objects.filter(pk=track.pk).update(plays_count=F('plays_count') + 1)
    return JsonResponse({'status': 'counted' if created else 'already_counted'})


def byte_range(header, size):
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header or '')
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError
    first, last = match.groups()
    if not first:
        length = int(last)
        if length <= 0:
            raise ValueError
        return max(0, size - length), size - 1
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        raise ValueError
    return start, end


def audio_chunks(field, start, length):
    with field.storage.open(field.name, 'rb') as audio:
        audio.seek(start)
        while length > 0:
            chunk = audio.read(min(65536, length))
            if not chunk:
                break
            length -= len(chunk)
            yield chunk


@require_http_methods(['GET', 'HEAD'])
def track_audio(request, track_id):
    track = get_object_or_404(Track.objects.visible_to(request.user), pk=track_id)
    if not track.audio_file:
        raise Http404
    try:
        size = track.audio_file.storage.size(track.audio_file.name)
    except (FileNotFoundError, OSError) as error:
        raise Http404 from error
    start, end, status = 0, size - 1, 200
    if 'Range' in request.headers:
        try:
            start, end = byte_range(request.headers['Range'], size)
        except (ValueError, OverflowError):
            return HttpResponse(
                status=416,
                headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'}
            )
        status = 206
    length = end - start + 1
    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Length': str(length),
        'Cache-Control': 'private, max-age=0, must-revalidate',
        'X-Content-Type-Options': 'nosniff'
    }
    if status == 206:
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    content_type = mimetypes.guess_type(track.audio_file.name)[0] or 'application/octet-stream'
    if request.method == 'HEAD':
        return HttpResponse(status=status, content_type=content_type, headers=headers)
    return StreamingHttpResponse(
        audio_chunks(track.audio_file, start, length),
        status=status,
        content_type=content_type,
        headers=headers
    )
