from django.urls import path
from apps.accounts.views import (
    LoginView, LogoutView, MeView, csrf_view,
    TwoFactorSetupView, TwoFactorConfirmView, TwoFactorVerifyView, TwoFactorDisableView,
    ChangePasswordView,
)

urlpatterns = [
    path('csrf/',             csrf_view,                      name='csrf'),
    path('login/',            LoginView.as_view(),             name='login'),
    path('logout/',           LogoutView.as_view(),            name='logout'),
    path('me/',                MeView.as_view(),                name='me'),
    path('2fa/setup/',        TwoFactorSetupView.as_view(),    name='2fa-setup'),
    path('2fa/confirm/',      TwoFactorConfirmView.as_view(),  name='2fa-confirm'),
    path('2fa/verify/',       TwoFactorVerifyView.as_view(),   name='2fa-verify'),
    path('2fa/disable/',      TwoFactorDisableView.as_view(),  name='2fa-disable'),
    path('change-password/',  ChangePasswordView.as_view(),    name='change-password'),
]