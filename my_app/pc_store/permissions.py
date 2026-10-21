from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def can_moderate(user):
    return user.is_authenticated and user.is_active and (
        user.is_superuser or user.has_perm('pc_store.moderate_content')
    )


def can_manage_users(user):
    return user.is_authenticated and user.is_active and (
        user.is_superuser or user.has_perm('pc_store.manage_accounts')
    )


def require_access(predicate):
    def decorate(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not predicate(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


moderator_required = require_access(can_moderate)
administrator_required = require_access(can_manage_users)
