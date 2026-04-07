from django import forms
from django.contrib.auth.models import User
from .models import Profile, Artist

class RegistrationForm(forms.ModelForm):
    # Добавляем выбор роли прямо в форму регистрации
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES, label="Кто вы?")
    password = forms.CharField(widget=forms.PasswordInput, label="Пароль")
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Подтвердите пароль")

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def clean(self):
        # Проверка совпадения паролей
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("password_confirm"):
            raise forms.ValidationError("Пароли не совпадают!")
        return cleaned_data