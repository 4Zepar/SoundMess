from django.contrib import admin
from .models import Album, Artist, Comment, Donation, Follow, Profile, Track, Wallet

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role']
    list_filter = ['role']

@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ['title', 'owner', 'is_public', 'is_favorite_folder']
    list_filter = ['is_public', 'is_favorite_folder']

@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ['user', 'moderation_status', 'is_premium', 'reviewed_at']
    list_filter = ['moderation_status', 'is_premium']
    search_fields = ['user__username']

@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ['title', 'artist', 'source_provider', 'release_type', 'plays_count', 'is_explicit']
    list_filter = ['genre', 'release_type', 'source_provider', 'is_explicit']
    search_fields = ['title', 'artist__user__username', 'source_id']


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ['follower', 'artist', 'created_at']
    list_filter = ['created_at']
    search_fields = ['follower__username', 'artist__user__username']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['track', 'author', 'timestamp_seconds', 'is_hidden', 'created_at']
    list_filter = ['is_hidden', 'created_at']
    search_fields = ['text', 'track__title', 'author__username']


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance_cents', 'updated_at']
    search_fields = ['user__username']


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ['donor', 'artist', 'amount_cents', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['donor__username', 'artist__user__username', 'idempotency_key']