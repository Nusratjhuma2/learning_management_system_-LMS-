from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_router, name='index'),
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('instructor/', views.instructor_dashboard, name='instructor_dashboard'),
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('session/<int:session_pk>/terminate/', views.terminate_session, name='terminate_session'),
]

