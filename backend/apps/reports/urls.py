from django.urls import path
from apps.reports.views import (
    HazardSummaryReportView,
    ResponseStatusReportView,
    IncidentReportListCreateView,
    IncidentReportReviewView,
    
)

urlpatterns = [
    path('hazard-summary/',  HazardSummaryReportView.as_view(),  name='report-hazard-summary'),
    path('response-status/', ResponseStatusReportView.as_view(), name='report-response-status'),
    path('incidents/',              IncidentReportListCreateView.as_view(), name='incident-list-create'),
    path('incidents/<uuid:pk>/review/', IncidentReportReviewView.as_view(), name='incident-review'),
]