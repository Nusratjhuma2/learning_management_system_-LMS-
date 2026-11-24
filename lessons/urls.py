from django.urls import path

from . import views

app_name = 'lessons'

urlpatterns = [
    path('<slug:course_slug>/lessons/add/', views.lesson_create, name='lesson_create'),
    path('<slug:course_slug>/lessons/<int:pk>/', views.lesson_detail, name='lesson_detail'),
    path('<slug:course_slug>/lessons/<int:pk>/edit/', views.lesson_update, name='lesson_update'),
    path('<slug:course_slug>/lessons/<int:pk>/delete/', views.lesson_delete, name='lesson_delete'),

    # Secure HLS Streaming Endpoints
    path('<slug:course_slug>/lessons/<int:lesson_id>/hls/manifest.m3u8', views.lesson_hls_manifest, name='hls_manifest'),
    path('<slug:course_slug>/lessons/<int:lesson_id>/hls/<str:quality>/manifest.m3u8', views.lesson_hls_variant_manifest, name='hls_variant_manifest'),
    path('<slug:course_slug>/lessons/<int:lesson_id>/hls/key/', views.lesson_hls_key, name='hls_key'),
    path('<slug:course_slug>/lessons/<int:lesson_id>/hls/segment/<str:segment_name>', views.lesson_hls_segment, name='hls_segment'),
    path('<slug:course_slug>/lessons/<int:lesson_id>/hls/<str:quality>/segment/<str:segment_name>', views.lesson_hls_variant_segment, name='hls_variant_segment'),
    path('<slug:course_slug>/lessons/<int:lesson_id>/stream/', views.lesson_protected_stream, name='protected_stream'),

    # Security, Transcript & Progress APIs
    path('api/heartbeat/<int:lesson_id>/', views.lesson_heartbeat_api, name='heartbeat_api'),
    path('api/mark-completed/<int:lesson_id>/', views.mark_lesson_completed_api, name='mark_completed_api'),
    path('api/security-violation/', views.log_security_violation_api, name='log_security_violation_api'),
    path('api/notes/<int:lesson_id>/save/', views.lesson_save_note_api, name='save_note_api'),
    path('api/transcript/<int:lesson_id>/generate/', views.generate_transcript_api, name='generate_transcript_api'),
]
