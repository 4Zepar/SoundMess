import io
import json

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from pc_store.forms import TrackForm
from pc_store.models import Album, Artist, ModerationAction, Track
from .base import AppTestCase, audio_upload, cover_upload


class PublicationTests(AppTestCase):
    def track_data(self, track, **changes):
        data = {
            'title': track.title, 'genre': track.genre, 'mood': track.mood,
            'tempo': track.tempo, 'release_year': track.release_year or '',
            'release_type': track.release_type, 'lyrics': track.lyrics,
            'is_explicit': track.is_explicit, 'intent': 'submit',
        }
        data.update(changes)
        return data

    def release_data(self, album, **changes):
        data = {
            'title': album.title, 'description': album.description,
            'release_type': album.release_type, 'release_year': album.release_year or '',
            'tracks': list(album.tracks.values_list('pk', flat=True)), 'intent': 'submit',
        }
        data.update(changes)
        return data

    def test_unchanged_published_release_keeps_approval_and_publication(self):
        album = self.make_album(
            cover=cover_upload(), reviewed_at=timezone.now(),
            reviewed_by=self.moderator, moderation_note='Approved by moderator',
        )
        fields = ('moderation_status', 'published_at', 'reviewed_at', 'reviewed_by_id', 'moderation_note', 'cover')
        before = Album.objects.filter(pk=album.pk).values(*fields).get()
        self.login(self.artist_user)
        for intent in ('submit', 'draft'):
            with self.subTest(intent=intent):
                response = self.client.post(
                    reverse('edit_release', args=[album.pk]), self.release_data(album, intent=intent),
                )
                self.assertRedirects(response, reverse('artist_dashboard'))
                self.assertEqual(Album.objects.filter(pk=album.pk).values(*fields).get(), before)
                self.assertEqual(list(album.tracks.all()), [self.track])
                self.assertTrue(Album.objects.published().filter(pk=album.pk).exists())

    def test_track_order_alone_does_not_resubmit_a_release(self):
        other = self.make_track()
        album = self.make_album(tracks=[self.track, other])
        self.login(self.artist_user)
        self.client.post(
            reverse('edit_release', args=[album.pk]),
            self.release_data(album, tracks=[other.pk, self.track.pk]),
        )
        album.refresh_from_db()
        self.assertEqual(album.moderation_status, 'approved')

    def test_changed_published_release_requires_another_review(self):
        album = self.make_album(reviewed_at=timezone.now(), reviewed_by=self.moderator)
        self.login(self.artist_user)
        response = self.client.post(
            reverse('edit_release', args=[album.pk]), self.release_data(album, title='Updated release'),
        )
        self.assertRedirects(response, reverse('artist_dashboard'))
        album.refresh_from_db()
        self.assertEqual(album.title, 'Updated release')
        self.assertEqual(album.moderation_status, 'pending')
        self.assertIsNone(album.published_at)
        self.assertIsNone(album.reviewed_at)
        self.assertIsNone(album.reviewed_by)
        self.assertFalse(Album.objects.published().filter(pk=album.pk).exists())

    def test_unchanged_published_track_is_not_resubmitted(self):
        published_at = self.track.published_at
        self.login(self.artist_user)
        response = self.client.post(reverse('edit_track', args=[self.track.pk]), {
            'title': self.track.title, 'genre': self.track.genre,
            'mood': self.track.mood, 'tempo': self.track.tempo,
            'release_year': self.track.release_year, 'release_type': self.track.release_type,
            'lyrics': self.track.lyrics, 'intent': 'submit',
        })
        self.assertRedirects(response, reverse('artist_dashboard'))
        self.track.refresh_from_db()
        self.assertEqual(self.track.moderation_status, 'approved')
        self.assertEqual(self.track.published_at, published_at)

    def test_published_editors_explain_how_changes_are_submitted(self):
        album = self.make_album()
        self.login(self.artist_user)
        for route, object_id, label in (
            ('edit_release', album.pk, 'Сохранить изменения'),
            ('edit_track', self.track.pk, 'Отправить изменения на проверку'),
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(route, args=[object_id]))
                self.assertContains(response, label)
                self.assertNotContains(response, 'Сохранить черновик')

    def test_every_track_field_change_requires_review_even_with_draft_intent(self):
        self.login(self.artist_user)
        changes = [
            {'title': 'Changed title'}, {'genre': 'jazz'}, {'mood': 'happy'},
            {'tempo': 'fast'}, {'release_year': 2025}, {'release_type': 'ep'},
            {'lyrics': 'Updated lyrics'}, {'is_explicit': True},
            {'audio_file': audio_upload(seconds=3)}, {'cover': cover_upload('new.png')},
            {'cover-clear': 'on'},
        ]
        for change in changes:
            with self.subTest(field=next(iter(change))):
                track = self.make_track(
                    cover=cover_upload(), moderation_note='Previously approved',
                    reviewed_at=timezone.now(), reviewed_by=self.moderator,
                )
                response = self.client.post(
                    reverse('edit_track', args=[track.pk]),
                    self.track_data(track, intent='draft', **change),
                )
                self.assertRedirects(response, reverse('artist_dashboard'))
                track.refresh_from_db()
                self.assertEqual(track.moderation_status, 'pending')
                self.assertEqual(track.moderation_note, '')
                self.assertIsNone(track.published_at)
                self.assertIsNone(track.reviewed_at)
                self.assertIsNone(track.reviewed_by)
                self.assertFalse(Track.objects.published().filter(pk=track.pk).exists())
                if 'audio_file' in change:
                    self.assertEqual(track.duration_seconds, 3)

    def test_missing_or_forged_intent_cannot_keep_an_edited_track_published(self):
        self.login(self.artist_user)
        for intent in (None, 'approved'):
            with self.subTest(intent=intent):
                track = self.make_track()
                data = self.track_data(track, title='Needs approval', moderation_status='approved')
                if intent is None:
                    data.pop('intent')
                else:
                    data['intent'] = intent
                self.client.post(reverse('edit_track', args=[track.pk]), data)
                track.refresh_from_db()
                self.assertEqual(track.moderation_status, 'pending')

    def test_edits_of_submitted_tracks_cannot_be_saved_as_drafts(self):
        self.login(self.artist_user)
        for status in ('pending', 'rejected', 'hidden'):
            with self.subTest(status=status):
                track = self.make_track(moderation_status=status)
                url = reverse('edit_track', args=[track.pk])
                editor = self.client.get(url)
                self.assertNotContains(editor, 'Сохранить черновик')
                self.assertContains(editor, 'Отправить изменения на проверку')
                self.client.post(url, self.track_data(track, title='Corrected track', intent='draft'))
                track.refresh_from_db()
                self.assertEqual(track.moderation_status, 'pending')

    def test_edited_track_and_its_release_are_public_only_after_approval(self):
        album = self.make_album()
        self.login(self.artist_user)
        self.client.post(
            reverse('edit_track', args=[self.track.pk]),
            self.track_data(self.track, lyrics='Revised lyrics', intent='draft'),
        )
        self.client.logout()
        self.assertEqual(self.client.get(self.track.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(self.track.audio_url).status_code, 404)
        self.assertEqual(self.client.get(album.get_absolute_url()).status_code, 404)
        self.login(self.moderator)
        queue = self.client.get(reverse('moderation_tracks'))
        self.assertContains(queue, self.track.title)
        self.client.post(reverse('review_track', args=[self.track.pk]), {'decision': 'approved'})
        self.client.logout()
        self.assertEqual(self.client.get(self.track.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(album.get_absolute_url()).status_code, 200)

    def test_unsent_draft_can_be_prepared_before_submission(self):
        track = self.make_track(moderation_status='draft', published_at=None)
        self.login(self.artist_user)
        self.client.post(
            reverse('edit_track', args=[track.pk]),
            self.track_data(track, title='Work in progress', intent='draft'),
        )
        track.refresh_from_db()
        self.assertEqual(track.moderation_status, 'draft')
        self.assertFalse(Track.objects.published().filter(pk=track.pk).exists())

    def test_removing_a_track_not_in_release_preserves_publication(self):
        album = self.make_album()
        other = self.make_track()
        published_at = album.published_at
        self.login(self.artist_user)
        response = self.client.post(
            reverse('remove_track_from_album'),
            json.dumps({'album_id': album.pk, 'track_id': other.pk}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        album.refresh_from_db()
        self.assertEqual(album.moderation_status, 'approved')
        self.assertEqual(album.published_at, published_at)
        self.assertEqual(list(album.tracks.all()), [self.track])

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
