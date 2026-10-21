import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .forms import TrackUploadForm
from .importers import JamendoAdapter
from .models import Album, Artist, Comment, Donation, Follow, PlayEvent, Track, Wallet


class PublicListeningTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='artist', password='password')
		self.artist = Artist.objects.create(user=self.user)
		self.track = Track.objects.create(
			artist=self.artist,
			title='Demo track',
			audio_file=SimpleUploadedFile('demo.mp3', b'audio data', content_type='audio/mpeg'),
		)

	def test_guest_can_open_catalog(self):
		response = self.client.get(reverse('home'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Demo track')

	def test_guest_cannot_toggle_favorite(self):
		response = self.client.post(reverse('toggle_favorite', args=[self.track.id]))

		self.assertEqual(response.status_code, 302)
		self.assertFalse(Album.objects.filter(is_favorite_folder=True, tracks=self.track).exists())


class MutationContractTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='listener', password='password')
		self.client.force_login(self.user)
		self.album = Album.objects.create(owner=self.user, title='Playlist')

	def test_delete_album_requires_post(self):
		response = self.client.get(reverse('delete_album', args=[self.album.id]))

		self.assertEqual(response.status_code, 405)
		self.assertTrue(Album.objects.filter(id=self.album.id).exists())

	def test_add_track_rejects_malformed_json(self):
		response = self.client.post(
			reverse('add_track_to_album'),
			data='{invalid json',
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()['error'], 'Invalid JSON')

	def test_like_requires_authentication(self):
		self.client.logout()
		response = self.client.post(reverse('toggle_like', args=[1]))

		self.assertEqual(response.status_code, 401)

	def test_comment_rejects_negative_timestamp(self):
		artist_user = User.objects.create_user(username='artist', password='password')
		artist = Artist.objects.create(user=artist_user)
		track = Track.objects.create(
			artist=artist,
			title='Timed track',
			duration_seconds=180,
			audio_file=SimpleUploadedFile('timed.mp3', b'audio data', content_type='audio/mpeg'),
		)
		response = self.client.post(
			reverse('add_comment', args=[track.id]),
			data=json.dumps({'text': 'At this moment', 'timestamp_seconds': -1}),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json()['error'], 'Timestamp cannot be negative')

	def test_play_count_is_idempotent(self):
		artist_user = User.objects.create_user(username='play-artist', password='password')
		artist = Artist.objects.create(user=artist_user)
		track = Track.objects.create(
			artist=artist,
			title='Counted track',
			audio_file=SimpleUploadedFile('counted.mp3', b'audio data', content_type='audio/mpeg'),
		)
		payload = json.dumps({'playback_token': 'unique-playback-token'})

		first_response = self.client.post(
			reverse('record_play', args=[track.id]),
			data=payload,
			content_type='application/json',
		)
		second_response = self.client.post(
			reverse('record_play', args=[track.id]),
			data=payload,
			content_type='application/json',
		)

		track.refresh_from_db()
		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(second_response.status_code, 200)
		self.assertEqual(first_response.json()['status'], 'counted')
		self.assertEqual(second_response.json()['status'], 'already_counted')
		self.assertEqual(track.plays_count, 1)
		self.assertEqual(PlayEvent.objects.filter(playback_token='unique-playback-token').count(), 1)


class FollowAndFeedTests(TestCase):
	def setUp(self):
		self.listener = User.objects.create_user(username='feed-listener', password='password')
		self.artist_user = User.objects.create_user(username='approved-artist', password='password')
		self.artist = Artist.objects.create(
			user=self.artist_user,
			moderation_status='approved',
		)

	def test_guest_cannot_follow_artist(self):
		response = self.client.post(reverse('toggle_follow', args=[self.artist.id]))

		self.assertEqual(response.status_code, 401)

	def test_follow_toggle_and_feed(self):
		self.client.force_login(self.listener)
		follow_url = reverse('toggle_follow', args=[self.artist.id])

		first_response = self.client.post(follow_url)
		second_response = self.client.post(follow_url)
		self.assertTrue(first_response.json()['following'])
		self.assertFalse(second_response.json()['following'])
		self.assertFalse(Follow.objects.filter(follower=self.listener, artist=self.artist).exists())

		self.client.post(follow_url)
		release = Album.objects.create(
			owner=self.artist_user,
			title='Public release',
			is_public=True,
		)
		private_release = Album.objects.create(
			owner=self.artist_user,
			title='Private release',
			is_public=False,
		)

		response = self.client.get(reverse('feed'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, release.title)
		self.assertNotContains(response, private_release.title)

	def test_only_approved_artists_are_listed(self):
		Artist.objects.create(
			user=User.objects.create_user(username='pending-artist', password='password'),
		)

		response = self.client.get(reverse('artist_list'))

		self.assertContains(response, self.artist_user.username)
		self.assertNotContains(response, 'pending-artist')


class ModerationTests(TestCase):
	def setUp(self):
		self.pending_user = User.objects.create_user(username='pending-applicant', password='password')
		self.artist = Artist.objects.create(user=self.pending_user)
		self.staff = User.objects.create_user(
			username='moderator',
			password='password',
			is_staff=True,
		)

	def test_regular_user_cannot_open_moderation(self):
		self.client.force_login(self.pending_user)

		response = self.client.get(reverse('moderation_dashboard'))

		self.assertEqual(response.status_code, 403)

	def test_staff_can_approve_artist_application(self):
		self.client.force_login(self.staff)

		response = self.client.post(
			reverse('review_artist_application', args=[self.artist.id]),
			{'decision': 'approved', 'note': 'Проверено'},
		)

		self.artist.refresh_from_db()
		self.assertRedirects(response, reverse('moderation_applications'))
		self.assertEqual(self.artist.moderation_status, 'approved')
		self.assertEqual(self.artist.moderation_note, 'Проверено')
		self.assertIsNotNone(self.artist.reviewed_at)


class ArtistDashboardTests(TestCase):
	def setUp(self):
		self.artist_user = User.objects.create_user(username='dashboard-artist', password='password')
		self.artist = Artist.objects.create(user=self.artist_user, moderation_status='approved')
		self.track = Track.objects.create(
			artist=self.artist,
			title='Popular track',
			audio_file=SimpleUploadedFile('popular.mp3', b'audio data', content_type='audio/mpeg'),
		)

	def test_listener_cannot_open_artist_dashboard(self):
		listener = User.objects.create_user(username='dashboard-listener', password='password')
		self.client.force_login(listener)

		response = self.client.get(reverse('artist_dashboard'))

		self.assertEqual(response.status_code, 403)

	def test_artist_dashboard_contains_top_track(self):
		self.track.plays_count = 12
		self.track.save(update_fields=['plays_count'])
		self.client.force_login(self.artist_user)

		response = self.client.get(reverse('artist_dashboard'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.track.title)
		self.assertContains(response, '12 прослушиваний')


class DonationTests(TestCase):
	def setUp(self):
		self.donor = User.objects.create_user(username='donor', password='password')
		self.artist_user = User.objects.create_user(username='supported-artist', password='password')
		self.artist = Artist.objects.create(user=self.artist_user, moderation_status='approved')
		Wallet.objects.filter(user=self.donor).update(balance_cents=1000)

	def test_donation_transfers_balance_atomically(self):
		self.client.force_login(self.donor)

		response = self.client.post(
			reverse('support_artist', args=[self.artist.id]),
			{'amount': '5.00'},
		)

		self.assertRedirects(response, reverse('support_artist', args=[self.artist.id]))
		self.assertEqual(Wallet.objects.get(user=self.donor).balance_cents, 500)
		self.assertEqual(Wallet.objects.get(user=self.artist_user).balance_cents, 500)
		self.assertEqual(Donation.objects.filter(donor=self.donor, artist=self.artist).count(), 1)

	def test_donation_rejects_insufficient_balance(self):
		self.client.force_login(self.donor)

		response = self.client.post(
			reverse('support_artist', args=[self.artist.id]),
			{'amount': '20.00'},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Недостаточно средств')
		self.assertEqual(Donation.objects.count(), 0)
		self.assertEqual(Wallet.objects.get(user=self.donor).balance_cents, 1000)

	def test_artist_cannot_donate_to_self(self):
		self.client.force_login(self.artist_user)

		response = self.client.post(
			reverse('support_artist', args=[self.artist.id]),
			{'amount': '1.00'},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Нельзя поддержать самого себя')


class ImporterTests(TestCase):
	def test_jamendo_track_mapping_normalizes_metadata(self):
		imported = JamendoAdapter._map_track({
			'id': 42,
			'name': '  Imported Song  ',
			'artist_name': 'Demo Artist',
			'releasedate': '2024-05-10',
			'duration': 185,
			'shareurl': 'https://example.test/track/42',
			'audio': 'https://example.test/audio.mp3',
			'image': 'https://example.test/cover.jpg',
			'license_ccurl': 'https://creativecommons.org/licenses/by/4.0/',
			'musicinfo': {'tags': {'genres': ['Indie']}},
		})

		self.assertEqual(imported.external_id, '42')
		self.assertEqual(imported.title, 'Imported Song')
		self.assertEqual(imported.release_year, 2024)
		self.assertEqual(imported.duration_seconds, 185)
		self.assertEqual(imported.genre, 'Indie')

	def test_dry_run_requires_client_id(self):
		with self.assertRaisesMessage(Exception, 'JAMENDO_CLIENT_ID'):
			call_command('import_jamendo', dry_run=True)


class UploadValidationTests(TestCase):
	def test_audio_extension_is_validated(self):
		form = TrackUploadForm(files={
			'audio_file': SimpleUploadedFile('payload.exe', b'not audio'),
		})

		self.assertFalse(form.is_valid())
		self.assertIn('Разрешены только MP3', str(form.errors['audio_file']))

	def test_audio_size_is_validated(self):
		large_audio = SimpleUploadedFile('large.mp3', b'x' * (50 * 1024 * 1024 + 1))
		form = TrackUploadForm(files={'audio_file': large_audio})

		self.assertFalse(form.is_valid())
		self.assertIn('50 МБ', str(form.errors['audio_file']))


class CommentModerationTests(TestCase):
	def setUp(self):
		self.staff = User.objects.create_user(username='comment-moderator', password='password', is_staff=True)
		artist_user = User.objects.create_user(username='comment-artist', password='password')
		artist = Artist.objects.create(user=artist_user, moderation_status='approved')
		self.track = Track.objects.create(
			artist=artist,
			title='Comment track',
			audio_file=SimpleUploadedFile('comment.mp3', b'audio data'),
		)
		self.author = User.objects.create_user(username='comment-author', password='password')
		self.comment = Comment.objects.create(author=self.author, track=self.track, text='Needs review')

	def test_staff_can_hide_comment(self):
		self.client.force_login(self.staff)

		response = self.client.post(reverse('toggle_comment_visibility', args=[self.comment.id]))

		self.comment.refresh_from_db()
		self.assertRedirects(response, reverse('moderation_comments'))
		self.assertTrue(self.comment.is_hidden)


class ProfileAndStaffUiTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='ui-user', password='password')
		self.artist_user = User.objects.create_user(username='ui-artist', password='password')
		self.artist = Artist.objects.create(user=self.artist_user, moderation_status='approved')
		self.album = Album.objects.create(owner=self.artist_user, title='Public album', is_public=True)
		self.staff = User.objects.create_user(username='ui-staff', password='password', is_staff=True)

	def test_user_can_edit_profile(self):
		self.client.force_login(self.user)

		response = self.client.post(reverse('profile_edit'), {'bio': 'Updated bio'})

		self.assertRedirects(response, reverse('profile'))
		self.user.profile.refresh_from_db()
		self.assertEqual(self.user.profile.bio, 'Updated bio')

	def test_artist_page_shows_public_album(self):
		response = self.client.get(reverse('artist_detail', args=[self.artist.id]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.album.title)

	def test_staff_can_open_user_directory(self):
		self.client.force_login(self.staff)

		response = self.client.get(reverse('moderation_users'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.user.username)
		self.assertContains(response, self.artist_user.username)
