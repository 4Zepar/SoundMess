from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from .models import Track, Artist, Profile, ListeningHistory, Album
from .forms import RegistrationForm, TrackUploadForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404


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


@login_required 
def profile_view(request):
    # Получаем профиль текущего юзера
    profile = request.user.profile
    # Все альбомы пользователя (и личные, и публичные)
    my_albums = Album.objects.filter(owner=request.user)
    # История: берем последние 10 записей
    history = ListeningHistory.objects.filter(user=request.user)[:10]
    
    context = {
        'profile': profile,
        'my_albums': my_albums,
        'history': history,
    }
    return render(request, 'profile.html', context)

@login_required
def toggle_favorite(request, track_id):
    track = get_object_or_404(Track, id=track_id)
    # Ищем специальный альбом пользователя "Любимое"
    favorite_album, created = Album.objects.get_or_create(
        owner=request.user, 
        is_favorite_folder=True,
        defaults={'title': 'Любимое'}
    )
    
    if track in favorite_album.tracks.all():
        favorite_album.tracks.remove(track)
    else:
        favorite_album.tracks.add(track)
        
    return redirect(request.META.get('HTTP_REFERER', 'home'))

def album_detail(request, album_id):
    # Находим альбом или выдаем 404, если ID левый
    album = get_object_or_404(Album, id=album_id)
    
    # Проверка приватности: если альбом не публичный и ты не владелец — доступ закрыт
    if not album.is_public and album.owner != request.user:
        return render(request, '403.html', status=403) # Можно просто редирект на главную

    return render(request, 'album_detail.html', {
        'album': album,
        'tracks': album.tracks.all()
    })




@login_required
def upload_track(request):
    # Проверяем, есть ли у пользователя профиль артиста
    if request.user.profile.role != 'artist':
        return render(request, '403.html', status=403) # Или редирект с сообщением об ошибке

    if request.method == 'POST':
        form = TrackUploadForm(request.POST, request.FILES)
        if form.is_valid():
            track = form.save(commit=False)
            # Привязываем трек к объекту Artist, связанному с текущим юзером
            track.artist = Artist.objects.get(user=request.user)
            track.save()
            return redirect('profile')
    else:
        form = TrackUploadForm()
    
    return render(request, 'upload_track.html', {'form': form})