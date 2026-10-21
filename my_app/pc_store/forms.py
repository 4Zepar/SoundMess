from decimal import Decimal
from math import isfinite
from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone
from mutagen import File as AudioFile, MutagenError

from .constants import GENRES, MOODS, TEMPOS, ReleaseType
from .models import Album, Artist, Profile, Track


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                'class',
                'checkbox' if isinstance(field.widget, forms.CheckboxInput) else 'input'
            )
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault('rows', 5)


def validate_audio_upload(upload):
    if Path(upload.name).suffix.lower() not in {'.mp3', '.wav', '.ogg', '.m4a'}:
        raise ValidationError('Разрешены только MP3, WAV, OGG и M4A.')
    if upload.size > 50 * 1024 * 1024:
        raise ValidationError('Размер аудиофайла не должен превышать 50 МБ.')


def validate_cover_upload(upload):
    if Path(upload.name).suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
        raise ValidationError('Разрешены только JPG, PNG и WebP.')
    if upload.size > 5 * 1024 * 1024:
        raise ValidationError('Размер изображения не должен превышать 5 МБ.')


class RegistrationForm(StyledFormMixin, UserCreationForm):
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES, label='Тип аккаунта')

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('username', 'email', 'role')


class ProfileForm(StyledFormMixin, forms.ModelForm):
    avatar = forms.ImageField(required=False, validators=[validate_cover_upload], label='Аватар')

    class Meta:
        model = Profile
        fields = ['bio', 'avatar']


class ArtistApplicationForm(StyledFormMixin, forms.ModelForm):
    bio = forms.CharField(max_length=2000, label='Расскажите о своей музыке', widget=forms.Textarea)

    class Meta:
        model = Artist
        fields = ['bio']


class TrackForm(StyledFormMixin, forms.ModelForm):
    audio_file = forms.FileField(
        validators=[validate_audio_upload],
        label='Аудиофайл',
        help_text='MP3, WAV, OGG или M4A, до 50 МБ.'
    )
    cover = forms.ImageField(
        required=False,
        validators=[validate_cover_upload],
        label='Обложка',
        help_text='JPG, PNG или WebP, до 5 МБ.'
    )

    class Meta:
        model = Track
        fields = [
            'title',
            'audio_file',
            'cover',
            'genre',
            'mood',
            'tempo',
            'release_year',
            'release_type',
            'lyrics',
            'is_explicit'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['audio_file'].required = not self.instance.pk
        self.fields['release_year'].min_value = 1900
        self.fields['release_year'].max_value = timezone.localdate().year + 1
        self.fields['lyrics'].help_text = 'Необязательное поле. До 30 000 символов.'

    def clean_audio_file(self):
        upload = self.cleaned_data.get('audio_file')
        if not upload or not hasattr(upload, 'content_type'):
            return upload
        try:
            upload.seek(0)
            audio = AudioFile(upload)
            if audio is None or not isfinite(audio.info.length) or not 0 < audio.info.length <= 86400:
                raise ValidationError('Не удалось прочитать аудиофайл. Проверьте его формат.')
            self.instance.duration_seconds = max(1, round(audio.info.length))
        except (MutagenError, OSError, ValueError, EOFError) as error:
            raise ValidationError('Аудиофайл повреждён или его формат не поддерживается.') from error
        finally:
            upload.seek(0)
        return upload


class TrackFilterForm(StyledFormMixin, forms.Form):
    search = forms.CharField(
        required=False,
        max_length=200,
        label='Поиск',
        widget=forms.TextInput(attrs={'placeholder': 'Трек, артист или релиз', 'type': 'search'})
    )
    genre = forms.ChoiceField(required=False, choices=[('', 'Все жанры'), *GENRES], label='Жанр')
    mood = forms.ChoiceField(required=False, choices=[('', 'Любое настроение'), *MOODS], label='Настроение')
    tempo = forms.ChoiceField(required=False, choices=[('', 'Любой темп'), *TEMPOS], label='Темп')
    release_year_from = forms.IntegerField(required=False, min_value=1900, label='Год от')
    release_year_to = forms.IntegerField(required=False, min_value=1900, label='Год до')
    release_type = forms.ChoiceField(
        required=False,
        choices=[('', 'Любой релиз'), *ReleaseType.choices],
        label='Тип релиза'
    )
    duration = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Любая длительность'),
            ('short', 'До 3 минут'),
            ('standard', '3–5 минут'),
            ('long', 'Более 5 минут')
        ],
        label='Длительность'
    )
    has_lyrics = forms.BooleanField(required=False, label='Только с текстом')
    explicit = forms.BooleanField(required=False, label='Без цензуры')
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ('newest', 'Сначала новые'),
            ('popular', 'По прослушиваниям'),
            ('liked', 'По лайкам')
        ],
        label='Сортировка'
    )

    def clean(self):
        data = super().clean()
        start, end = data.get('release_year_from'), data.get('release_year_to')
        if start and end and start > end:
            raise ValidationError('Начальный год не может быть больше конечного.')
        return data


class AlbumForm(StyledFormMixin, forms.ModelForm):
    cover = forms.ImageField(required=False, validators=[validate_cover_upload], label='Обложка')

    class Meta:
        model = Album
        fields = ['title', 'description', 'cover', 'release_type', 'release_year', 'tracks']
        widgets = {'tracks': forms.CheckboxSelectMultiple()}

    def __init__(self, *args, user, public=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.public = public
        self.instance.owner = user
        self.instance.is_public = public
        self.fields['tracks'].queryset = (
            Track.objects.filter(artist__user=user) if public else Track.objects.visible_to(user)
        ).select_related('artist__user')
        self.fields['tracks'].label = 'Треки релиза' if public else 'Добавить треки'
        if not public:
            self.fields.pop('release_type')
            self.fields.pop('release_year')
        else:
            self.fields['release_year'].min_value = 1900
            self.fields['release_year'].max_value = timezone.localdate().year + 1


class PaymentForm(StyledFormMixin, forms.Form):
    amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        max_value=Decimal('100000.00'),
        max_digits=10,
        decimal_places=2,
        label='Сумма, демо USD',
        widget=forms.NumberInput(attrs={'step': '0.01', 'inputmode': 'decimal', 'placeholder': '5.00'})
    )
    token = forms.CharField(widget=forms.HiddenInput)


class BalanceAdjustmentForm(StyledFormMixin, forms.Form):
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('-100000'),
        max_value=Decimal('100000'),
        label='Изменение баланса, демо USD',
        widget=forms.NumberInput(attrs={'step': '0.01', 'placeholder': '+10.00 или -5.00'})
    )
    note = forms.CharField(max_length=200, label='Причина')
    token = forms.CharField(widget=forms.HiddenInput)


class ReviewForm(StyledFormMixin, forms.Form):
    decision = forms.ChoiceField(
        choices=[('approved', 'Одобрить'), ('rejected', 'Отклонить'), ('hidden', 'Скрыть')]
    )
    note = forms.CharField(
        required=False,
        max_length=2000,
        label='Комментарий',
        widget=forms.Textarea(attrs={'rows': 2})
    )

    def clean(self):
        data = super().clean()
        if data.get('decision') in {'rejected', 'hidden'} and not data.get('note', '').strip():
            self.add_error('note', 'Укажите причину решения.')
        return data
