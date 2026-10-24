from django.urls import path
from apps.barangays.views import BarangayListView, BarangayDetailView, BarangayHazardsView, PurokListView

urlpatterns = [
    path('',        BarangayListView.as_view(),   name='barangay-list'),
    path('puroks/', PurokListView.as_view(),      name='purok-list'),
    path('<int:pk>/', BarangayDetailView.as_view(), name='barangay-detail'),
    path('<int:pk>/hazards/', BarangayHazardsView.as_view(), name='barangay-hazards'),
]
