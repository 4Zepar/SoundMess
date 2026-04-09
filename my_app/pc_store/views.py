from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from .models import Track, Artist, Profile, ListeningHistory, Album
from .forms import RegistrationForm, TrackUploadForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404


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
    profile = request.user.profile
    my_albums = Album.objects.filter(owner=request.user)
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