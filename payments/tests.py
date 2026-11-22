from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import Course, Category
from payments.forms import CouponForm
from payments.models import Coupon, Order

User = get_user_model()


class CouponSystemTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.admin = User.objects.create_superuser(
            username='admin_boss',
            email='admin@test.com',
            password='Password123!',
        )
        self.instructor_a = User.objects.create_user(
            username='instructor_a',
            email='inst_a@test.com',
            password='Password123!',
            role='instructor',
        )
        self.instructor_b = User.objects.create_user(
            username='instructor_b',
            email='inst_b@test.com',
            password='Password123!',
            role='instructor',
        )
        self.student = User.objects.create_user(
            username='student_sam',
            email='student@test.com',
            password='Password123!',
            role='student',
        )

        self.category = Category.objects.create(name='Computer Science', slug='cs')

        # Courses
        self.course_a = Course.objects.create(
            title='Course By Instructor A',
            slug='course-a',
            instructor=self.instructor_a,
            category=self.category,
            price=Decimal('100.00'),
            status=Course.Status.PUBLISHED,
        )
        self.course_b = Course.objects.create(
            title='Course By Instructor B',
            slug='course-b',
            instructor=self.instructor_b,
            category=self.category,
            price=Decimal('50.00'),
            status=Course.Status.PUBLISHED,
        )

    def test_instructor_can_create_coupon_for_own_course(self):
        """Instructors can successfully create coupons for their own courses."""
        form_data = {
            'code': 'INSTA25',
            'discount_percent': 25,
            'course': self.course_a.pk,
            'max_uses': 50,
            'is_active': True,
        }
        form = CouponForm(data=form_data, user=self.instructor_a)
        self.assertTrue(form.is_valid(), form.errors)
        coupon = form.save(commit=False)
        coupon.created_by = self.instructor_a
        coupon.save()

        self.assertEqual(coupon.code, 'INSTA25')
        self.assertEqual(coupon.course, self.course_a)
        self.assertEqual(coupon.created_by, self.instructor_a)

    def test_instructor_cannot_create_coupon_for_another_instructors_course(self):
        """Instructors cannot create coupons targeting other instructors' courses."""
        form_data = {
            'code': 'HACK50',
            'discount_percent': 50,
            'course': self.course_b.pk,  # Course owned by instructor_b
            'max_uses': 50,
            'is_active': True,
        }
        form = CouponForm(data=form_data, user=self.instructor_a)
        self.assertFalse(form.is_valid())
        self.assertIn('course', form.errors)

    def test_instructor_cannot_create_sitewide_coupon(self):
        """Instructors cannot create coupons with course=None (site-wide)."""
        form_data = {
            'code': 'GLOBAL20',
            'discount_percent': 20,
            'course': '',  # Blank course
            'max_uses': 50,
            'is_active': True,
        }
        form = CouponForm(data=form_data, user=self.instructor_a)
        self.assertFalse(form.is_valid())
        self.assertIn('course', form.errors)

    def test_admin_can_create_sitewide_coupon(self):
        """Admins can create site-wide coupons that apply to all courses."""
        form_data = {
            'code': 'ADMINALL30',
            'discount_percent': 30,
            'course': '',  # Blank course = site-wide
            'max_uses': 200,
            'is_active': True,
        }
        form = CouponForm(data=form_data, user=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        coupon = form.save(commit=False)
        coupon.created_by = self.admin
        coupon.save()

        self.assertEqual(coupon.code, 'ADMINALL30')
        self.assertIsNone(coupon.course)
        self.assertTrue(coupon.is_site_wide)

    def test_admin_can_create_course_specific_coupon_on_any_course(self):
        """Admins can create coupons for any course on the platform."""
        form_data = {
            'code': 'ADMINSPECIAL',
            'discount_percent': 40,
            'course': self.course_b.pk,
            'max_uses': 20,
            'is_active': True,
        }
        form = CouponForm(data=form_data, user=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        coupon = form.save(commit=False)
        coupon.created_by = self.admin
        coupon.save()

        self.assertEqual(coupon.course, self.course_b)

    def test_checkout_course_specific_coupon_validation(self):
        """A course-specific coupon is valid on its target course and rejected on other courses."""
        coupon = Coupon.objects.create(
            code='TARGETA',
            discount_percent=20,
            course=self.course_a,
            created_by=self.instructor_a,
        )

        # Valid on course_a
        is_valid, reason = coupon.is_valid(course=self.course_a)
        self.assertTrue(is_valid)

        # Rejected on course_b
        is_valid, reason = coupon.is_valid(course=self.course_b)
        self.assertFalse(is_valid)
        self.assertIn("only valid for 'Course By Instructor A'", reason)

    def test_checkout_sitewide_coupon_valid_on_any_course(self):
        """A site-wide coupon (course=None) is valid on any course."""
        coupon = Coupon.objects.create(
            code='SITEWIDE10',
            discount_percent=10,
            course=None,
            created_by=self.admin,
        )

        is_valid_a, _ = coupon.is_valid(course=self.course_a)
        is_valid_b, _ = coupon.is_valid(course=self.course_b)
        self.assertTrue(is_valid_a)
        self.assertTrue(is_valid_b)

    def test_student_forbidden_from_managing_coupons(self):
        """Students cannot access the coupon console."""
        self.client.force_login(self.student)
        res = self.client.get(reverse('payments:coupon_list'))
        self.assertEqual(res.status_code, 302)  # Redirects with permission denied

    def test_instructor_console_only_shows_authored_coupons(self):
        """Instructors only see coupons for their courses, not other instructors'."""
        coupon_a = Coupon.objects.create(code='COUPONA', discount_percent=10, course=self.course_a, created_by=self.instructor_a)
        coupon_b = Coupon.objects.create(code='COUPONB', discount_percent=10, course=self.course_b, created_by=self.instructor_b)

        self.client.force_login(self.instructor_a)
        res = self.client.get(reverse('payments:coupon_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'COUPONA')
        self.assertNotContains(res, 'COUPONB')

    def test_admin_console_shows_all_coupons(self):
        """Admin console lists coupons across the entire system."""
        Coupon.objects.create(code='COUPONA', discount_percent=10, course=self.course_a, created_by=self.instructor_a)
        Coupon.objects.create(code='COUPONB', discount_percent=10, course=self.course_b, created_by=self.instructor_b)

        self.client.force_login(self.admin)
        res = self.client.get(reverse('payments:coupon_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'COUPONA')
        self.assertContains(res, 'COUPONB')
