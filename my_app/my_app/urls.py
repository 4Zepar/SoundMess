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
    path('favorite/toggle/<int:track_id>/', views.toggle_favorite, name='toggle_favorite'),
    path('album/<int:album_id>/', views.album_detail, name='album_detail'),
    path('upload/', views.upload_track, name='upload_track'),
    path('album/create/', views.create_album, name='create_album'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)