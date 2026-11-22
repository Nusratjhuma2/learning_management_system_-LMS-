"""Root URL configuration for lms_project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from accounts import views as accounts_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('instructors/', accounts_views.instructor_list, name='instructors_root'),
    path('instructors/<str:username>/', accounts_views.instructor_detail, name='instructor_detail_root'),
    path('courses/', include('courses.urls')),
    path('lessons/', include('lessons.urls')),
    path('quizzes/', include('quizzes.urls')),
    path('assignments/', include('assignments.urls')),
    path('enrollments/', include('enrollments.urls')),
    path('payments/', include('payments.urls')),
    path('discussions/', include('discussions.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('', RedirectView.as_view(url='/courses/', permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
