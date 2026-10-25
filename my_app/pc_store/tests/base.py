import io
import tempfile
import wave

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from pc_store.models import Album, Artist, Track


def audio_upload(name='sample.wav', seconds=2):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b'\x00\x00' * 8000 * seconds)
    return SimpleUploadedFile(name, stream.getvalue(), content_type='audio/wav')


def cover_upload(name='cover.png'):
    stream = io.BytesIO()
    with Image.new('RGB', (2, 2), color=(255, 98, 15)) as cover:
        cover.save(stream, format='PNG')
    return SimpleUploadedFile(name, stream.getvalue(), content_type='image/png')


class AppTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = tempfile.TemporaryDirectory(prefix='soundmess-tests-')
        cls.addClassCleanup(cls.media.cleanup)
        cls.settings_override = override_settings(
            MEDIA_ROOT=cls.media.name,
            PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
        )
        cls.settings_override.enable()
        cls.addClassCleanup(cls.settings_override.disable)

    def setUp(self):
        User = get_user_model()
        self.listener = User.objects.create_user(username='listener')
        self.artist_user = User.objects.create_user(username='artist')
        self.artist_user.profile.role = 'artist'
        self.artist_user.profile.save(update_fields=['role'])
        self.artist = Artist.objects.create(user=self.artist_user, moderation_status='approved')
        self.moderator = User.objects.create_user(username='moderator', is_staff=True)
        self.moderator.groups.add(Group.objects.get(name='Модераторы'))
        self.administrator = User.objects.create_user(username='administrator', is_staff=True)
        self.administrator.groups.add(Group.objects.get(name='Администраторы'))
        self.track = self.make_track(title='Published song')

    def make_track(self, **kwargs):
        values = {
            'artist': self.artist, 'title': 'Another song', 'audio_file': audio_upload(),
            'genre': 'rock', 'moderation_status': 'approved', 'published_at': timezone.now(),
            'duration_seconds': 120, 'release_year': 2024,
        }
        values.update(kwargs)
        return Track.objects.create(**values)

    def make_album(self, **kwargs):
        tracks = kwargs.pop('tracks', [self.track])
        values = {
            'owner': self.artist_user, 'title': 'Published album', 'is_public': True,
            'moderation_status': 'approved', 'published_at': timezone.now(), 'release_year': 2024,
        }
        values.update(kwargs)
        album = Album.objects.create(**values)
        album.tracks.set(tracks)
        return album

    def login(self, user=None):
        self.client.force_login(user or self.listener)
