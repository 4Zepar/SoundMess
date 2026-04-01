from django.contrib import admin
from django.urls import path
from django.conf import settings 
from django.conf.urls.static import static 
from pc_store.views import track_list

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', track_list, name='home'),
]

# Именно этот кусок кода заставляет Django отдавать музыку в браузер
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)