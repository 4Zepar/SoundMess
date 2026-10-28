import json

from django.urls import reverse
from django.contrib.auth import get_user_model

from pc_store.models import Artist, Comment, Follow, Track
from .base import AppTestCase


class SocialTests(AppTestCase):
    def post_json(self, name, data, args=()):
        return self.client.post(reverse(name, args=args), json.dumps(data), content_type='application/json')

    def test_like_updates_favorites_and_count_without_toggle_retries(self):
        self.login()
        url = reverse('toggle_like', args=[self.track.pk])
        for _ in range(2):
            response = self.client.post(url, '{"liked":true}', content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['like_count'], 1)
        response = self.client.get(reverse('profile'))
        self.assertIn(self.track, response.context['favorite_tracks'])
        self.client.post(url, '{"liked":false}', content_type='application/json')
        self.assertFalse(self.track.likes.filter(pk=self.listener.pk).exists())

    def test_saved_album_is_independent_of_liked_tracks(self):
        album = self.make_album()
        self.login()
        self.track.likes.add(self.listener)
        self.assertNotIn(album, self.client.get(reverse('profile')).context['saved_albums'])
        self.client.post(reverse('add_album_to_favorites', args=[album.pk]))
        self.assertIn(album, self.client.get(reverse('profile')).context['saved_albums'])

    def test_artist_can_save_and_unsave_their_own_published_release(self):
        album = self.make_album()
        url = reverse('add_album_to_favorites', args=[album.pk])
        self.login(self.artist_user)
        self.assertContains(self.client.get(album.get_absolute_url()), f'action="{url}"')
        for _ in range(2):
            self.assertRedirects(self.client.post(url, {'saved': 'true'}), album.get_absolute_url())
        self.assertEqual(album.saved_by.filter(pk=self.artist_user.pk).count(), 1)
        self.assertIn(album, self.client.get(reverse('profile')).context['saved_albums'])
        self.assertFalse(self.track.likes.filter(pk=self.artist_user.pk).exists())
        self.assertContains(self.client.get(album.get_absolute_url()), 'из медиатеки')
        self.assertRedirects(self.client.post(url, {'saved': 'false'}), album.get_absolute_url())
        self.assertNotIn(album, self.client.get(reverse('profile')).context['saved_albums'])

    def test_own_private_or_unpublished_album_cannot_be_saved_as_a_release(self):
        self.login(self.artist_user)
        for public, status in ((False, 'draft'), (True, 'draft'), (True, 'pending'), (True, 'hidden')):
            with self.subTest(public=public, status=status):
                album = self.make_album(is_public=public, moderation_status=status)
                url = reverse('add_album_to_favorites', args=[album.pk])
                self.assertNotContains(self.client.get(album.get_absolute_url()), f'action="{url}"')
                self.assertEqual(self.client.post(url, {'saved': 'true'}).status_code, 404)
                self.assertFalse(album.saved_by.exists())

    def test_valid_non_object_json_returns_400(self):
        self.login()
        for payload in ['[1]', '1', '"text"', '{broken', '{"number":' + '9' * 5000 + '}']:
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse('add_track_to_album'),
                    payload,
                    content_type='application/json'
                )
                self.assertEqual(response.status_code, 400)

    def test_async_comment_preserves_time_and_escapes_html(self):
        self.login()
        response = self.post_json(
            'add_comment',
            {'text': '<script>unsafe()</script>', 'timestamp_seconds': 47},
            [self.track.pk]
        )
        self.assertEqual(response.status_code, 201)
        comment = Comment.objects.get(pk=response.json()['id'])
        self.assertEqual(comment.timestamp_seconds, 47)
        html = self.client.get(self.track.get_absolute_url()).content.decode()
        self.assertIn('&lt;script&gt;unsafe()', html)
        self.assertNotIn('<script>unsafe()', html)

    def test_comment_rejects_negative_or_out_of_range_time(self):
        self.login()
        for time in [-1, 121, 2**100, True, [], 'not-a-number']:
            with self.subTest(time=time):
                self.assertEqual(
                    self.post_json(
                        'add_comment',
                        {'text': 'Test', 'timestamp_seconds': time},
                        [self.track.pk]
                    ).status_code,
                    400
                )

    def test_hidden_reply_is_not_rendered(self):
        root = Comment.objects.create(author=self.listener, track=self.track, text='Visible root')
        Comment.objects.create(
            author=self.listener,
            track=self.track,
            parent=root,
            text='HIDDEN_REPLY',
            is_hidden=True
        )
        self.assertNotContains(self.client.get(self.track.get_absolute_url()), 'HIDDEN_REPLY')

    def test_descendants_of_hidden_parent_are_not_exposed(self):
        root = Comment.objects.create(
            author=self.listener,
            track=self.track,
            text='Hidden parent',
            is_hidden=True
        )
        Comment.objects.create(author=self.listener, track=self.track, parent=root, text='SECRET_DESCENDANT')
        self.assertNotContains(self.client.get(self.track.get_absolute_url()), 'SECRET_DESCENDANT')
        response = self.client.get(reverse('add_comment', args=[self.track.pk]))
        self.assertEqual(response.json()['comments'], [])

    def test_follow_is_idempotent_when_desired_state_is_provided(self):
        self.login()
        for _ in range(2):
            response = self.post_json('toggle_follow', {'following': True}, [self.artist.pk])
            self.assertTrue(response.json()['following'])
        self.assertEqual(Follow.objects.filter(follower=self.listener, artist=self.artist).count(), 1)

    def test_feed_contains_albums_and_singles_without_duplicate_album_tracks(self):
        album = self.make_album()
        single = self.make_track(title='New standalone single')
        self.login()
        Follow.objects.create(follower=self.listener, artist=self.artist)
        entries = self.client.get(reverse('feed')).context['entries']
        self.assertEqual(
            {(entry['kind'], entry['item'].pk) for entry in entries},
            {('album', album.pk), ('track', single.pk)}
        )

    def test_feed_lists_only_current_users_available_followed_artists(self):
        User = get_user_model()
        other = Artist.objects.create(user=User.objects.create_user(username='another-artist'), moderation_status='approved')
        blocked = Artist.objects.create(user=User.objects.create_user(username='blocked-artist', is_active=False), moderation_status='approved')
        pending = Artist.objects.create(user=User.objects.create_user(username='pending-artist'), moderation_status='pending')
        for artist in (self.artist, blocked, pending):
            Follow.objects.create(follower=self.listener, artist=artist)
        Follow.objects.create(follower=self.moderator, artist=other)
        self.login()
        response = self.client.get(reverse('feed'))
        self.assertEqual(list(response.context['followed_artists']), [self.artist])
        self.assertContains(response, f'class="followed-artist" href="{self.artist.get_absolute_url()}"')
        for artist in (other, blocked, pending):
            self.assertNotContains(response, f'class="followed-artist" href="{artist.get_absolute_url()}"')

    def test_followed_artist_is_listed_even_without_publications(self):
        self.track.moderation_status = 'draft'
        self.track.save(update_fields=['moderation_status'])
        Follow.objects.create(follower=self.listener, artist=self.artist)
        self.login()
        response = self.client.get(reverse('feed'))
        self.assertEqual(list(response.context['followed_artists']), [self.artist])
        self.assertFalse(response.context['entries'])
        self.assertContains(response, 'Публикаций пока нет')

    def test_unfollowing_removes_artist_and_their_publications_from_feed(self):
        Follow.objects.create(follower=self.listener, artist=self.artist)
        self.login()
        self.post_json('toggle_follow', {'following': False}, [self.artist.pk])
        response = self.client.get(reverse('feed'))
        self.assertFalse(response.context['followed_artists'])
        self.assertFalse(response.context['entries'])
        self.assertContains(response, 'Подпишись на артистов')
