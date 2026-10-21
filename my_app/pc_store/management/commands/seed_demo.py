import io
import math
import os
import sys
import wave
from array import array
from datetime import timedelta
from getpass import getpass
from uuid import uuid5, NAMESPACE_URL

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from pc_store.models import Album, Artist, Comment, Follow, PlayEvent, Track
from pc_store.services.payments import adjust_balance


def sample_audio(frequency):
    """An original, quiet synthetic tone for testing; this is not a music recording."""
    rate, seconds = 8000, 40
    frames = array('h')
    for index in range(rate * seconds):
        moment = index / rate
        envelope = min(1, moment, seconds - moment)
        value = math.sin(2 * math.pi * frequency * moment)
        value += 0.3 * math.sin(2 * math.pi * frequency * 1.5 * moment)
        frames.append(round(1600 * envelope * value))
    if sys.byteorder != 'little':
        frames.byteswap()
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(frames.tobytes())
    return output.getvalue()


class Command(BaseCommand):
    help = 'Создаёт демонстрационные аккаунты. Опционально добавляет явно обозначенное тестовое аудио.'

    def add_arguments(self, parser):
        parser.add_argument('--with-sample-audio', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.environ.get('SOUNDMESS_DEMO_PASSWORD') or getpass('Пароль новых демо-аккаунтов: ')
        if len(password) < 10:
            raise CommandError('Используйте пароль длиной не менее 10 символов.')
        accounts = {}
        for name, group in (
            ('demo_listener', None), ('demo_pulse', None), ('demo_echo', None),
            ('demo_moderator', 'Модераторы'), ('demo_admin', 'Администраторы'),
        ):
            user, created = get_user_model().objects.get_or_create(username=name)
            if created:
                user.set_password(password)
                user.is_staff = bool(group)
                user.save(update_fields=['password', 'is_staff'])
                if group:
                    user.groups.add(Group.objects.get(name=group))
                self.stdout.write(f'Создан {name}')
            else:
                self.stdout.write(f'{name} уже существует; пароль и права не изменены.')
            accounts[name] = user
        artists = []
        for name in ('demo_pulse', 'demo_echo'):
            user = accounts[name]
            artist, created = Artist.objects.get_or_create(
                user=user,
                defaults={
                    'bio': 'Демонстрационный артист. Аудио — синтетические тестовые сигналы.',
                    'moderation_status': 'approved'
                },
            )
            if created:
                user.profile.role = 'artist'
                user.profile.save(update_fields=['role'])
            artists.append(artist)
        listener = accounts['demo_listener']
        adjust_balance(
            user=listener, amount_cents=2500, operation_key='seed-demo:opening-balance',
            description='Начальный демонстрационный баланс',
        )
        Follow.objects.get_or_create(follower=listener, artist=artists[0])
        if options['with_sample_audio']:
            self.create_catalog(artists, listener)
        self.stdout.write(self.style.SUCCESS('Демо готово. Реальные платежи не выполняются.'))

    def create_catalog(self, artists, listener):
        now = timezone.now()
        tracks = []
        for index, title in enumerate(
            ('Пульс', 'Тихий вечер', 'Орбита', 'Ночной город', 'Отражение', 'Рассвет')
        ):
            artist = artists[index % 2]
            track, created = Track.objects.get_or_create(
                artist=artist, title=f'[Демо] {title}',
                defaults={
                    'moderation_status': 'approved', 'published_at': now,
                    'duration_seconds': 40, 'release_year': now.year,
                    'genre': ('electronic', 'indie', 'rock')[index % 3],
                    'mood': ('energetic', 'relax', 'melancholic')[index % 3],
                    'tempo': ('fast', 'slow', 'medium')[index % 3],
                    'lyrics': 'Синтетический тестовый сигнал для демонстрации плеера.' if index % 2 == 0 else '',
                    'is_explicit': index == 4,
                },
            )
            if created:
                track.audio_file.save(f'demo-{index + 1}.wav', ContentFile(sample_audio(180 + index * 40)))
                for day in range(14):
                    for event_index in range((day + index) % 4):
                        token = uuid5(NAMESPACE_URL, f'soundmess-demo:{track.pk}:{day}:{event_index}').hex
                        event = PlayEvent.objects.create(track=track, user=listener, playback_token=token)
                        PlayEvent.objects.filter(pk=event.pk).update(created_at=now - timedelta(days=day))
                track.plays_count = track.play_events.count()
                track.save(update_fields=['plays_count'])
            tracks.append(track)
        for artist in artists:
            album, created = Album.objects.get_or_create(
                owner=artist.user, title='[Демо] Звуковые зарисовки', is_public=True,
                defaults={
                    'moderation_status': 'approved',
                    'published_at': now,
                    'release_type': 'ep',
                    'release_year': now.year
                },
            )
            if created:
                album.tracks.set(track for track in tracks if track.artist_id == artist.pk)
        playlist, created = Album.objects.get_or_create(
            owner=listener,
            title='[Демо] Моя подборка',
            is_public=False
        )
        if created:
            playlist.tracks.set(tracks[:3])
        tracks[0].likes.add(listener)
        Comment.objects.get_or_create(
            author=listener, track=tracks[0], text='Тестовый комментарий с таймкодом.',
            defaults={'timestamp_seconds': 12},
        )
