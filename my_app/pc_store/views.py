from django.shortcuts import render
from .models import Track

def track_list(request):
    tracks = Track.objects.all()
    return render(request, 'index.html', {'tracks': tracks})