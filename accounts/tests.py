from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, RequestFactory, TestCase

from accounts.admin import AdministratorAdmin, UserAdmin
from accounts.forms import SignUpForm
from accounts.models import Administrator

User = get_user_model()


class AdminSegregationAndPermissionsTests(TestCase):
    """Verifies segregation of regular users from administrators and full permission grants."""

    def setUp(self):
        self.rf = RequestFactory()
        self.request = self.rf.get('/admin/')
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(self.request, 'session', {})
        setattr(self.request, '_messages', FallbackStorage(self.request))

        self.super_admin = User.objects.create_superuser(
            username='root_admin',
            email='root@example.com',
            password='Password123!',
        )
        self.instructor = User.objects.create_user(
            username='instructor_jane',
            email='jane@example.com',
            password='Password123!',
            role='instructor',
        )
        self.student = User.objects.create_user(
            username='student_mark',
            email='mark@example.com',
            password='Password123!',
            role='student',
        )

    def test_user_admin_excludes_administrators(self):
        """UserAdmin must strictly exclude administrators and superusers."""
        user_admin = UserAdmin(User, admin.site)
        qs = user_admin.get_queryset(self.request)
        usernames = list(qs.values_list('username', flat=True))

        self.assertNotIn('root_admin', usernames)
        self.assertIn('instructor_jane', usernames)
        self.assertIn('student_mark', usernames)

    def test_administrator_admin_includes_only_administrators(self):
        """AdministratorAdmin must only include administrators and superusers."""
        admin_admin = AdministratorAdmin(Administrator, admin.site)
        qs = admin_admin.get_queryset(self.request)
        usernames = list(qs.values_list('username', flat=True))

        self.assertIn('root_admin', usernames)
        self.assertNotIn('instructor_jane', usernames)
        self.assertNotIn('student_mark', usernames)

    def test_public_signup_form_excludes_admin_role(self):
        """Public signup must not allow choosing 'admin' as a role."""
        form = SignUpForm()
        role_choices = [c[0] for c in form.fields['role'].choices]
        self.assertNotIn('admin', role_choices)
        self.assertIn('student', role_choices)
        self.assertIn('instructor', role_choices)

    def test_saving_administrator_grants_all_permissions_and_superuser(self):
        """Saving an Administrator via AdministratorAdmin grants every system permission and superuser access."""
        admin_admin = AdministratorAdmin(Administrator, admin.site)
        new_admin = Administrator(
            username='new_admin_gov',
            email='gov@example.com',
        )
        new_admin.set_password('Password123!')
        admin_admin.save_model(self.request, new_admin, form=None, change=False)

        saved = Administrator.objects.get(username='new_admin_gov')
        self.assertTrue(saved.is_superuser)
        self.assertTrue(saved.is_staff)
        self.assertEqual(saved.role, User.Role.ADMIN)

        total_system_perms = Permission.objects.count()
        self.assertEqual(saved.user_permissions.count(), total_system_perms)

    def test_grant_all_permissions_action(self):
        """The grant_all_permissions action assigns all permissions and superuser access."""
        admin_admin = AdministratorAdmin(Administrator, admin.site)
        promoted = Administrator.objects.create(
            username='promoted_officer',
            email='promoted@example.com',
        )
        qs = Administrator.objects.filter(pk=promoted.pk)
        admin_admin.grant_all_permissions(self.request, qs)

        promoted.refresh_from_db()
        self.assertTrue(promoted.is_superuser)
        self.assertTrue(promoted.is_staff)
        self.assertEqual(promoted.role, User.Role.ADMIN)
        self.assertEqual(promoted.user_permissions.count(), Permission.objects.count())

    def test_all_lms_models_registered_in_admin(self):
        """Verifies that all models across the enterprise LMS are registered in admin.site."""
        from assignments.models import Assignment, AssignmentSubmission
        from courses.models import Announcement, Category, Course, Module
        from discussions.models import CourseAnnouncement, DiscussionThread, Notification
        from enrollments.models import Badge, Certificate, Enrollment, StudentBadge
        from lessons.models import Lesson, LessonNote, LessonProgress
        from payments.models import Coupon, Order, PaymentTransaction
        from quizzes.models import Choice, Question, Quiz, QuizAttempt, QuizAttemptAnswer

        expected_models = [
            User, Administrator,
            Assignment, AssignmentSubmission,
            Course, Category, Module, Announcement,
            DiscussionThread, CourseAnnouncement, Notification,
            Enrollment, Certificate, Badge, StudentBadge,
            Lesson, LessonProgress, LessonNote,
            Coupon, Order, PaymentTransaction,
            Quiz, Question, Choice, QuizAttempt, QuizAttemptAnswer,
        ]

        for model in expected_models:
            self.assertIn(model, admin.site._registry, f"{model.__name__} should be registered in admin.site")

    def test_instructor_list_view_accessible(self):
        """Instructor directory is publicly accessible and lists active instructors."""
        client = Client()
        res = client.get('/accounts/instructors/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'instructor_jane')
        self.assertNotContains(res, 'student_mark')

    def test_instructor_list_search(self):
        """Instructor directory can be filtered by name or department."""
        self.instructor.department = 'Computer Science'
        self.instructor.save()

        client = Client()
        res = client.get('/accounts/instructors/?q=jane')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'instructor_jane')

        res_miss = client.get('/accounts/instructors/?q=nonexistent_prof')
        self.assertEqual(res_miss.status_code, 200)
        self.assertNotContains(res_miss, 'instructor_jane')

    def test_instructor_detail_view(self):
        """Instructor public profile page renders correctly with faculty credentials."""
        self.instructor.institution_name = 'MIT'
        self.instructor.department = 'Artificial Intelligence'
        self.instructor.bio = 'Pioneering researcher in AI.'
        self.instructor.save()

        client = Client()
        res = client.get(f'/accounts/instructors/{self.instructor.username}/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'instructor_jane')
        self.assertContains(res, 'MIT')
        self.assertContains(res, 'Artificial Intelligence')
        self.assertContains(res, 'Pioneering researcher in AI.')

    def test_instructor_detail_404_for_non_instructor(self):
        """Attempting to view a student's profile via instructor detail returns 404."""
        client = Client()
        res = client.get(f'/accounts/instructors/{self.student.username}/')
        self.assertEqual(res.status_code, 404)
