from django.urls import path
from apps.hazards.views import (
    HazardZoneListView,
    HazardZoneDetailView,
    HazardZoneResolvedListView,
    HazardZoneRetractView,
    HazardZoneRetractedListView,
    HazardZoneAwaitingListView,
    HazardZoneApproveView,
    HazardZoneRefuseRaiseView,
    HazardZoneReceiptsView,
    HazardTypeListView,
    HazardLayerListView,
)
from apps.hazards.fire_close_views import FireCloseView
from apps.hazards.field_views import ZoneFieldMarkDetailView, ZoneFieldMarksView

urlpatterns = [
    path('<uuid:pk>/marks/',  ZoneFieldMarksView.as_view(),         name='hazard-marks'),
    path('<uuid:pk>/marks/<uuid:mark_id>/', ZoneFieldMarkDetailView.as_view(),
         name='hazard-mark-detail'),
    path('',                  HazardZoneListView.as_view(),         name='hazard-list'),
    path('awaiting/',         HazardZoneAwaitingListView.as_view(), name='hazard-awaiting'),
    path('<uuid:pk>/approve/', HazardZoneApproveView.as_view(),      name='hazard-approve'),
    path('<uuid:pk>/raise/refuse/', HazardZoneRefuseRaiseView.as_view(), name='hazard-raise-refuse'),
    path('<uuid:pk>/receipts/', HazardZoneReceiptsView.as_view(),     name='hazard-receipts'),
    path('types/',            HazardTypeListView.as_view(),         name='hazard-types'),
    path('layers/',           HazardLayerListView.as_view(),        name='hazard-layers'),
    path('resolved/',          HazardZoneResolvedListView.as_view(),  name='hazard-resolved'),
    path('retracted/',         HazardZoneRetractedListView.as_view(), name='hazard-retracted'),
    path('<uuid:pk>/retract/', HazardZoneRetractView.as_view(),       name='hazard-retract'),
    # A fire closes with the BFP figures, which also puts it out
    path('<uuid:pk>/close/',   FireCloseView.as_view(),              name='hazard-fire-close'),
    path('<uuid:pk>/',         HazardZoneDetailView.as_view(),        name='hazard-detail'),
]