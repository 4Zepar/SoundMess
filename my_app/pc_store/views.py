from django.contrib.auth import login, logout
from .models import Track, Artist, Profile, ListeningHistory, Album
from .forms import RegistrationForm, TrackUploadForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .forms import AlbumForm

def track_list(request):
    tracks = Track.objects.all()
    return render(request, 'index.html', {'tracks': tracks})


def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            
            role = form.cleaned_data.get('role')
            profile = user.profile
            profile.role = role
            profile.save()

            if role == 'artist':
                Artist.objects.create(user=user)
            
            login(request, user)
            return redirect('home')
    else:
        form = RegistrationForm()
    return render(request, 'register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required 
def profile_view(request):
    my_albums = Album.objects.filter(owner=request.user)
    my_tracks = None
    if request.user.profile.role == 'artist':
        my_tracks = Track.objects.filter(artist__user=request.user)

    context = {
        'my_albums': my_albums,
        'my_tracks': my_tracks,
    }
    return render(request, 'profile.html', context)


@login_required
def toggle_favorite(request, track_id):
    track = get_object_or_404(Track, id=track_id)
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
    album = get_object_or_404(Album, id=album_id)
    
    if not album.is_public and album.owner != request.user:
        return render(request, '403.html', status=403) 

    return render(request, 'album_detail.html', {
        'album': album,
        'tracks': album.tracks.all()
    })




@login_required
def upload_track(request):
    if request.user.profile.role != 'artist':
        return render(request, '403.html', status=403) 

    if request.method == 'POST':
        form = TrackUploadForm(request.POST, request.FILES)
        if form.is_valid():
            track = form.save(commit=False)
            track.artist = Artist.objects.get(user=request.user)
            track.save()
            return redirect('profile')
    else:
        form = TrackUploadForm()
    
    return render(request, 'upload_track.html', {'form': form})




@login_required
def create_album(request):
    if request.method == 'POST':
        # ВАЖНО: добавлен request.FILES
        form = AlbumForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            album = form.save(commit=False)
            album.owner = request.user
            album.save()
            
            # Логика фильтрации треков (как мы делали раньше)
            selected_tracks = form.cleaned_data['tracks']
            if album.is_public:
                final_tracks = selected_tracks.filter(artist__user=request.user)
                album.tracks.set(final_tracks)
            else:
                album.tracks.set(selected_tracks)
                
            return redirect('profile')
    else:
        form = AlbumForm(user=request.user)
    return render(request, 'create_album.html', {'form': form})


@login_required
def delete_album(request, album_id):
    # Ищем альбом, который принадлежит юзеру
    album = get_object_or_404(Album, id=album_id, owner=request.user)
    
    # Защита от удаления системного альбома
    if not album.is_favorite_folder:
        album.delete()
        
    return redirect('profile')

from django.http import JsonResponse

@login_required
def add_track_to_album(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        track_id = data.get('track_id')
        album_id = data.get('album_id')
        
        track = get_object_or_404(Track, id=track_id)
        # Ищем альбом, убеждаясь, что он принадлежит юзеру
        album = get_object_or_404(Album, id=album_id, owner=request.user)
        
        if track not in album.tracks.all():
            album.tracks.add(track)
            return JsonResponse({'status': 'added'})
        else:
            return JsonResponse({'status': 'exists'})
    
    return JsonResponse({'status': 'error'}, status=400)


@login_required
def remove_track_from_album(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        track_id = data.get('track_id')
        album_id = data.get('album_id')
        
        album = get_object_or_404(Album, id=album_id, owner=request.user)
        track = get_object_or_404(Track, id=track_id)
        
        album.tracks.remove(track)
        return JsonResponse({'status': 'removed'})
    return JsonResponse({'status': 'error'}, status=400)