import io
import json

from django.contrib.auth import get_user_model
from django.urls import reverse

from pc_store.forms import TrackForm
from pc_store.models import Album, Artist, ModerationAction, Track
from .base import AppTestCase, audio_upload


class PublicationTests(AppTestCase):
    def test_drafts_and_pending_tracks_are_not_public(self):
        hidden = self.make_track(title='Pending secret', moderation_status='pending')
        self.assertNotContains(self.client.get(reverse('home')), hidden.title)
        self.assertEqual(self.client.get(hidden.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(hidden.audio_url).status_code, 404)
        self.login(self.artist_user)
        self.assertEqual(self.client.get(hidden.get_absolute_url()).status_code, 200)

    def test_tracks_of_unapproved_artists_are_hidden(self):
        self.artist.moderation_status = 'pending'
        self.artist.save(update_fields=['moderation_status'])
        self.assertNotContains(self.client.get(reverse('home')), self.track.title)

    def test_audio_upload_reads_actual_duration(self):
        form = TrackForm(
            data={
                'title': 'New track',
                'genre': 'indie',
                'release_type': 'single',
                'release_year': 2025
            },
            files={'audio_file': audio_upload(seconds=3)}
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.duration_seconds, 3)

    def test_disguised_non_audio_file_is_rejected(self):
        upload = audio_upload()
        upload.file = io.BytesIO(b'not an audio file')
        form = TrackForm(
            data={'title': 'Invalid', 'genre': 'rock', 'release_type': 'single'},
            files={'audio_file': upload}
        )
        self.assertFalse(form.is_valid())
        self.assertIn('audio_file', form.errors)

    def test_upload_submits_for_review(self):
        self.login(self.artist_user)
        response = self.client.post(
            reverse('upload_track'),
            {
                'title': 'Review me',
                'genre': 'indie',
                'release_type': 'single',
                'intent': 'submit',
                'audio_file': audio_upload()
            }
        )
        self.assertEqual(response.status_code, 302)
        track = Track.objects.get(title='Review me')
        self.assertEqual(track.moderation_status, 'pending')
        self.assertEqual(track.duration_seconds, 2)

    def test_editing_public_track_requires_another_review(self):
        self.login(self.artist_user)
        response = self.client.post(
            reverse('edit_track', args=[self.track.pk]),
            {
                'title': 'Changed title',
                'genre': 'rock',
                'release_type': 'single',
                'intent': 'submit'
            }
        )
        self.assertEqual(response.status_code, 302)
        self.track.refresh_from_db()
        self.assertEqual(self.track.moderation_status, 'pending')
        self.client.logout()
        self.assertNotContains(self.client.get(reverse('home')), 'Changed title')

    def test_moderator_can_approve_and_log_pending_track(self):
        self.track.moderation_status = 'pending'
        self.track.save(update_fields=['moderation_status'])
        self.login(self.moderator)
        response = self.client.post(reverse('review_track', args=[self.track.pk]), {'decision': 'approved'})
        self.assertEqual(response.status_code, 302)
        self.track.refresh_from_db()
        self.assertEqual(self.track.moderation_status, 'approved')
        self.assertTrue(
            ModerationAction.objects.filter(
                actor=self.moderator,
                target_type='track',
                target_id=self.track.pk,
                action='approved'
            ).exists()
        )

    def test_rejection_requires_reason(self):
        self.track.moderation_status = 'pending'
        self.track.save(update_fields=['moderation_status'])
        self.login(self.moderator)
        self.client.post(reverse('review_track', args=[self.track.pk]), {'decision': 'rejected'})
        self.track.refresh_from_db()
        self.assertEqual(self.track.moderation_status, 'pending')

    def test_release_cannot_contain_another_artists_track(self):
        other_user = get_user_model().objects.create_user(username='other-artist')
        other = Artist.objects.create(user=other_user, moderation_status='approved')
        foreign_track = self.make_track(artist=other)
        album = self.make_album()
        self.login(self.artist_user)
        response = self.client.post(
            reverse('add_track_to_album'),
            json.dumps({'track_id': foreign_track.pk, 'album_id': album.pk}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(album.tracks.filter(pk=foreign_track.pk).exists())

    def test_release_requires_approved_tracks(self):
        draft = self.make_track(moderation_status='draft')
        self.login(self.artist_user)
        response = self.client.post(
            reverse('create_release'),
            {
                'title': 'Not ready',
                'release_type': 'album',
                'tracks': [draft.pk],
                'intent': 'submit'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Сначала дождитесь одобрения')
        self.assertFalse(self.artist_user.albums.filter(title='Not ready').exists())

    def test_release_track_tiles_only_offer_the_artists_own_tracks(self):
        other_artist = Artist.objects.create(user=self.listener, moderation_status='approved')
        foreign_track = self.make_track(artist=other_artist, title='Foreign song')
        self.track.likes.add(self.artist_user)
        self.login(self.artist_user)

        response = self.client.get(reverse('create_release'))

        self.assertContains(response, 'class="track-row track-choice"', count=1)
        self.assertContains(response, f'data-url="{self.track.audio_url}"')
        self.assertContains(response, 'data-liked="true"')
        self.assertContains(response, '2:00')
        self.assertContains(response, 'type="button" data-play-track')
        self.assertNotContains(response, foreign_track.title)

        response = self.client.post(reverse('create_release'), {
            'title': 'Invalid selection', 'release_type': 'album',
            'tracks': [foreign_track.pk], 'intent': 'draft',
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('tracks', response.context['form'].errors)
        self.assertFalse(Album.objects.filter(title='Invalid selection').exists())

    def test_release_track_tiles_preserve_edit_and_invalid_post_selections(self):
        another = self.make_track(title='Second song')
        album = self.make_album()
        self.login(self.artist_user)
        url = reverse('edit_release', args=[album.pk])
        initial_response = self.client.get(url)
        invalid_response = self.client.post(url, {
            'title': '', 'release_type': 'album', 'tracks': [another.pk], 'intent': 'draft',
        })

        for response, selected_id in [(initial_response, self.track.pk), (invalid_response, another.pk)]:
            with self.subTest(selected_id=selected_id):
                self.assertEqual(response.status_code, 200)
                choices = response.context['form']['tracks']
                selected = {choice.data['value'].value for choice in choices if choice.data['selected']}
                self.assertEqual(selected, {selected_id})
                for choice in choices:
                    self.assertContains(response, choice.tag())

        self.assertIn('title', invalid_response.context['form'].errors)
        self.assertQuerySetEqual(album.tracks.all(), [self.track])

    def test_release_track_tiles_save_and_remove_selected_tracks(self):
        another = self.make_track(title='Second song')
        self.login(self.artist_user)
        response = self.client.post(reverse('create_release'), {
            'title': 'Selected tracks', 'release_type': 'album',
            'tracks': [self.track.pk, another.pk], 'intent': 'draft',
        })

        self.assertRedirects(response, reverse('artist_dashboard'))
        album = Album.objects.get(title='Selected tracks', owner=self.artist_user)
        self.assertSetEqual(set(album.tracks.all()), {self.track, another})

        response = self.client.post(reverse('edit_release', args=[album.pk]), {
            'title': album.title, 'release_type': 'album', 'tracks': [another.pk], 'intent': 'draft',
        })

        self.assertRedirects(response, reverse('artist_dashboard'))
        self.assertQuerySetEqual(album.tracks.all(), [another])

    def test_hidden_track_removes_release_from_public_catalog(self):
        album = self.make_album()
        self.track.moderation_status = 'hidden'
        self.track.save(update_fields=['moderation_status'])
        self.assertEqual(self.client.get(album.get_absolute_url()).status_code, 404)

    def test_missing_audio_does_not_crash_catalog(self):
        self.track.audio_file = ''
        self.track.save(update_fields=['audio_file'])
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

    def test_missing_file_disables_playback(self):
        self.track.audio_file = 'music/missing.wav'
        self.track.save(update_fields=['audio_file'])
        self.assertEqual(self.track.audio_url, '')
        self.assertContains(self.client.get(reverse('home')), 'Аудиофайл недоступен')

    def test_moderator_cannot_approve_own_material(self):
        artist = Artist.objects.create(user=self.moderator, moderation_status='approved')
        track = self.make_track(artist=artist, moderation_status='pending')
        self.login(self.moderator)
        self.client.post(reverse('review_track', args=[track.pk]), {'decision': 'approved'})
        track.refresh_from_db()
        self.assertEqual(track.moderation_status, 'pending')

    def test_listener_application_is_approved_and_unblocks_upload(self):
        self.login()
        response = self.client.post(reverse('artist_application'), {'bio': 'My original music'})
        self.assertEqual(response.status_code, 302)
        artist = Artist.objects.get(user=self.listener)
        self.assertEqual(artist.moderation_status, 'pending')
        self.assertRedirects(self.client.get(reverse('upload_track')), reverse('artist_application'))
        self.login(self.moderator)
        self.client.post(reverse('review_artist_application', args=[artist.pk]), {'decision': 'approved'})
        artist.refresh_from_db()
        self.assertEqual(artist.moderation_status, 'approved')
        self.login()
        self.assertEqual(self.client.get(reverse('upload_track')).status_code, 200)
