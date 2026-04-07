from django.contrib import admin
from .models import Artist, Track, Profile, Album  # Добавь Profile и Album в импорт

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
    list_display = ['user', 'is_premium']

@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ['title', 'artist']
    search_fields = ['title', 'artist__user__username']