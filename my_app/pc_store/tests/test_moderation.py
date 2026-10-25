from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from pc_store.models import Artist, Comment, ModerationAction
from .base import AppTestCase


class CommentModerationTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.other_track = self.make_track(title='Standalone single')
        self.comment = Comment.objects.create(author=self.listener, track=self.track, text='First discussion')
        self.hidden = Comment.objects.create(
            author=self.listener, track=self.track, text='Hidden discussion', is_hidden=True,
        )
        Comment.objects.create(author=self.listener, track=self.other_track, text='Other discussion')
        self.login(self.moderator)

    def test_index_lists_songs_and_counts_instead_of_comment_text(self):
        self.make_track(title='No comments yet')
        self.make_album()
        self.make_album(title='Another release with the same song')
        response = self.client.get(reverse('moderation_comments'))
        self.assertCountEqual(response.context['tracks'], [self.track, self.other_track])
        song = next(track for track in response.context['tracks'] if track.pk == self.track.pk)
        self.assertEqual(song.comment_count, 2)
        self.assertEqual(song.hidden_comment_count, 1)
        self.assertNotContains(response, self.comment.text)
        self.assertNotContains(response, 'No comments yet')

    def test_release_filter_uses_author_releases_and_ignores_private_playlists(self):
        self.make_album(release_type='ep')
        self.make_album(owner=self.listener, is_public=False, tracks=[self.other_track])
        self.make_album(title='Single release', release_type='single', tracks=[self.other_track])
        albums = self.client.get(reverse('moderation_comments'), {'release_kind': 'album'})
        singles = self.client.get(reverse('moderation_comments'), {'release_kind': 'single'})
        self.assertEqual(list(albums.context['tracks']), [self.track])
        self.assertEqual(list(singles.context['tracks']), [self.other_track])

    def test_artist_search_and_release_filters_combine(self):
        account = get_user_model().objects.create_user(username='other-musician')
        artist = Artist.objects.create(user=account, moderation_status='approved')
        song = self.make_track(artist=artist, title='Standalone foreign song')
        Comment.objects.create(author=self.listener, track=song, text='Foreign discussion')
        self.make_album()
        response = self.client.get(reverse('moderation_comments'), {
            'q': 'Standalone', 'artist': self.artist.pk, 'release_kind': 'single',
        })
        self.assertEqual(list(response.context['tracks']), [self.other_track])

    def test_invalid_artist_filter_has_a_form_error(self):
        response = self.client.get(reverse('moderation_comments'), {'artist': 'not-an-id'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('artist', response.context['filter_form'].errors)
        self.assertFalse(response.context['tracks'])

    def test_song_page_contains_its_hidden_comments_and_replies(self):
        Comment.objects.create(
            author=self.artist_user, track=self.track, parent=self.comment, text='Reply in this discussion',
        )
        response = self.client.get(reverse('moderation_track_comments', args=[self.track.pk]))
        self.assertContains(response, self.comment.text)
        self.assertContains(response, self.hidden.text)
        self.assertContains(response, 'Reply in this discussion')
        self.assertNotContains(response, 'Other discussion')
        self.assertEqual(response.context['comment_count'], 3)

    def test_visibility_returns_to_the_same_song_and_preserves_filter_context(self):
        query = '?artist=' + str(self.artist.pk) + '&release_kind=single&list_page=2&page=1'
        response = self.client.post(
            reverse('toggle_comment_visibility', args=[self.comment.pk]) + query,
            {'hidden': 'true'},
        )
        self.comment.refresh_from_db()
        self.assertTrue(self.comment.is_hidden)
        destination = urlsplit(response.url)
        self.assertEqual(destination.path, reverse('moderation_track_comments', args=[self.track.pk]))
        self.assertEqual(parse_qs(destination.query)['list_page'], ['2'])
        detail = self.client.get(response.url)
        back = parse_qs(detail.context['back_query'])
        self.assertEqual(back['page'], ['2'])
        self.assertEqual(back['artist'], [str(self.artist.pk)])
        self.assertNotIn('list_page', back)
        self.assertTrue(ModerationAction.objects.filter(target_id=self.comment.pk, action='hidden').exists())
        self.client.post(
            reverse('toggle_comment_visibility', args=[self.comment.pk]), {'hidden': 'false'},
        )
        self.comment.refresh_from_db()
        self.assertFalse(self.comment.is_hidden)
        self.assertTrue(ModerationAction.objects.filter(target_id=self.comment.pk, action='restored').exists())

    def test_song_discussion_paginates_without_dropping_old_comments(self):
        Comment.objects.bulk_create([
            Comment(author=self.listener, track=self.track, text=f'Comment {index}')
            for index in range(29)
        ])
        response = self.client.get(reverse('moderation_track_comments', args=[self.track.pk]), {'page': 2})
        self.assertEqual(response.context['comment_count'], 31)
        self.assertEqual(len(response.context['comments']), 1)

    def test_reply_in_a_hidden_branch_has_an_accurate_visibility_status(self):
        reply = Comment.objects.create(
            author=self.artist_user, track=self.track, parent=self.hidden, text='Hidden with parent',
        )
        response = self.client.get(reverse('moderation_track_comments', args=[self.track.pk]))
        item = next(comment for comment in response.context['comments'] if comment.pk == reply.pk)
        self.assertTrue(item.hidden_by_parent)
        self.assertContains(response, 'Скрыт вместе с веткой')

    def test_listener_cannot_read_or_moderate_private_discussions(self):
        self.login()
        for name, args in [('moderation_comments', []), ('moderation_track_comments', [self.track.pk])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)
        self.assertEqual(self.client.post(
            reverse('toggle_comment_visibility', args=[self.comment.pk]), {'hidden': 'true'},
        ).status_code, 403)
        self.comment.refresh_from_db()
        self.assertFalse(self.comment.is_hidden)

    def test_threads_keep_nested_replies_and_parent_links_in_order(self):
        first = Comment.objects.create(author=self.artist_user, track=self.track, parent=self.comment, text='First reply')
        nested = Comment.objects.create(author=self.listener, track=self.track, parent=first, text='Nested answer')
        second = Comment.objects.create(author=self.artist_user, track=self.track, parent=self.comment, text='Second reply')
        response = self.client.get(reverse('moderation_track_comments', args=[self.track.pk]))
        root = next(item for item in response.context['comment_threads'] if item.pk == self.comment.pk)
        self.assertEqual([item.pk for item in root.moderation_replies], [first.pk, second.pk])
        self.assertEqual(root.moderation_replies[0].moderation_replies[0].pk, nested.pk)
        self.assertEqual(root.descendant_count, 3)
        self.assertEqual(root.moderation_replies[0].moderation_replies[0].depth, 2)
        html = response.content.decode()
        positions = [html.index(f'id="comment-{pk}"') for pk in (self.comment.pk, first.pk, nested.pk, second.pk)]
        self.assertEqual(positions, sorted(positions))
        self.assertContains(response, f'href="#comment-{first.pk}"')
        self.assertContains(response, 'и все ответы на него (3)')

    def test_pagination_keeps_all_replies_with_their_root_even_if_newer(self):
        Comment.objects.bulk_create([
            Comment(author=self.listener, track=self.track, text=f'New thread {index}') for index in range(29)
        ])
        reply = Comment.objects.create(author=self.artist_user, track=self.track, parent=self.comment, text='Newest reply to old thread')
        nested = Comment.objects.create(author=self.listener, track=self.track, parent=reply, text='Nested on the second page')
        url = reverse('moderation_track_comments', args=[self.track.pk])
        first_page = self.client.get(url)
        self.assertNotContains(first_page, reply.text)
        second_page = self.client.get(url, {'page': 2})
        self.assertEqual(second_page.context['thread_count'], 31)
        self.assertEqual(second_page.context['comment_count'], 33)
        self.assertEqual(len(second_page.context['comment_threads']), 1)
        self.assertCountEqual([item.pk for item in second_page.context['comments']], [self.comment.pk, reply.pk, nested.pk])
        self.assertContains(second_page, self.comment.text)
        self.assertContains(second_page, reply.text)
        self.assertContains(second_page, nested.text)

    def test_hidden_parent_status_propagates_through_all_reply_levels(self):
        reply = Comment.objects.create(author=self.artist_user, track=self.track, parent=self.hidden, text='Reply below hidden root')
        nested = Comment.objects.create(author=self.listener, track=self.track, parent=reply, text='Nested hidden reply')
        response = self.client.get(reverse('moderation_track_comments', args=[self.track.pk]))
        nodes = {comment.pk: comment for comment in response.context['comments']}
        self.assertTrue(nodes[reply.pk].hidden_by_parent)
        self.assertTrue(nodes[nested.pk].hidden_by_parent)
        self.assertFalse(nodes[nested.pk].is_hidden)

    def test_deleting_root_removes_its_branch_and_logs_action(self):
        reply = Comment.objects.create(author=self.artist_user, track=self.track, parent=self.comment, text='Reply to delete')
        nested = Comment.objects.create(author=self.listener, track=self.track, parent=reply, text='Nested to delete')
        target_id = self.comment.pk
        query = f'?artist={self.artist.pk}&release_kind=single&list_page=2&page=1'
        response = self.client.post(reverse('delete_moderated_comment', args=[target_id]) + query)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Comment.objects.filter(pk__in=[target_id, reply.pk, nested.pk]).exists())
        self.assertTrue(Comment.objects.filter(pk=self.hidden.pk).exists())
        self.assertTrue(Comment.objects.filter(track=self.other_track).exists())
        self.assertEqual(urlsplit(response.url).path, reverse('moderation_track_comments', args=[self.track.pk]))
        self.assertEqual(parse_qs(urlsplit(response.url).query)['list_page'], ['2'])
        action = ModerationAction.objects.get(target_type='comment', target_id=target_id, action='deleted')
        self.assertEqual(action.actor, self.moderator)
        self.assertIn('3', action.note)
        self.assertContains(self.client.get(reverse('moderation_dashboard')), 'Удалено')

    def test_deleting_a_reply_preserves_parent_and_sibling(self):
        reply = Comment.objects.create(author=self.artist_user, track=self.track, parent=self.comment, text='Delete this answer')
        nested = Comment.objects.create(author=self.listener, track=self.track, parent=reply, text='Delete descendant')
        sibling = Comment.objects.create(author=self.listener, track=self.track, parent=self.comment, text='Keep sibling')
        self.client.post(reverse('delete_moderated_comment', args=[reply.pk]))
        self.assertFalse(Comment.objects.filter(pk__in=[reply.pk, nested.pk]).exists())
        self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())
        self.assertTrue(Comment.objects.filter(pk=sibling.pk).exists())

    def test_delete_requires_post_permission_and_csrf(self):
        url = reverse('delete_moderated_comment', args=[self.comment.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.moderator)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        self.login()
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())
        self.assertFalse(ModerationAction.objects.filter(action='deleted').exists())

    def test_failed_audit_rolls_back_comment_deletion(self):
        reply = Comment.objects.create(author=self.artist_user, track=self.track, parent=self.comment, text='Keep on failure')
        with patch('pc_store.views.moderation.ModerationAction.objects.create', side_effect=RuntimeError('Audit failed')):
            with self.assertRaisesMessage(RuntimeError, 'Audit failed'):
                self.client.post(reverse('delete_moderated_comment', args=[self.comment.pk]))
        self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())
        self.assertTrue(Comment.objects.filter(pk=reply.pk).exists())

    def test_deleting_last_comment_renders_empty_discussion(self):
        track = self.make_track(title='Temporary discussion')
        comment = Comment.objects.create(author=self.listener, track=track, text='Only comment')
        response = self.client.post(reverse('delete_moderated_comment', args=[comment.pk]) + '?page=2', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'У этой песни пока нет комментариев')
        self.assertEqual(response.context['comment_count'], 0)
        self.assertFalse(response.context['comment_threads'])
        self.assertNotContains(self.client.get(reverse('moderation_comments')), track.title)

    def test_admin_discussion_escapes_comment_and_parent_preview(self):
        self.comment.text = '<script>alert("parent")</script>'
        self.comment.save(update_fields=['text'])
        Comment.objects.create(author=self.artist_user, track=self.track, parent=self.comment, text='<img src=x onerror=alert(1)>')
        response = self.client.get(reverse('moderation_track_comments', args=[self.track.pk]))
        self.assertContains(response, '&lt;script&gt;')
        self.assertContains(response, '&lt;img')
        self.assertNotContains(response, '<script>alert(')
        self.assertNotContains(response, '<img src=x')


