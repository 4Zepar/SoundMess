from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, re_path
from django.views.static import serve

from pc_store.views import accounts, artists, catalog, errors, library, moderation, playback, social, wallet

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', catalog.track_list, name='home'),
    path('releases/', catalog.release_list, name='release_list'),
    path('register/', accounts.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', accounts.logout_view, name='logout'),
    path('profile/', library.profile_view, name='profile'),
    path('profile/edit/', accounts.profile_edit, name='profile_edit'),
    path('wallet/top-up/', wallet.wallet_top_up, name='wallet_top_up'),
    path('artists/', catalog.artist_list, name='artist_list'),
    path('artist/<int:artist_id>/', catalog.artist_detail, name='artist_detail'),
    path('artist/<int:artist_id>/follow/', social.toggle_follow, name='toggle_follow'),
    path('feed/', social.feed_view, name='feed'),
    path('artist/application/', artists.artist_application, name='artist_application'),
    path('artist/dashboard/', artists.artist_dashboard, name='artist_dashboard'),
    path('artist/track/<int:track_id>/edit/', artists.track_editor, name='edit_track'),
    path('upload/', artists.track_editor, name='upload_track'),
    path('support/<int:artist_id>/', wallet.support_artist, name='support_artist'),
    path('favorite/toggle/<int:track_id>/', social.toggle_like, name='toggle_favorite'),
    path('like/toggle/<int:track_id>/', social.toggle_like, name='toggle_like'),
    path('track/<int:track_id>/comments/', social.comments, name='add_comment'),
    path('track/<int:track_id>/comments/page/', catalog.comment_page, name='comment_page'),
    path('track/<int:track_id>/play/', playback.record_play, name='record_play'),
    path('track/<int:track_id>/audio/', playback.track_audio, name='track_audio'),
    path('album/<int:album_id>/', catalog.album_detail, name='album_detail'),
    path('album/<int:album_id>/favorite/', library.add_album_to_favorites, name='add_album_to_favorites'),
    path('album/create/', library.album_editor, name='create_album'),
    path('album/<int:album_id>/edit/', library.album_editor, name='edit_album'),
    path('release/create/', library.album_editor, {'public': True}, name='create_release'),
    path('release/<int:album_id>/edit/', library.album_editor, {'public': True}, name='edit_release'),
    path('album/<int:album_id>/delete/', library.delete_album, name='delete_album'),
    path('album/add-track/', library.add_track_to_album, name='add_track_to_album'),
    path('album/remove-track/', library.remove_track_from_album, name='remove_track_from_album'),
    path('history/add/<int:track_id>/', social.add_to_history, name='add_to_history'),
    path('moderation/', moderation.dashboard, name='moderation_dashboard'),
    path('moderation/users/', moderation.users, name='moderation_users'),
    path('moderation/users/<int:user_id>/', moderation.user_detail, name='moderation_user_detail'),
    path(
        'moderation/users/<int:user_id>/balance/',
        moderation.adjust_user_balance,
        name='adjust_user_balance'
    ),
    path('moderation/users/<int:user_id>/update/', moderation.update_user, name='moderation_update_user'),
    path('moderation/applications/', moderation.applications, name='moderation_applications'),
    path(
        'moderation/applications/<int:artist_id>/review/',
        moderation.review_application,
        name='review_artist_application'
    ),
    path('moderation/tracks/', moderation.content_queue, {'kind': 'track'}, name='moderation_tracks'),
    path('moderation/albums/', moderation.content_queue, {'kind': 'album'}, name='moderation_albums'),
    path(
        'moderation/tracks/<int:object_id>/review/',
        moderation.review_material,
        {'kind': 'track'},
        name='review_track'
    ),
    path(
        'moderation/albums/<int:object_id>/review/',
        moderation.review_material,
        {'kind': 'album'},
        name='review_album'
    ),
    path('moderation/comments/', moderation.comments, name='moderation_comments'),
    path(
        'moderation/comments/<int:comment_id>/toggle/',
        moderation.comment_visibility,
        name='toggle_comment_visibility'
    ),
]

if settings.DEBUG:
    urlpatterns += [
        re_path(
            r'^media/(?P<path>(?:avatars|covers|album_covers)/[^/]+)$',
            serve,
            {'document_root': settings.MEDIA_ROOT}
        ),
    ]

handler403 = errors.forbidden
handler404 = errors.not_found
handler500 = errors.server_error
