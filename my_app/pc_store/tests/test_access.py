from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from pc_store.models import Album, Artist
from .base import AppTestCase


class AccessTests(AppTestCase):
    def test_guests_can_browse_and_listen(self):
        album = self.make_album()
        for name, args in [
            ('home', []),
            ('release_list', []),
            ('artist_list', []),
            ('artist_detail', [self.artist.pk]),
            ('album_detail', [album.pk]),
            ('comment_page', [self.track.pk])
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
        response = self.client.get(reverse('track_audio', args=[self.track.pk]), HTTP_RANGE='bytes=0-7')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(b''.join(response.streaming_content)), 8)

    def test_guests_cannot_mutate_personal_data(self):
        for name, args in [
            ('toggle_like', [self.track.pk]),
            ('toggle_follow', [self.artist.pk]),
            ('add_to_history', [self.track.pk]),
            ('add_track_to_album', [])
        ]:
            with self.subTest(endpoint=name):
                self.assertEqual(
                    self.client.post(
                        reverse(name, args=args),
                        '{}',
                        content_type='application/json'
                    ).status_code,
                    401
                )

    def test_mutations_require_post(self):
        self.login()
        for name, args in [
            ('toggle_like', [self.track.pk]),
            ('record_play', [self.track.pk]),
            ('add_to_history', [self.track.pk]),
            ('logout', [])
        ]:
            with self.subTest(endpoint=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 405)

    def test_listener_cannot_access_moderation(self):
        self.login()
        self.assertEqual(self.client.get(reverse('moderation_dashboard')).status_code, 403)

    def test_moderator_cannot_manage_accounts_or_balances(self):
        self.login(self.moderator)
        self.assertEqual(self.client.get(reverse('moderation_dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('moderation_users')).status_code, 403)
        self.assertEqual(
            self.client.post(reverse('adjust_user_balance', args=[self.listener.pk]), {}).status_code,
            403
        )

    def test_administrator_can_manage_accounts(self):
        self.login(self.administrator)
        self.assertEqual(self.client.get(reverse('moderation_users')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('moderation_user_detail', args=[self.listener.pk])).status_code,
            200
        )

    def test_administrators_are_not_offered_an_artist_application(self):
        superuser = get_user_model().objects.create_user(
            username='super-administrator', is_superuser=True, is_staff=True,
        )
        for user in (self.administrator, superuser):
            with self.subTest(user=user.username):
                self.login(user)
                response = self.client.get(reverse('home'))
                self.assertNotContains(response, f'href="{reverse("artist_application")}"')
                self.assertNotContains(response, 'Для артистов')
                self.assertContains(response, f'href="{reverse("moderation_dashboard")}"')

    def test_listeners_and_moderators_keep_artist_application_links(self):
        for user in (self.listener, self.moderator):
            with self.subTest(user=user.username):
                self.login(user)
                response = self.client.get(reverse('home'))
                self.assertContains(response, f'href="{reverse("artist_application")}"', count=2)

    def test_administrator_with_approved_artist_keeps_artist_tools(self):
        self.artist_user.groups.add(*self.administrator.groups.all())
        self.login(self.artist_user)
        response = self.client.get(reverse('home'))
        self.assertContains(response, f'href="{reverse("artist_dashboard")}"')
        self.assertContains(response, f'href="{reverse("upload_track")}"')
        self.assertNotContains(response, f'href="{reverse("artist_application")}"')

    def test_staff_flag_alone_does_not_grant_moderation(self):
        user = get_user_model().objects.create_user(username='unprivileged-staff', is_staff=True)
        self.login(user)
        self.assertEqual(self.client.get(reverse('moderation_dashboard')).status_code, 403)

    def test_csrf_is_enforced_on_api(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.listener)
        response = client.post(
            reverse('toggle_like', args=[self.track.pk]),
            '{}',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_registration_rejects_weak_password(self):
        count = get_user_model().objects.count()
        response = self.client.post(
            reverse('register'),
            {
                'username': 'new-user',
                'role': 'listener',
                'password1': '1',
                'password2': '1'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_user_model().objects.count(), count)

    def test_artist_registration_requires_a_separate_complete_application(self):
        response = self.client.post(reverse('register'), {
            'username': 'new-artist', 'role': 'artist',
            'password1': 'Valid-demo-pass-4826', 'password2': 'Valid-demo-pass-4826',
        })
        self.assertRedirects(response, reverse('artist_application'))
        user = get_user_model().objects.get(username='new-artist')
        self.assertFalse(Artist.objects.filter(user=user).exists())

    def test_listener_cannot_publish_release(self):
        self.login()
        response = self.client.post(
            reverse('create_release'),
            {'title': 'Illegal release', 'intent': 'submit'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Album.objects.filter(title='Illegal release').exists())

    def test_tampered_playlist_flag_does_not_publish(self):
        self.login()
        response = self.client.post(
            reverse('create_album'),
            {'title': 'My playlist', 'is_public': 'on', 'tracks': [self.track.pk]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Album.objects.get(title='My playlist').is_public)

    def test_admin_cannot_block_themself(self):
        self.login(self.administrator)
        response = self.client.post(
            reverse('moderation_update_user', args=[self.administrator.pk]),
            {'action': 'active', 'active': 'false'}
        )
        self.assertEqual(response.status_code, 403)
        self.administrator.refresh_from_db()
        self.assertTrue(self.administrator.is_active)

    def test_blocking_artist_hides_their_public_content(self):
        album = self.make_album()
        self.login(self.administrator)
        self.client.post(
            reverse('moderation_update_user', args=[self.artist_user.pk]),
            {'action': 'active', 'active': 'false'}
        )
        self.client.logout()
        self.assertNotContains(self.client.get(reverse('home')), self.track.title)
        self.assertEqual(self.client.get(album.get_absolute_url()).status_code, 404)
