from django.contrib import admin
from django.urls import path
from django.conf import settings 
from django.conf.urls.static import static 
from django.contrib.auth import views as auth_views
from pc_store.views import track_list, register_view, logout_view 
from pc_store import views 

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', track_list, name='home'),
    path('register/', register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('wallet/top-up/', views.wallet_top_up, name='wallet_top_up'),
    path('artists/', views.artist_list, name='artist_list'),
    path('artist/<int:artist_id>/', views.artist_detail, name='artist_detail'),
    path('artist/<int:artist_id>/follow/', views.toggle_follow, name='toggle_follow'),
    path('feed/', views.feed_view, name='feed'),
    path('artist/dashboard/', views.artist_dashboard, name='artist_dashboard'),
    path('artist/track/<int:track_id>/edit/', views.edit_track, name='edit_track'),
    path('support/<int:artist_id>/', views.support_artist, name='support_artist'),
    path('moderation/', views.moderation_dashboard, name='moderation_dashboard'),
    path('moderation/users/', views.moderation_users, name='moderation_users'),
    path('moderation/users/<int:user_id>/', views.moderation_user_detail, name='moderation_user_detail'),
    path('moderation/users/<int:user_id>/balance/', views.adjust_user_balance, name='adjust_user_balance'),
    path('moderation/tracks/<int:track_id>/delete/', views.delete_moderated_track, name='delete_moderated_track'),
    path('moderation/albums/<int:album_id>/delete/', views.delete_moderated_album, name='delete_moderated_album'),
    path('moderation/comments/<int:comment_id>/delete/', views.delete_moderated_comment, name='delete_moderated_comment'),
    path('moderation/applications/', views.moderation_applications, name='moderation_applications'),
    path('moderation/applications/<int:artist_id>/review/', views.review_artist_application, name='review_artist_application'),
    path('moderation/comments/', views.moderation_comments, name='moderation_comments'),
    path('moderation/comments/<int:comment_id>/toggle/', views.toggle_comment_visibility, name='toggle_comment_visibility'),
    path('favorite/toggle/<int:track_id>/', views.toggle_favorite, name='toggle_favorite'),
    path('like/toggle/<int:track_id>/', views.toggle_like, name='toggle_like'),
    path('track/<int:track_id>/comments/', views.add_comment, name='add_comment'),
    path('track/<int:track_id>/comments/page/', views.comment_page, name='comment_page'),
    path('track/<int:track_id>/play/', views.record_play, name='record_play'),
    path('album/<int:album_id>/', views.album_detail, name='album_detail'),
    path('album/<int:album_id>/favorite/', views.add_album_to_favorites, name='add_album_to_favorites'),
    path('upload/', views.upload_track, name='upload_track'),
    path('album/create/', views.create_album, name='create_album'),
    path('album/<int:album_id>/delete/', views.delete_album, name='delete_album'),
    path('album/add-track/', views.add_track_to_album, name='add_track_to_album'),
    path('album/remove-track/', views.remove_track_from_album, name='remove_track_from_album'),
    path('history/add/<int:track_id>/', views.add_to_history, name='add_to_history'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)