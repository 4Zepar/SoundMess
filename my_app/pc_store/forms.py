from django import forms
from django.contrib.auth.models import User
from .models import Profile, Artist, Track, Album  

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
    

class TrackUploadForm(forms.ModelForm):
    class Meta:
        model = Track
        fields = ['title', 'audio_file', 'cover']


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
            
            # Если такой альбом есть, берем его треки, иначе — пустой список
            favorite_tracks_ids = fav_album.tracks.values_list('id', flat=True) if fav_album else []

            # 3. ФИНАЛЬНЫЙ ФИЛЬТР
            # Показываем треки, где юзер — автор (через Artist) 
            # ИЛИ треки, которые лежат в его папке "Любимое"
            self.fields['tracks'].queryset = Track.objects.filter(
                Q(artist__user=user) | Q(id__in=favorite_tracks_ids)
            ).distinct()