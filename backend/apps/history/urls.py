from django.urls import path
from apps.history.views import (
    HistoricalRecordListView,
    HistoricalRecordDetailView,
    HistoricalTrendsView,
    HistoricalForecastView,
    PurokLevelsView,
    AreaHistoryView,
    EventOptionsView,
)
from apps.hazards.fire_close_views import BfpOptionsView

urlpatterns = [
    path('',           HistoricalRecordListView.as_view(),   name='history-list'),
    path('trends/',    HistoricalTrendsView.as_view(),       name='history-trends'),
    path('forecast/', HistoricalForecastView.as_view(),     name='history-forecast'),
    # Per purok and hazard type: how often it was hit and the level that gives
    path('purok-levels/', PurokLevelsView.as_view(),         name='history-purok-levels'),
    # One barangay's past hazards, or one purok's in it
    path('area/',      AreaHistoryView.as_view(),            name='history-area'),
    # The fire close form's lists: property types and alarm levels
    path('bfp-options/', BfpOptionsView.as_view(),           name='history-bfp-options'),
    # The flood and landslide close form's list: sub categories
    path('event-options/', EventOptionsView.as_view(),       name='history-event-options'),
    path('<uuid:pk>/', HistoricalRecordDetailView.as_view(), name='history-detail'),
]