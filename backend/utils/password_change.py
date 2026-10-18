"""
F1: a password an administrator set must be replaced before the account is used.

An admin creating an account or resetting a password sees the temporary
password, and it used to keep working for as long as nobody changed it.
Until the owner picks their own, a signed-in account can only reach the
sign-in endpoints (/api/auth/: who am I, change password, 2FA, sign out).
Everything else answers 403 with code 'password_change_required', and the
app sends the user to the change-password screen.
"""

from django.http import JsonResponse

ALLOWED_PREFIX = '/api/auth/'

REQUIRED = {
    'error': 'Your password was set by an administrator. Choose your own password to continue.',
    'code': 'password_change_required',
}


class PasswordChangeRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith('/api/') and not path.startswith(ALLOWED_PREFIX):
            user = getattr(request, 'user', None)
            if user is not None and user.is_authenticated and getattr(user, 'must_change_password', False):
                return JsonResponse(REQUIRED, status=403)
        return self.get_response(request)
