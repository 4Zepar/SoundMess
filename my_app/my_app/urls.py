from django.contrib import admin
from django.urls import path
from django.conf import settings 
from django.conf.urls.static import static 
from django.contrib.auth import views as auth_views # Стандартные вьюхи для входа
from pc_store.views import track_list, register_view, logout_view # Наши вьюхи

urlpatterns = [
    # Панель администратора
    path('admin/', admin.site.urls),
    
    # Главная страница со списком треков
    path('', track_list, name='home'),
    
    # Регистрация (наша кастомная функция)
    path('register/', register_view, name='register'),
    
    # Вход (используем готовый класс от Django, но указываем наш шаблон)
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    
    # Выход (наша функция, чтобы сразу перенаправлять на главную)
    path('logout/', logout_view, name='logout'),
]

# Обслуживание медиа-файлов (музыка, обложки) в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)