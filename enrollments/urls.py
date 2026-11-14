from django.urls import path
from . import views

app_name = 'enrollments'

urlpatterns = [
    path('enroll/<slug:course_slug>/', views.enroll, name='enroll'),
    path('unenroll/<slug:course_slug>/', views.unenroll, name='unenroll'),
    path('my-courses/', views.my_courses, name='my_courses'),
    path('my-certificates/', views.my_certificates, name='my_certificates'),
    path('verify/<uuid:certificate_uid>/', views.verify_certificate, name='verify_certificate'),
    path('download/<uuid:certificate_uid>/', views.download_certificate, name='download_certificate'),
]
