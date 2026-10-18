from django.urls import path
from apps.barangays.views import BarangayListView, BarangayDetailView, BarangayHazardsView

urlpatterns = [
    path('',        BarangayListView.as_view(),   name='barangay-list'),
    path('<int:pk>/', BarangayDetailView.as_view(), name='barangay-detail'),
    path('<int:pk>/hazards/', BarangayHazardsView.as_view(), name='barangay-hazards'),
]