from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# 1. Профиль — расширяет стандартного Юзера
class Profile(models.Model):
    ROLE_CHOICES = [
        ('listener', 'Слушатель'),
        ('artist', 'Артист'),
    ]
    # ТУТ БЫЛА ОШИБКА: заменяем on_submit на on_delete
    user = models.OneToOneField(User, on_delete=models.CASCADE) 
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='listener')
    bio = models.TextField(blank=True, verbose_name="О себе")
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

# 2. Альбомы (и публичные, и локальные плейлисты)
class Album(models.Model):
    title = models.CharField(max_length=200)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='albums')
    tracks = models.ManyToManyField('Track', related_name='contained_in', blank=True)
    is_public = models.BooleanField(default=False) 
    is_favorite_folder = models.BooleanField(default=False) 
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
    
# 3. Артист (Специфические данные для авторов)
class Artist(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(blank=True, verbose_name="О себе")
    is_premium = models.BooleanField(default=False, verbose_name="Платная подписка")

    def __str__(self):
        return self.user.username

# 4. Треки
class Track(models.Model):
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='tracks')
    title = models.CharField(max_length=200, verbose_name="Название")
    audio_file = models.FileField(upload_to='music/', verbose_name="Файл трека")
    cover = models.ImageField(upload_to='covers/', blank=True, verbose_name="Обложка")
    genre = models.CharField(max_length=50, default='Rock', verbose_name="Жанр")
    plays = models.PositiveIntegerField(default=0, verbose_name="Прослушивания")
    # Добавили дату выхода, как ты хотел
    release_date = models.DateField(auto_now_add=True, verbose_name="Дата выхода") 
    
    likes = models.ManyToManyField(User, related_name='liked_tracks', blank=True)

    def __str__(self):
        return f"{self.artist.user.username} - {self.title}"

# Сигналы для автоматизации
@receiver(post_save, sender=User)
def create_user_assets(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        Album.objects.create(
            title="Любимое", 
            owner=instance, 
            is_public=False, 
            is_favorite_folder=True
        )