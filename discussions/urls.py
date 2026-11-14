from django.urls import path
from . import views

app_name = 'discussions'

urlpatterns = [
    path('course/<slug:course_slug>/', views.course_discussions, name='course_discussions'),
    path('course/<slug:course_slug>/new/', views.thread_create, name='thread_create'),
    path('course/<slug:course_slug>/announcements/new/', views.create_announcement, name='create_announcement'),
    path('thread/<int:pk>/', views.thread_detail, name='thread_detail'),
    path('thread/<int:pk>/reply/', views.reply_create, name='reply_create'),
    path('thread/<int:pk>/toggle-resolve/', views.toggle_resolve, name='toggle_resolve'),
    path('api/lesson/<int:lesson_id>/thread/', views.create_thread_api, name='create_thread_api'),
    path('api/thread/<int:thread_id>/reply/', views.reply_thread_api, name='reply_thread_api'),
    path('notifications/', views.notifications_list, name='notifications_list'),
]
