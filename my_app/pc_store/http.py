import json
from functools import wraps

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse


def json_body(request):
    try:
        data = json.loads(request.body or '{}')
    except (UnicodeDecodeError, ValueError) as error:
        raise ValidationError('Некорректный JSON.', code='invalid_json') from error
    if not isinstance(data, dict):
        raise ValidationError('Ожидается JSON-объект.', code='invalid_json')
    return data


def integer(value, label='Значение', minimum=0, maximum=2**63 - 1):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValidationError(f'{label}: требуется целое число.')
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f'{label}: требуется целое число.') from error
    if result < minimum:
        raise ValidationError(f'{label}: минимальное значение — {minimum}.')
    if result > maximum:
        raise ValidationError(f'{label}: максимальное значение — {maximum}.')
    return result


def api_endpoint(*, methods=('POST',), authenticated=True):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                response = JsonResponse(
                    {'error': 'method_not_allowed', 'message': 'Метод не поддерживается.'},
                    status=405
                )
                response['Allow'] = ', '.join(methods)
                return response
            if authenticated and not request.user.is_authenticated:
                return JsonResponse(
                    {'error': 'authentication_required', 'message': 'Войдите в аккаунт.'},
                    status=401
                )
            try:
                return view(request, *args, **kwargs)
            except ValidationError as error:
                return JsonResponse(
                    {
                        'error': getattr(error, 'code', None) or 'invalid_request',
                        'message': ' '.join(error.messages)
                    },
                    status=400
                )
            except PermissionDenied:
                return JsonResponse(
                    {'error': 'permission_denied', 'message': 'Недостаточно прав.'},
                    status=403
                )
            except Http404:
                return JsonResponse({'error': 'not_found', 'message': 'Материал не найден.'}, status=404)
        return wrapped
    return decorate
