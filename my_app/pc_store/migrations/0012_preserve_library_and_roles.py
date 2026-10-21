from datetime import datetime, time, timezone

from django.db import migrations


def preserve_data(apps, schema_editor):
    Track = apps.get_model('pc_store', 'Track')
    Album = apps.get_model('pc_store', 'Album')
    Artist = apps.get_model('pc_store', 'Artist')
    Wallet = apps.get_model('pc_store', 'Wallet')
    Ledger = apps.get_model('pc_store', 'WalletTransaction')
    approved_users = set(Artist.objects.filter(moderation_status='approved').values_list('user_id', flat=True))
    approved_artists = set(Artist.objects.filter(moderation_status='approved').values_list('pk', flat=True))
    genres = {'rock': 'rock', 'рок': 'rock', 'hip-hop': 'hiphop', 'hip hop': 'hiphop', 'хип-хоп': 'hiphop', 'phonk': 'phonk', 'фонк': 'phonk', 'indie': 'indie', 'инди': 'indie', 'electronic': 'electronic', 'электроника': 'electronic', 'pop': 'pop', 'jazz': 'jazz', 'classical': 'classical'}
    for track in Track.objects.iterator():
        published = datetime.combine(track.release_date, time.min, tzinfo=timezone.utc)
        Track.objects.filter(pk=track.pk).update(
            moderation_status='approved' if track.artist_id in approved_artists else 'pending',
            published_at=published if track.artist_id in approved_artists else None,
            created_at=published,
            genre=genres.get(track.genre.lower(), 'other'),
        )
    for album in Album.objects.filter(is_public=True).iterator():
        valid = album.owner_id in approved_users and album.tracks.exists() and not album.tracks.exclude(artist__user_id=album.owner_id, moderation_status='approved').exists()
        Album.objects.filter(pk=album.pk).update(moderation_status='approved' if valid else 'pending', published_at=album.created_at if valid else None)
    likes = Track.likes.through
    for folder in Album.objects.filter(is_favorite_folder=True).iterator():
        for track_id in folder.tracks.values_list('pk', flat=True):
            likes.objects.get_or_create(track_id=track_id, user_id=folder.owner_id)
        folder.tracks.clear()
    for wallet in Wallet.objects.exclude(balance_cents=0).iterator():
        Ledger.objects.create(wallet_id=wallet.pk, amount_cents=wallet.balance_cents, balance_after_cents=wallet.balance_cents, description='Начальный баланс', operation_key=f'opening:{wallet.pk}')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model('auth', 'User')
    content_type, _ = ContentType.objects.get_or_create(app_label='pc_store', model='moderationaction')
    moderate, _ = Permission.objects.get_or_create(content_type=content_type, codename='moderate_content', defaults={'name': 'Модерация контента и заявок'})
    manage, _ = Permission.objects.get_or_create(content_type=content_type, codename='manage_accounts', defaults={'name': 'Управление пользователями и балансами'})
    moderators, _ = Group.objects.get_or_create(name='Модераторы')
    moderators.permissions.add(moderate)
    administrators, _ = Group.objects.get_or_create(name='Администраторы')
    administrators.permissions.add(moderate, manage)
    for user in User.objects.filter(is_staff=True).iterator():
        user.groups.add(administrators)


class Migration(migrations.Migration):
    dependencies = [('pc_store', '0011_publication_and_wallet')]
    operations = [migrations.RunPython(preserve_data, migrations.RunPython.noop)]
