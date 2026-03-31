from django.contrib import admin
from .models import Artist, Track

@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_premium']

@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ['title', 'artist']
    # Позволяет искать треки по названию или имени артиста
    search_fields = ['title', 'artist__user__username']