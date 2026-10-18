from django.urls import path
from apps.history.views import (
    HistoricalRecordListView,
    HistoricalRecordDetailView,
    HistoricalTrendsView,
    HistoricalHeatView,
    HistoricalForecastView,
)

urlpatterns = [
    path('',           HistoricalRecordListView.as_view(),   name='history-list'),
    path('trends/',    HistoricalTrendsView.as_view(),       name='history-trends'),
    path('forecast/', HistoricalForecastView.as_view(),     name='history-forecast'),
    path('heat/',      HistoricalHeatView.as_view(),         name='history-heat'),
    path('<uuid:pk>/', HistoricalRecordDetailView.as_view(), name='history-detail'),
]