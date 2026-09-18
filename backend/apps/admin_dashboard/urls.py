from django.urls import path
from apps.admin_dashboard.views import (
    DashboardMetricsView,
    UserListCreateView,
    UserDetailView,
    ResetPasswordView,
    AuditLogListView
)

urlpatterns = [
    path('metrics/',                       DashboardMetricsView.as_view(),  name='admin-metrics'),
    path('users/',                         UserListCreateView.as_view(),    name='admin-users'),
    path('users/<uuid:pk>/',               UserDetailView.as_view(),        name='admin-user-detail'),
    path('users/<uuid:pk>/reset-password/', ResetPasswordView.as_view(),    name='admin-reset-password'),
    path('logs/',                          AuditLogListView.as_view(),      name='admin-logs'),
]