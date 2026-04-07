from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from .models import Track, Artist, Profile
from .forms import RegistrationForm

# 1. Главная страница (тот самый track_list, который потерялся)
def track_list(request):
    tracks = Track.objects.all()
    # Передаем список треков в шаблон index.html
    return render(request, 'index.html', {'tracks': tracks})

# 2. Логика регистрации
def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            # Создаем пользователя, но не сохраняем в базу сразу (чтобы поставить пароль)
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            
            # Обновляем роль в профиле (профиль создается автоматически сигналом)
            role = form.cleaned_data.get('role')
            profile = user.profile
            profile.role = role
            profile.save()

            # Если юзер выбрал "Артист" — создаем ему запись в таблице Artist
            if role == 'artist':
                Artist.objects.create(user=user)
            
            # Сразу логиним пользователя после регистрации
            login(request, user)
            return redirect('home')
    else:
        form = RegistrationForm()
    return render(request, 'register.html', {'form': form})

# 3. Логика выхода
def logout_view(request):
    logout(request)
    return redirect('home')