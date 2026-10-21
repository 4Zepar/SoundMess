from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .constants import GENRES, MOODS, TEMPOS, PublicationStatus, ReleaseType


class ContentQuerySet(models.QuerySet):
    def published(self):
        filters = {'moderation_status': PublicationStatus.APPROVED}
        if self.model._meta.model_name == 'track':
            filters.update(artist__moderation_status='approved', artist__user__is_active=True)
        else:
            filters.update(is_public=True, owner__artist__moderation_status='approved', owner__is_active=True)
        query = self.filter(**filters)
        if self.model._meta.model_name == 'album':
            query = query.filter(tracks__isnull=False).exclude(
                tracks__in=Track.objects.exclude(moderation_status=PublicationStatus.APPROVED)
            ).distinct()
        return query

    def visible_to(self, user):
        from .permissions import can_moderate

        if can_moderate(user):
            return self
        public = Q(pk__in=self.published().values('pk'))
        if user.is_authenticated and user.is_active:
            owner = 'artist__user' if self.model._meta.model_name == 'track' else 'owner'
            return self.filter(public | Q(**{owner: user}))
        return self.filter(public)


class ModeratedContent(models.Model):
    moderation_status = models.CharField(
        max_length=10,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
        db_index=True
    )
    moderation_note = models.TextField(blank=True, max_length=2000)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = ContentQuerySet.as_manager()

    class Meta:
        abstract = True


class Profile(models.Model):
    ROLE_CHOICES = [('listener', 'Слушатель'), ('artist', 'Артист')]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='listener')
    bio = models.TextField(blank=True, verbose_name='О себе', max_length=2000)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    @property
    def favorite_album(self):
        return self.user.albums.filter(is_favorite_folder=True).first()

    def __str__(self):
        return str(self.user)


class Artist(models.Model):
    MODERATION_STATUS_CHOICES = [
        ('pending', 'На проверке'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонён')
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    bio = models.TextField(blank=True, max_length=2000, verbose_name='Об артисте')
    is_premium = models.BooleanField(default=False)
    moderation_status = models.CharField(
        max_length=10,
        choices=MODERATION_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    moderation_note = models.TextField(blank=True, max_length=2000)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return str(self.user)

    def get_absolute_url(self):
        return reverse('artist_detail', args=[self.pk])


class Track(ModeratedContent):
    RELEASE_TYPE_CHOICES = ReleaseType.choices
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='tracks')
    title = models.CharField(max_length=200, verbose_name='Название')
    audio_file = models.FileField(upload_to='music/', verbose_name='Аудиофайл')
    cover = models.ImageField(upload_to='covers/', blank=True, verbose_name='Обложка')
    genre = models.CharField(max_length=50, choices=GENRES, default='rock', verbose_name='Жанр')
    plays_count = models.PositiveIntegerField(default=0)
    release_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(default=timezone.now)
    release_year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Год выпуска')
    release_type = models.CharField(
        max_length=10,
        choices=ReleaseType.choices,
        default=ReleaseType.SINGLE,
        verbose_name='Тип релиза'
    )
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    mood = models.CharField(max_length=50, choices=MOODS, blank=True, verbose_name='Настроение')
    tempo = models.CharField(max_length=10, choices=TEMPOS, blank=True, verbose_name='Темп')
    lyrics = models.TextField(blank=True, max_length=30000, verbose_name='Текст песни')
    is_explicit = models.BooleanField(default=False, verbose_name='Содержит ненормативную лексику')
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='liked_tracks', blank=True)

    class Meta:
        ordering = ['-published_at', '-pk']

    def __str__(self):
        return f'{self.artist} — {self.title}'

    def get_absolute_url(self):
        return reverse('comment_page', args=[self.pk])

    @property
    def audio_url(self):
        if not self.audio_file or not self.audio_file.storage.exists(self.audio_file.name):
            return ''
        return reverse('track_audio', args=[self.pk])


class Album(ModeratedContent):
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, max_length=2000, verbose_name='Описание')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='albums')
    tracks = models.ManyToManyField(Track, related_name='contained_in', blank=True)
    is_favorite_folder = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False, verbose_name='Публичный релиз')
    release_type = models.CharField(
        max_length=10,
        choices=ReleaseType.choices,
        default=ReleaseType.ALBUM,
        verbose_name='Тип релиза'
    )
    release_year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Год выпуска')
    created_at = models.DateTimeField(auto_now_add=True)
    cover = models.ImageField(upload_to='album_covers/', blank=True, null=True, verbose_name='Обложка')
    saved_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='saved_albums', blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['owner'],
                condition=Q(is_favorite_folder=True),
                name='one_favorite_folder_per_user'
            )
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('album_detail', args=[self.pk])


class Follow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='artist_follows'
    )
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['follower', 'artist'], name='unique_artist_follow')]


class Comment(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='track_comments'
    )
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='comments')
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='replies'
    )
    text = models.TextField(max_length=1000)
    timestamp_seconds = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at', 'pk']


class ListeningHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='history')
    track = models.ForeignKey(Track, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp', '-pk']


class PlayEvent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='play_events'
    )
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='play_events')
    playback_token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']


class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    balance_cents = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def balance_usd(self):
        return Decimal(self.balance_cents) / 100


class Donation(models.Model):
    STATUS_CHOICES = [('succeeded', 'Успешно'), ('failed', 'Отклонён'), ('refunded', 'Возвращён')]
    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='donations_sent'
    )
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='donations_received')
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='succeeded')
    idempotency_key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def amount_usd(self):
        return Decimal(self.amount_cents) / 100

    class Meta:
        ordering = ['-created_at', '-pk']


class WalletTransaction(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    amount_cents = models.IntegerField()
    balance_after_cents = models.PositiveIntegerField()
    description = models.CharField(max_length=200)
    operation_key = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    @property
    def amount_usd(self):
        return Decimal(self.amount_cents) / 100

    @property
    def balance_after_usd(self):
        return Decimal(self.balance_after_cents) / 100


class ModerationAction(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    target_type = models.CharField(max_length=30)
    target_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=30)
    note = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        permissions = [
            ('moderate_content', 'Модерация контента и заявок'),
            ('manage_accounts', 'Управление пользователями и балансами')
        ]
