from django.shortcuts import render
from .models import Track

def track_list(request):
    # Получаем все треки из базы данных
    tracks = Track.objects.all()
    # Отправляем их в шаблон index.html
    return render(request, 'index.html', {'tracks': tracks})