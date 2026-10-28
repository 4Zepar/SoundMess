import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Count


def prepare_existing_data(apps, schema_editor):
    alias = schema_editor.connection.alias
    Wallet = apps.get_model('pc_store', 'Wallet')
    Ledger = apps.get_model('pc_store', 'WalletTransaction')
    Donation = apps.get_model('pc_store', 'Donation')
    AlbumTrack = apps.get_model('pc_store', 'AlbumTrack')

    # Financial rows must not be silently discarded or have their amounts rewritten.
    for model, invalid in (
        (Wallet, {'balance_cents__lt': 0}),
        (Ledger, {'amount_cents': 0}),
        (Donation, {'amount_cents__lte': 0}),
    ):
        if model.objects.using(alias).filter(**invalid).exists():
            raise RuntimeError(f'Invalid amounts in {model._meta.db_table}; review these rows before migrating.')

    for model, fields in (
        (Ledger, ('wallet_id', 'operation_key')),
        (Donation, ('donor_id', 'idempotency_key')),
        (AlbumTrack, ('album_id', 'track_id')),
    ):
        objects = model.objects.using(alias)
        duplicates = list(objects.order_by().values(*fields).annotate(total=Count('pk')).filter(total__gt=1))
        for duplicate in duplicates:
            criteria = {field: duplicate[field] for field in fields}
            rows = objects.filter(**criteria).order_by('pk')
            rows.exclude(pk=rows.values_list('pk', flat=True).first()).delete()

    previous_album = None
    position = 0
    for entry in AlbumTrack.objects.using(alias).order_by('album_id', 'pk').iterator():
        if entry.album_id != previous_album:
            previous_album, position = entry.album_id, 0
        position += 1
        AlbumTrack.objects.using(alias).filter(pk=entry.pk).update(position=position)
    Ledger.objects.using(alias).filter(amount_cents__gt=0).update(type='topup')
    Ledger.objects.using(alias).filter(amount_cents__lt=0).update(type='withdrawal')


class Migration(migrations.Migration):
    dependencies = [
        ('pc_store', '0012_preserve_library_and_roles'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Reuse the implicit M2M table rather than dropping and recreating its links.
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.CreateModel(
                name='AlbumTrack',
                fields=[
                    ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                    ('album', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='track_entries', to='pc_store.album')),
                    ('track', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='album_entries', to='pc_store.track')),
                ],
                options={
                    'db_table': 'pc_store_album_tracks', 'ordering': ['position'],
                    'unique_together': {('album', 'track')},
                },
            ),
            migrations.AlterField(
                model_name='album', name='tracks',
                field=models.ManyToManyField(blank=True, related_name='contained_in', through='pc_store.AlbumTrack', to='pc_store.track'),
            ),
        ]),
        migrations.AddField(model_name='albumtrack', name='position', field=models.PositiveIntegerField(null=True)),
        migrations.AddField(
            model_name='wallettransaction', name='donation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='pc_store.donation'),
        ),
        migrations.AddField(
            model_name='wallettransaction', name='type',
            field=models.CharField(choices=[('topup', 'Пополнение'), ('donation_out', 'Донат (списание)'), ('donation_in', 'Донат (начисление)'), ('withdrawal', 'Вывод')], max_length=20, null=True),
        ),
        migrations.RunPython(prepare_existing_data, migrations.RunPython.noop),
        migrations.AlterField(model_name='albumtrack', name='position', field=models.PositiveIntegerField()),
        migrations.AlterUniqueTogether(name='albumtrack', unique_together=set()),
        migrations.AddConstraint(
            model_name='albumtrack',
            constraint=models.UniqueConstraint(fields=('album', 'track'), name='uniq_album_track'),
        ),
        migrations.AddConstraint(
            model_name='albumtrack',
            constraint=models.UniqueConstraint(fields=('album', 'position'), name='uniq_album_track_position'),
        ),
        migrations.AlterField(
            model_name='wallettransaction', name='type',
            field=models.CharField(choices=[('topup', 'Пополнение'), ('donation_out', 'Донат (списание)'), ('donation_in', 'Донат (начисление)'), ('withdrawal', 'Вывод')], max_length=20),
        ),
        migrations.AlterField(model_name='donation', name='idempotency_key', field=models.CharField(max_length=64)),
        migrations.AlterField(model_name='wallettransaction', name='operation_key', field=models.CharField(max_length=100)),
        migrations.AddConstraint(
            model_name='donation', constraint=models.UniqueConstraint(fields=('donor', 'idempotency_key'), name='uniq_donor_idempotency_key'),
        ),
        migrations.AddConstraint(
            model_name='wallettransaction', constraint=models.UniqueConstraint(fields=('wallet', 'operation_key'), name='uniq_wallet_operation_key'),
        ),
        migrations.AddConstraint(
            model_name='wallet', constraint=models.CheckConstraint(condition=models.Q(balance_cents__gte=0), name='wallet_balance_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='donation', constraint=models.CheckConstraint(condition=models.Q(amount_cents__gt=0), name='donation_amount_positive'),
        ),
        migrations.AddConstraint(
            model_name='wallettransaction', constraint=models.CheckConstraint(condition=~models.Q(amount_cents=0), name='wallettx_amount_non_zero'),
        ),
        migrations.AddIndex(model_name='playevent', index=models.Index(fields=['track', 'created_at'], name='playevent_track_created_idx')),
        migrations.AddIndex(model_name='playevent', index=models.Index(fields=['user', 'created_at'], name='playevent_user_created_idx')),
        migrations.AddIndex(model_name='listeninghistory', index=models.Index(fields=['user', '-timestamp'], name='listenhist_user_ts_idx')),
        migrations.AddIndex(model_name='listeninghistory', index=models.Index(fields=['track', 'timestamp'], name='listenhist_track_ts_idx')),
        migrations.AddIndex(model_name='track', index=models.Index(fields=['moderation_status', '-published_at'], name='track_mod_pub_idx')),
    ]