class AccountRoleTests(AppTestCase):
    def test_access_role_changes_persist_and_change_permissions(self):
        self.login(self.administrator)
        for role, moderate, manage in [
            ('moderator', True, False), ('administrator', True, True), ('member', False, False),
        ]:
            with self.subTest(role=role):
                response = self.client.post(
                    reverse('moderation_update_user', args=[self.listener.pk]),
                    {'action': 'role', 'role': role},
                )
                self.assertEqual(response.status_code, 302)
                account = get_user_model().objects.get(pk=self.listener.pk)
                self.assertEqual(account.has_perm('pc_store.moderate_content'), moderate)
                self.assertEqual(account.has_perm('pc_store.manage_accounts'), manage)
                self.assertEqual(account.is_staff, moderate)
                self.assertEqual(account.profile.role, 'listener')
                detail = self.client.get(response.url)
                self.assertEqual(detail.context['account_role'], role)
                self.assertContains(detail, 'Уровень доступа сохранён')

    def test_own_role_cannot_be_removed(self):
        self.login(self.administrator)
        response = self.client.post(
            reverse('moderation_update_user', args=[self.administrator.pk]),
            {'action': 'role', 'role': 'member'},
        )
        self.assertEqual(response.status_code, 403)

    def test_moderator_cannot_grant_admin_rights(self):
        self.login(self.moderator)
        response = self.client.post(
            reverse('moderation_update_user', args=[self.listener.pk]),
            {'action': 'role', 'role': 'administrator'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.listener.groups.filter(name='Администраторы').exists())
