from django.urls import path

from . import views

app_name = 'courses'

urlpatterns = [
    path('', views.course_list, name='course_list'),
    path('create/', views.course_create, name='course_create'),
    path('<slug:slug>/', views.course_detail, name='course_detail'),
    path('<slug:slug>/update/', views.course_update, name='course_update'),
    path('<slug:slug>/delete/', views.course_delete, name='course_delete'),
    path('<slug:slug>/toggle-block/', views.toggle_course_block, name='toggle_block'),
    path('<slug:slug>/review/', views.add_course_review, name='add_review'),
    path('<slug:slug>/wishlist/', views.toggle_wishlist, name='toggle_wishlist'),
]
