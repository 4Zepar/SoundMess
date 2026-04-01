from django.db import models
from django.contrib.auth.models import User 


class Artist(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(blank=True, verbose_name="О себе")
    is_premium = models.BooleanField(default=False, verbose_name="Платная подписка")

    def __str__(self):
        return self.user.username


class Track(models.Model):
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='tracks')
    title = models.CharField(max_length=200, verbose_name="Название")
    audio_file = models.FileField(upload_to='music/', verbose_name="Файл трека")
    cover = models.ImageField(upload_to='covers/', blank=True, verbose_name="Обложка")
    
    likes = models.ManyToManyField(User, related_name='liked_tracks', blank=True)

    def __str__(self):
        return f"{self.artist.user.username} - {self.title}"
