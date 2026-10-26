from django.urls import path
from apps.history.views import (
    HistoricalRecordListView,
    HistoricalRecordDetailView,
    HistoricalTrendsView,
    HistoricalHeatView,
    HistoricalForecastView,
)
from apps.hazards.fire_close_views import BfpOptionsView

urlpatterns = [
    path('',           HistoricalRecordListView.as_view(),   name='history-list'),
    path('trends/',    HistoricalTrendsView.as_view(),       name='history-trends'),
    path('forecast/', HistoricalForecastView.as_view(),     name='history-forecast'),
    path('heat/',      HistoricalHeatView.as_view(),         name='history-heat'),
    # The fire close form's lists: property types and alarm levels
    path('bfp-options/', BfpOptionsView.as_view(),           name='history-bfp-options'),
    path('<uuid:pk>/', HistoricalRecordDetailView.as_view(), name='history-detail'),
]