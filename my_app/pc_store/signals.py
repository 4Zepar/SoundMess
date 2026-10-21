from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Album, Profile, Wallet


@receiver(post_save, sender=get_user_model(), dispatch_uid='pc_store.create_user_assets')
def create_user_assets(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        Profile.objects.get_or_create(user=instance)
        Wallet.objects.get_or_create(user=instance)
        Album.objects.get_or_create(owner=instance, is_favorite_folder=True, defaults={'title': 'Любимое'})
