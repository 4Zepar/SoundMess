from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.urls import reverse

from pc_store.models import Album, AlbumTrack, Donation, Follow, PlayEvent, Track, Wallet, WalletTransaction
from pc_store.services.albums import add_album_track, set_album_tracks
from pc_store.services.payments import adjust_balance, donate
from .base import AppTestCase


class DatabaseIntegrityTests(AppTestCase):
    def assert_integrity_error(self, operation):
        with self.assertRaises(IntegrityError), transaction.atomic():
            operation()

    def test_like_saved_release_follow_and_wallet_pairs_are_unique(self):
        album = self.make_album()
        likes = Track.likes.through
        saves = Album.saved_by.through
        likes.objects.create(track=self.track, user=self.listener)
        saves.objects.create(album=album, user=self.listener)
        Follow.objects.create(artist=self.artist, follower=self.listener)
        for operation in (
            lambda: likes.objects.create(track=self.track, user=self.listener),
            lambda: saves.objects.create(album=album, user=self.listener),
            lambda: Follow.objects.create(artist=self.artist, follower=self.listener),
            lambda: Wallet.objects.create(user=self.listener),
        ):
            self.assert_integrity_error(operation)

    def test_database_rejects_invalid_financial_amounts(self):
        wallet = self.listener.wallet
        for operation in (
            lambda: Wallet.objects.filter(pk=wallet.pk).update(balance_cents=-1),
            lambda: Donation.objects.create(donor=self.listener, artist=self.artist, amount_cents=0, idempotency_key='zero'),
            lambda: WalletTransaction.objects.create(
                wallet=wallet, amount_cents=0, balance_after_cents=0, operation_key='zero',
                type=WalletTransaction.Type.TOPUP, description='Invalid amount',
            ),
        ):
            self.assert_integrity_error(operation)

    def test_wallet_operation_key_is_unique_within_each_wallet(self):
        entry = adjust_balance(user=self.listener, amount_cents=100, operation_key='shared', description='Topup')
        other = adjust_balance(user=self.artist_user, amount_cents=200, operation_key='shared', description='Topup')
        self.assertNotEqual(entry.pk, other.pk)
        self.assert_integrity_error(lambda: WalletTransaction.objects.create(
            wallet=entry.wallet, amount_cents=100, balance_after_cents=200, operation_key='shared',
            type=WalletTransaction.Type.TOPUP, description='Duplicate',
        ))

    def test_donation_key_is_unique_within_each_donor(self):
        first = Donation.objects.create(donor=self.listener, artist=self.artist, amount_cents=10, idempotency_key='shared')
        Donation.objects.create(donor=self.moderator, artist=self.artist, amount_cents=10, idempotency_key='shared')
        self.assert_integrity_error(lambda: Donation.objects.create(
            donor=first.donor, artist=self.artist, amount_cents=10, idempotency_key='shared',
        ))

    def test_self_follow_is_rejected_by_model_and_endpoint(self):
        with self.assertRaises(ValidationError):
            Follow(artist=self.artist, follower=self.artist_user).full_clean()
        self.login(self.artist_user)
        response = self.client.post(
            reverse('toggle_follow', args=[self.artist.pk]), '{"following":true}', content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Follow.objects.filter(artist=self.artist, follower=self.artist_user).exists())

    def test_donation_with_ledger_entries_is_protected_from_deletion(self):
        adjust_balance(user=self.listener, amount_cents=100, operation_key='start', description='Topup')
        donation = donate(donor=self.listener, artist=self.artist, amount_cents=10, operation_key='protected')
        with self.assertRaises(ProtectedError):
            donation.delete()
        self.assertEqual(donation.transactions.count(), 2)

    def test_playback_token_stays_unique(self):
        PlayEvent.objects.create(track=self.track, playback_token='once')
        self.assert_integrity_error(lambda: PlayEvent.objects.create(track=self.track, playback_token='once'))

    def test_requested_indexes_exist(self):
        expected = {
            'pc_store_playevent': {'playevent_track_created_idx', 'playevent_user_created_idx'},
            'pc_store_listeninghistory': {'listenhist_user_ts_idx', 'listenhist_track_ts_idx'},
            'pc_store_track': {'track_mod_pub_idx'},
        }
        with connection.cursor() as cursor:
            for table, names in expected.items():
                constraints = connection.introspection.get_constraints(cursor, table)
                self.assertTrue(names.issubset(constraints), table)


class AlbumOrderTests(AppTestCase):
    def test_pair_and_position_are_unique_within_an_album(self):
        album = self.make_album()
        other = self.make_track()
        for track, position in ((self.track, 2), (other, 1)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                AlbumTrack.objects.create(album=album, track=track, position=position)
        another = self.make_album(tracks=[other])
        self.assertEqual(another.track_entries.get().position, 1)

    def test_album_detail_and_player_queue_follow_stored_positions(self):
        newer = self.make_track(title='Newest track')
        album = self.make_album(tracks=[self.track, newer])
        # The same track can have a different position in another album.
        self.make_album(tracks=[newer, self.track])
        response = self.client.get(album.get_absolute_url())
        self.assertEqual(list(response.context['tracks']), [self.track, newer])
        self.assertEqual(list(album.track_entries.values_list('position', flat=True)), [1, 2])

    def test_adding_and_removing_tracks_keeps_existing_order(self):
        second = self.make_track()
        third = self.make_track()
        album = self.make_album(tracks=[self.track, second])
        self.assertFalse(add_album_track(album, self.track))
        self.assertTrue(add_album_track(album, third))
        self.assertEqual(list(album.track_entries.values_list('track_id', flat=True)), [self.track.pk, second.pk, third.pk])
        set_album_tracks(album, [third, second])
        self.assertEqual(list(album.track_entries.values_list('track_id', flat=True)), [second.pk, third.pk])

    def test_playlist_form_and_add_remove_endpoints_preserve_positions(self):
        self.login()
        second = self.make_track()
        response = self.client.post(reverse('create_album'), {'title': 'Ordered playlist', 'tracks': [self.track.pk]})
        self.assertEqual(response.status_code, 302)
        album = Album.objects.get(owner=self.listener, title='Ordered playlist')
        for _ in range(2):
            response = self.client.post(
                reverse('add_track_to_album'),
                data={'album_id': album.pk, 'track_id': second.pk}, content_type='application/json',
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(list(album.track_entries.values_list('position', flat=True)), [1, 2])
        self.client.post(reverse('remove_track_from_album'), data={
            'album_id': album.pk, 'track_id': self.track.pk,
        }, content_type='application/json')
        self.assertEqual(list(album.track_entries.values_list('track_id', flat=True)), [second.pk])
