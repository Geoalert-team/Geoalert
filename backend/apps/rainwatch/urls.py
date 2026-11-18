from django.urls import path

from apps.rainwatch import views

urlpatterns = [
    path('', views.RainWatchView.as_view()),
    path('forecast-runs/', views.ForecastRunView.as_view()),
    path('forecast-runs/status/', views.ForecastRunStatusView.as_view()),
    path('overrides/', views.OverrideListView.as_view()),
    path('overrides/<int:pk>/cancel/', views.OverrideCancelView.as_view()),
]
