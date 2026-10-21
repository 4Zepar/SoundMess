from django.http import JsonResponse
from django.shortcuts import render


def error_response(request, status):
    if 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse(
            {'error': str(status), 'message': 'Запрос не может быть выполнен.'},
            status=status
        )
    return render(request, 'error.html', {'status': status}, status=status)


def forbidden(request, exception):
    return error_response(request, 403)


def not_found(request, exception):
    return error_response(request, 404)


def server_error(request):
    return error_response(request, 500)
