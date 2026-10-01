from django.urls import path
from apps.barangays.barangays_views import BarangayListView, BarangayDetailView

urlpatterns = [
    path('',        BarangayListView.as_view(),   name='barangay-list'),
    path('<int:pk>/', BarangayDetailView.as_view(), name='barangay-detail'),
]