from django.urls import path

from apps.news.views import NewsDetailView, NewsListView

urlpatterns = [
    path('',           NewsListView.as_view(),   name='news-list'),
    path('<uuid:pk>/', NewsDetailView.as_view(), name='news-detail'),
]
