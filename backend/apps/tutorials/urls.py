from django.urls import path

from apps.tutorials.views import (
    CategoryDetailView, CategoryListView, VideoDetailView, VideoListView, YouTubeCheckView,
)

urlpatterns = [
    path('',                      VideoListView.as_view(),      name='tutorial-list'),
    path('<uuid:pk>/',            VideoDetailView.as_view(),    name='tutorial-detail'),
    path('categories/',           CategoryListView.as_view(),   name='tutorial-category-list'),
    path('categories/<uuid:pk>/', CategoryDetailView.as_view(), name='tutorial-category-detail'),
    path('youtube-check/',        YouTubeCheckView.as_view(),   name='tutorial-youtube-check'),
]
