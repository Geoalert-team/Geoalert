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
from apps.reports.summary import SummaryView
from apps.reports.trend_patterns import PatternsView, PlacesView
from apps.reports.trends import TrendsView

urlpatterns = [
    path('hazard-summary/',  HazardSummaryReportView.as_view(),  name='report-hazard-summary'),
    path('response-status/', ResponseStatusReportView.as_view(), name='report-response-status'),
    path('summary/',         SummaryView.as_view(),              name='report-summary'),
    path('analytics/',       AnalyticsView.as_view(),            name='report-analytics'),
    path('trends/',          TrendsView.as_view(),               name='report-trends'),
    path('trends/patterns/', PatternsView.as_view(),             name='report-trend-patterns'),
    path('trends/places/',   PlacesView.as_view(),               name='report-trend-places'),
    path('printed/',         ReportPrintedView.as_view(),        name='report-printed'),
    path('incidents/',              IncidentReportListCreateView.as_view(), name='incident-list-create'),
    path('incidents/<uuid:pk>/review/', IncidentReportReviewView.as_view(), name='incident-review'),
    path('incidents/<uuid:pk>/decide/', IncidentReportDecideView.as_view(), name='incident-decide'),
]