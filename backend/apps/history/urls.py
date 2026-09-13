from django.urls import path
from apps.history.views import (
    HistoricalRecordListView,
    HistoricalRecordDetailView,
    HistoricalTrendsView,
)

urlpatterns = [
    path('',           HistoricalRecordListView.as_view(),   name='history-list'),
    path('trends/',    HistoricalTrendsView.as_view(),       name='history-trends'),
    path('<uuid:pk>/', HistoricalRecordDetailView.as_view(), name='history-detail'),
]