from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from pc_store.forms import ProfileForm, RegistrationForm
from pc_store.models import Artist


def register_view(request):
    if request.user.is_authenticated:
        return redirect('profile')
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
            user.profile.role = form.cleaned_data['role']
            user.profile.save(update_fields=['role'])
        login(request, user)
        messages.success(request, 'Аккаунт создан. Добро пожаловать в SoundMess!')
        return redirect('artist_application' if form.cleaned_data['role'] == 'artist' else 'profile')
    return render(request, 'register.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile_edit(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user.profile)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            profile = form.save()
            Artist.objects.filter(user=request.user).update(bio=profile.bio)
        messages.success(request, 'Профиль обновлён.')
        return redirect('profile')
    return render(request, 'profile_edit.html', {'form': form})
