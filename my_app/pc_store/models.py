from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class ListeningHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='history')
    track = models.ForeignKey('Track', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp'] 

    def __str__(self):
        return f"{self.user.username} послушал {self.track.title}"


class PlayEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='play_events')
    track = models.ForeignKey('Track', on_delete=models.CASCADE, related_name='play_events')
    playback_token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Засчитано прослушивание: {self.track.title}"


class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance_cents = models.PositiveIntegerField(default=0, verbose_name='Баланс, копейки')
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def balance_usd(self):
        return self.balance_cents / 100

    def __str__(self):
        return f"Кошелёк {self.user.username}"


class Donation(models.Model):
    STATUS_CHOICES = [
        ('succeeded', 'Успешно'),
        ('failed', 'Отклонён'),
        ('refunded', 'Возвращён'),
    ]

    donor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='donations_sent')
    artist = models.ForeignKey('Artist', on_delete=models.CASCADE, related_name='donations_received')
    amount_cents = models.PositiveIntegerField(verbose_name='Сумма, копейки')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='succeeded')
    idempotency_key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def amount_usd(self):
        return self.amount_cents / 100

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Донат {self.donor.username} -> {self.artist.user.username}"
    

class Profile(models.Model):
    ROLE_CHOICES = [
        ('listener', 'Слушатель'),
        ('artist', 'Артист'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE) 
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='listener')
    bio = models.TextField(blank=True, verbose_name="О себе")
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    @property
    def favorite_album(self):
        from .models import Album 
        return Album.objects.filter(owner=self.user, is_favorite_folder=True).first()

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class Album(models.Model):
    title = models.CharField(max_length=200)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='albums')
    tracks = models.ManyToManyField('Track', related_name='contained_in', blank=True)
    is_favorite_folder = models.BooleanField(default=False) 
    is_public = models.BooleanField(default=False, verbose_name="Публичный релиз")
    created_at = models.DateTimeField(auto_now_add=True)
    cover = models.ImageField(
        upload_to='album_covers/', 
        blank=True, 
        null=True, 
        verbose_name="Обложка альбома"
    )

    def __str__(self):
        return self.title
    

class Artist(models.Model):
    MODERATION_STATUS_CHOICES = [
        ('pending', 'На модерации'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонён'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(blank=True, verbose_name="О себе")
    is_premium = models.BooleanField(default=False, verbose_name="Платная подписка")
    moderation_status = models.CharField(
        max_length=10,
        choices=MODERATION_STATUS_CHOICES,
        default='pending',
        verbose_name="Статус модерации",
    )
    moderation_note = models.TextField(blank=True, verbose_name="Комментарий модератора")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата проверки")

    def __str__(self):
        return self.user.username


class Track(models.Model):
    SOURCE_CHOICES = [
        ('local', 'Локальная загрузка'),
        ('jamendo', 'Jamendo'),
        ('fma', 'Free Music Archive'),
    ]

    RELEASE_TYPE_CHOICES = [
        ('single', 'Сингл'),
        ('album', 'Альбом'),
        ('ep', 'EP'),
        ('mixtape', 'Микстейп'),
    ]

    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='tracks')
    title = models.CharField(max_length=200, verbose_name="Название")
    audio_file = models.FileField(upload_to='music/', verbose_name="Файл трека")
    cover = models.ImageField(upload_to='covers/', blank=True, verbose_name="Обложка")
    genre = models.CharField(max_length=50, default='Rock', verbose_name="Жанр")
    plays_count = models.PositiveIntegerField(default=0, verbose_name="Прослушивания")
    release_date = models.DateField(auto_now_add=True, verbose_name="Дата выхода")
    release_year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Год выпуска")
    release_type = models.CharField(
        max_length=10,
        choices=RELEASE_TYPE_CHOICES,
        default='single',
        verbose_name="Тип релиза",
    )
    duration_seconds = models.PositiveIntegerField(null=True, blank=True, verbose_name="Длительность, секунд")
    mood = models.CharField(max_length=50, blank=True, verbose_name="Настроение")
    lyrics = models.TextField(blank=True, verbose_name="Текст песни")
    is_explicit = models.BooleanField(default=False, verbose_name="Без цензуры")
    source_provider = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='local')
    source_id = models.CharField(max_length=200, blank=True)
    license_name = models.CharField(max_length=200, blank=True, verbose_name="Лицензия")
    attribution = models.TextField(blank=True, verbose_name="Атрибуция")
    source_url = models.URLField(blank=True, verbose_name="Источник")
    
    likes = models.ManyToManyField(User, related_name='liked_tracks', blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['source_provider', 'source_id'],
                condition=~models.Q(source_id=''),
                name='unique_external_track_source',
            ),
        ]

    def __str__(self):
        return f"{self.artist.user.username} - {self.title}" 


class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='artist_follows')
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['follower', 'artist'], name='unique_artist_follow'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.follower.username} подписан на {self.artist.user.username}"


class Comment(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='track_comments')
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='comments')
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='replies',
    )
    text = models.TextField(max_length=1000)
    timestamp_seconds = models.PositiveIntegerField(default=0, verbose_name="Таймкод, секунд")
    created_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False, verbose_name="Скрыт модератором")

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Комментарий {self.author.username} к {self.track.title}"


@receiver(post_save, sender=User)
def create_user_assets(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        Wallet.objects.create(user=instance)
        Album.objects.create(
            title="Любимое", 
            owner=instance, 
            is_public=False, 
            is_favorite_folder=True
        )