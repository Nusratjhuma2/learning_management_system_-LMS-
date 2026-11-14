from django.urls import path
from . import views

app_name = 'quizzes'

urlpatterns = [
    path('<int:pk>/', views.quiz_detail, name='quiz_detail'),
    path('<int:pk>/submit/', views.quiz_submit, name='quiz_submit'),
    path('<int:pk>/log-tab-switch/', views.log_tab_switch, name='log_tab_switch'),
    path('result/<int:attempt_id>/', views.quiz_result, name='quiz_result'),
    path('create/<slug:course_slug>/', views.quiz_create, name='quiz_create'),
    path('<int:pk>/edit/', views.quiz_edit, name='quiz_edit'),
    path('<int:pk>/delete/', views.quiz_delete, name='quiz_delete'),
    path('<int:quiz_pk>/questions/add/', views.question_create, name='question_create'),
    path('questions/<int:pk>/delete/', views.question_delete, name='question_delete'),
    path('<int:pk>/attempts/', views.quiz_attempts_list, name='quiz_attempts_list'),
]
