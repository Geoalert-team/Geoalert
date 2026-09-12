from django.urls import path
from apps.accounts.views import LoginView, LogoutView, MeView, csrf_view

urlpatterns = [
    path('csrf/',   csrf_view,            name='csrf'),
    path('login/',  LoginView.as_view(),  name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/',     MeView.as_view(),     name='me'),
]