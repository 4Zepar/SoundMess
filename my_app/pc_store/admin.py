from django.contrib import admin
from .models import Album, Artist, Comment, Donation, Follow, ModerationAction, Profile, Track, Wallet, WalletTransaction


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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
    list_display = ['title', 'artist', 'release_type', 'plays_count', 'is_explicit']
    list_filter = ['genre', 'release_type', 'is_explicit']
    search_fields = ['title', 'artist__user__username']


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
class WalletAdmin(ReadOnlyAdmin):
    list_display = ['user', 'balance_cents', 'updated_at']
    search_fields = ['user__username']


@admin.register(Donation)
class DonationAdmin(ReadOnlyAdmin):
    list_display = ['donor', 'artist', 'amount_cents', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['donor__username', 'artist__user__username', 'idempotency_key']


@admin.register(WalletTransaction)
class WalletTransactionAdmin(ReadOnlyAdmin):
    list_display = ['wallet', 'amount_cents', 'balance_after_cents', 'created_at']
    search_fields = ['wallet__user__username', 'operation_key']


@admin.register(ModerationAction)
class ModerationActionAdmin(ReadOnlyAdmin):
    list_display = ['actor', 'target_type', 'target_id', 'action', 'created_at']
    list_filter = ['target_type', 'action']
