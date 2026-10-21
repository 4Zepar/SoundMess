import json

from django.urls import reverse

from pc_store.models import PlayEvent
from .base import AppTestCase


class PlaybackTests(AppTestCase):
    def test_play_is_counted_once_per_session(self):
        url = reverse('record_play', args=[self.track.pk])
        for _ in range(2):
            response = self.client.post(
                url,
                json.dumps({'playback_token': 'session-token'}),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 200)
        self.track.refresh_from_db()
        self.assertEqual(self.track.plays_count, 1)
        self.assertEqual(PlayEvent.objects.count(), 1)

    def test_play_token_cannot_be_reused_for_another_track(self):
        other = self.make_track()
        self.client.post(
            reverse('record_play', args=[self.track.pk]),
            '{"playback_token":"shared"}',
            content_type='application/json'
        )
        response = self.client.post(
            reverse('record_play', args=[other.pk]),
            '{"playback_token":"shared"}',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        other.refresh_from_db()
        self.assertEqual(other.plays_count, 0)

    def test_byte_range_and_suffix_requests(self):
        size = self.track.audio_file.size
        for range_header, expected in [('bytes=0-9', 10), ('bytes=-16', 16), (f'bytes={size-5}-', 5)]:
            with self.subTest(range=range_header):
                response = self.client.get(self.track.audio_url, HTTP_RANGE=range_header)
                self.assertEqual(response.status_code, 206)
                self.assertEqual(len(b''.join(response.streaming_content)), expected)
                self.assertEqual(int(response['Content-Length']), expected)

    def test_invalid_ranges_are_rejected(self):
        for value in ['bytes=999999-', 'bytes=10-2', 'bytes=-0', 'bytes=0-1,4-8', 'invalid']:
            with self.subTest(range=value):
                self.assertEqual(self.client.get(self.track.audio_url, HTTP_RANGE=value).status_code, 416)

    def test_head_does_not_stream_audio(self):
        response = self.client.head(self.track.audio_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(response['Content-Length']), self.track.audio_file.size)
        self.assertEqual(response.content, b'')

    def test_raw_media_path_cannot_bypass_publication_permissions(self):
        self.track.moderation_status = 'draft'
        self.track.save(update_fields=['moderation_status'])
        self.assertEqual(self.client.get('/media/' + self.track.audio_file.name).status_code, 404)
        self.assertEqual(self.client.get(self.track.audio_url).status_code, 404)
        self.login(self.artist_user)
        response = self.client.get(self.track.audio_url)
        self.assertEqual(response.status_code, 200)
        response.close()
