from django.urls import path
from apps.guidance.views import GuidanceListView, GuidanceDetailView

urlpatterns = [
    path('',           GuidanceListView.as_view(),  name='guidance-list'),
    path('<uuid:pk>/', GuidanceDetailView.as_view(), name='guidance-detail'),
]