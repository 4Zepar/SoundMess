from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class DatabaseIntegrityMigrationTests(TransactionTestCase):
    previous = ('pc_store', '0012_preserve_library_and_roles')
    current = ('pc_store', '0013_database_integrity')

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.previous])
        self.addCleanup(self.restore_schema)
        self.apps = executor.loader.project_state([self.previous]).apps

    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def seed_previous_schema(self):
        User = self.apps.get_model('auth', 'User')
        owner = User.objects.create(username='migration-artist')
        listener = User.objects.create(username='migration-listener')
        artist = self.apps.get_model('pc_store', 'Artist').objects.create(user=owner, moderation_status='approved')
        Track = self.apps.get_model('pc_store', 'Track')
        tracks = [Track.objects.create(artist=artist, title=str(index), audio_file=f'music/{index}.wav') for index in range(3)]
        Album = self.apps.get_model('pc_store', 'Album')
        album = Album.objects.create(owner=owner, title='Existing album', is_public=True)
        links = Album.tracks.through
        # Deliberately differ from Track.Meta ordering.
        for track in tracks:
            links.objects.create(album=album, track=track)
        wallet = self.apps.get_model('pc_store', 'Wallet').objects.create(user=listener, balance_cents=900)
        Ledger = self.apps.get_model('pc_store', 'WalletTransaction')
        positive = Ledger.objects.create(wallet=wallet, amount_cents=1000, balance_after_cents=1000, operation_key='old-topup')
        negative = Ledger.objects.create(wallet=wallet, amount_cents=-100, balance_after_cents=900, operation_key='old-debit')
        donation = self.apps.get_model('pc_store', 'Donation').objects.create(
            donor=listener, artist=artist, amount_cents=100, idempotency_key='old-donation',
        )
        return album, tracks, wallet, positive, negative, donation

    def test_existing_rows_and_link_ids_survive_forward_and_reverse_migration(self):
        album, tracks, wallet, positive, negative, donation = self.seed_previous_schema()
        links = self.apps.get_model('pc_store', 'Album').tracks.through
        before = list(links.objects.order_by('pk').values_list('pk', 'album_id', 'track_id'))
        executor = MigrationExecutor(connection)
        executor.migrate([self.current])
        apps = executor.loader.project_state([self.current]).apps
        AlbumTrack = apps.get_model('pc_store', 'AlbumTrack')
        self.assertEqual(list(AlbumTrack.objects.order_by('pk').values_list('pk', 'album_id', 'track_id')), before)
        self.assertEqual(list(AlbumTrack.objects.values_list('position', flat=True)), [1, 2, 3])
        self.assertEqual(apps.get_model('pc_store', 'Wallet').objects.get(pk=wallet.pk).balance_cents, 900)
        Ledger = apps.get_model('pc_store', 'WalletTransaction')
        self.assertEqual(Ledger.objects.get(pk=positive.pk).type, 'topup')
        self.assertEqual(Ledger.objects.get(pk=negative.pk).type, 'withdrawal')
        self.assertFalse(Ledger.objects.filter(donation__isnull=False).exists())
        self.assertTrue(apps.get_model('pc_store', 'Donation').objects.filter(pk=donation.pk).exists())
        MigrationExecutor(connection).migrate([self.previous])
        self.assertEqual(list(links.objects.order_by('pk').values_list('pk', 'album_id', 'track_id')), before)

    def test_invalid_legacy_amount_does_not_get_silently_removed(self):
        _, _, wallet, _, _, _ = self.seed_previous_schema()
        Ledger = self.apps.get_model('pc_store', 'WalletTransaction')
        invalid = Ledger.objects.create(wallet=wallet, amount_cents=0, balance_after_cents=900, operation_key='invalid')
        with self.assertRaisesMessage(RuntimeError, 'Invalid amounts'):
            MigrationExecutor(connection).migrate([self.current])
        self.assertTrue(Ledger.objects.filter(pk=invalid.pk).exists())
        self.assertEqual(Ledger.objects.count(), 3)
        invalid.delete()


class RemoveModeratorRoleMigrationTests(TransactionTestCase):
    previous = ('pc_store', '0013_database_integrity')
    current = ('pc_store', '0014_remove_moderator_role')

    def test_only_moderator_access_is_removed_from_existing_accounts(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.previous])
        apps = executor.loader.project_state([
            self.previous, ('contenttypes', '0002_remove_content_type_name'),
        ]).apps
        User = apps.get_model('auth', 'User')
        Group = apps.get_model('auth', 'Group')
        Permission = apps.get_model('auth', 'Permission')
        ContentType = apps.get_model('contenttypes', 'ContentType')
        content_type, _ = ContentType.objects.get_or_create(app_label='pc_store', model='moderationaction')
        moderate, _ = Permission.objects.get_or_create(content_type=content_type, codename='moderate_content')
        manage, _ = Permission.objects.get_or_create(content_type=content_type, codename='manage_accounts')
        moderators, _ = Group.objects.get_or_create(name='Модераторы')
        administrators, _ = Group.objects.get_or_create(name='Администраторы')
        moderators.permissions.add(moderate)
        administrators.permissions.add(moderate, manage)

        former = User.objects.create(username='legacy-moderator', is_staff=True)
        former.groups.add(moderators)
        custom = User.objects.create(username='custom-moderator', is_staff=True)
        custom.user_permissions.add(moderate)
        admin = User.objects.create(username='legacy-admin', is_staff=True)
        admin.groups.add(moderators, administrators)

        executor = MigrationExecutor(connection)
        executor.migrate([self.current])
        self.assertFalse(Group.objects.filter(pk=moderators.pk).exists())
        self.assertFalse(Permission.objects.filter(pk=moderate.pk).exists())
        self.assertFalse(User.objects.get(pk=former.pk).is_staff)
        self.assertFalse(User.objects.get(pk=custom.pk).is_staff)
        admin.refresh_from_db()
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.groups.filter(pk=administrators.pk, permissions=manage).exists())
