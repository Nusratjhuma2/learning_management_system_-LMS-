from django.urls import path
from . import views

app_name = 'assignments'

urlpatterns = [
    path('', views.instructor_assignments_list, name='instructor_assignments'),
    path('<int:pk>/', views.assignment_detail, name='assignment_detail'),
    path('<int:pk>/submit/', views.submit_assignment, name='submit_assignment'),
    path('course/<slug:course_slug>/create/', views.assignment_create, name='assignment_create'),
    path('<int:pk>/edit/', views.assignment_update, name='assignment_update'),
    path('<int:pk>/delete/', views.assignment_delete, name='assignment_delete'),
    path('<int:pk>/submissions/', views.submissions_list, name='submissions_list'),
    path('submission/<int:submission_id>/grade/', views.grade_submission, name='grade_submission'),
]
