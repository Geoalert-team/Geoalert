from django.urls import path
from apps.reports.views import (
    HazardSummaryReportView,
    ResponseStatusReportView,
)

urlpatterns = [
    path('hazard-summary/',  HazardSummaryReportView.as_view(),  name='report-hazard-summary'),
    path('response-status/', ResponseStatusReportView.as_view(), name='report-response-status'),
]