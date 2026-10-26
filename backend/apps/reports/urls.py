from django.urls import path
from apps.reports.views import (
    HazardSummaryReportView,
    ResponseStatusReportView,
    IncidentReportListCreateView,
    IncidentReportReviewView,
    ReportPrintedView,

)
from apps.reports.analytics import AnalyticsView
from apps.reports.decide_views import IncidentReportDecideView

urlpatterns = [
    path('hazard-summary/',  HazardSummaryReportView.as_view(),  name='report-hazard-summary'),
    path('response-status/', ResponseStatusReportView.as_view(), name='report-response-status'),
    path('analytics/',       AnalyticsView.as_view(),            name='report-analytics'),
    path('printed/',         ReportPrintedView.as_view(),        name='report-printed'),
    path('incidents/',              IncidentReportListCreateView.as_view(), name='incident-list-create'),
    path('incidents/<uuid:pk>/review/', IncidentReportReviewView.as_view(), name='incident-review'),
    path('incidents/<uuid:pk>/decide/', IncidentReportDecideView.as_view(), name='incident-decide'),
]