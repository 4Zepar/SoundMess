from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from .models import Profile, Artist, Track, Album  


def validate_audio_upload(upload):
    allowed_extensions = {'.mp3', '.wav', '.ogg', '.m4a'}
    extension = upload.name.lower().rsplit('.', 1)[-1] if '.' in upload.name else ''
    if f'.{extension}' not in allowed_extensions:
        raise forms.ValidationError('Разрешены только MP3, WAV, OGG и M4A.')
    if upload.size > 50 * 1024 * 1024:
        raise forms.ValidationError('Размер аудиофайла не должен превышать 50 МБ.')


def validate_cover_upload(upload):
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    extension = upload.name.lower().rsplit('.', 1)[-1] if '.' in upload.name else ''
    if f'.{extension}' not in allowed_extensions:
        raise forms.ValidationError('Разрешены только JPG, PNG и WebP.')
    if upload.size > 5 * 1024 * 1024:
        raise forms.ValidationError('Размер обложки не должен превышать 5 МБ.')

class RegistrationForm(forms.ModelForm):
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES, label="Кто вы?")
    password = forms.CharField(widget=forms.PasswordInput, label="Пароль")
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Подтвердите пароль")

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("password_confirm"):
            raise forms.ValidationError("Пароли не совпадают!")
        return cleaned_data


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['bio', 'avatar']
        widgets = {'bio': forms.Textarea(attrs={'rows': 4})}
    

class TrackUploadForm(forms.ModelForm):
    audio_file = forms.FileField(validators=[validate_audio_upload])
    cover = forms.ImageField(required=False, validators=[validate_cover_upload])

    class Meta:
        model = Track
        fields = [
            'title', 'audio_file', 'cover', 'genre', 'release_year',
            'release_type', 'duration_seconds', 'mood', 'lyrics', 'is_explicit',
        ]


class TrackMetadataForm(forms.ModelForm):
    cover = forms.ImageField(required=False, validators=[validate_cover_upload])

    class Meta:
        model = Track
        fields = [
            'title', 'cover', 'genre', 'release_year', 'release_type',
            'duration_seconds', 'mood', 'lyrics', 'is_explicit',
        ]


class TrackFilterForm(forms.Form):
    search = forms.CharField(required=False, label='Поиск')
    genre = forms.CharField(required=False, label='Жанр')
    mood = forms.CharField(required=False, label='Настроение')
    release_year_from = forms.IntegerField(required=False, min_value=1900, label='Год от')
    release_year_to = forms.IntegerField(required=False, min_value=1900, label='Год до')
    release_type = forms.ChoiceField(
        required=False,
        choices=[('', 'Любой тип')] + Track.RELEASE_TYPE_CHOICES,
        label='Тип релиза',
    )
    duration = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Любая длительность'),
            ('short', 'Синглы до 3 минут'),
            ('standard', 'Стандарт 3-5 минут'),
            ('long', 'Длинные более 5 минут'),
        ],
        label='Длительность',
    )
    has_lyrics = forms.BooleanField(required=False, label='Только с текстом')
    explicit = forms.BooleanField(required=False, label='Только без цензуры')
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ('newest', 'Сначала новые'),
            ('popular', 'По популярности'),
            ('liked', 'По лайкам'),
        ],
        initial='newest',
        label='Сортировка',
    )


from django.db.models import Q

class AlbumForm(forms.ModelForm):
    class Meta:
        model = Album
        fields = ['title', 'cover', 'is_public', 'tracks'] 
        widgets = {
            'tracks': forms.CheckboxSelectMultiple(),
            'cover': forms.FileInput(attrs={'class': 'file-input-custom'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            if user.profile.role != 'artist':
                self.fields['is_public'].widget = forms.HiddenInput()

            fav_album = Album.objects.filter(owner=user, is_favorite_folder=True).first()
            
            favorite_tracks_ids = fav_album.tracks.values_list('id', flat=True) if fav_album else []

            self.fields['tracks'].queryset = Track.objects.filter(
                Q(artist__user=user) | Q(id__in=favorite_tracks_ids)
            ).distinct()


class DonationForm(forms.Form):
    amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        max_value=Decimal('100000.00'),
        max_digits=10,
        decimal_places=2,
        label='Сумма',
        widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': 'Например, 5.00'}),
    )


class WalletTopUpForm(forms.Form):
    amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        max_value=Decimal('100000.00'),
        max_digits=10,
        decimal_places=2,
        label='Сумма пополнения',
        widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': 'Например, 100.00'}),
    )