from django import template
from django.core.exceptions import SuspiciousFileOperation

register = template.Library()


@register.filter
def action_label(value):
    return {
        'approved': 'Одобрено',
        'rejected': 'Отклонено',
        'hidden': 'Скрыто',
        'restored': 'Восстановлено',
        'deleted': 'Удалено',
        'balance_adjustment': 'Корректировка баланса',
        'active': 'Доступ к аккаунту',
        'role': 'Права доступа'
    }.get(value, value)


@register.filter
def target_label(value):
    return {
        'track': 'Трек',
        'album': 'Релиз',
        'artist': 'Заявка артиста',
        'comment': 'Комментарий',
        'user': 'Пользователь',
        'wallet_transaction': 'Операция'
    }.get(value, value)


@register.filter
def image_url(field):
    if not field:
        return ''
    try:
        return field.url if field.storage.exists(field.name) else ''
    except (ValueError, OSError, SuspiciousFileOperation):
        return ''


@register.filter
def duration(value):
    seconds = int(value or 0)
    return f'{seconds // 60}:{seconds % 60:02d}'


@register.simple_tag(takes_context=True)
def page_query(context, page):
    query = context['request'].GET.copy()
    query['page'] = page
    return query.urlencode()
