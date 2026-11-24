from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from courses.forms import CourseForm
from courses.models import Category, Course
from enrollments.models import Enrollment

User = get_user_model()


class CoursePricingModelTests(TestCase):
    """Unit tests for Course model pricing properties and save hooks."""

    def setUp(self):
        self.instructor = User.objects.create_user(
            username='prof_pricing',
            email='prof@example.com',
            password='testpassword123',
            role='instructor',
        )

    def test_free_course_properties(self):
        course = Course.objects.create(
            title='Intro to Algorithms',
            instructor=self.instructor,
            is_free=True,
            price=Decimal('50.00'),
            discount_price=Decimal('20.00'),
            description='Free algorithms curriculum.',
        )
        self.assertTrue(course.is_free)
        self.assertEqual(course.price, Decimal('0.00'))
        self.assertIsNone(course.discount_price)
        self.assertEqual(course.effective_price, Decimal('0.00'))
        self.assertFalse(course.has_discount)
        self.assertEqual(course.discount_percentage, 0)
        self.assertEqual(course.savings_amount, Decimal('0.00'))
        self.assertEqual(course.formatted_price, 'Free')

    def test_paid_course_without_discount(self):
        course = Course.objects.create(
            title='Advanced Microeconomics',
            instructor=self.instructor,
            is_free=False,
            price=Decimal('100.00'),
            description='Graduate microeconomics theory.',
        )
        self.assertFalse(course.is_free)
        self.assertEqual(course.price, Decimal('100.00'))
        self.assertIsNone(course.discount_price)
        self.assertEqual(course.effective_price, Decimal('100.00'))
        self.assertFalse(course.has_discount)
        self.assertEqual(course.discount_percentage, 0)
        self.assertEqual(course.savings_amount, Decimal('0.00'))
        self.assertEqual(course.formatted_price, '$100.00')

    def test_paid_course_with_valid_discount(self):
        course = Course.objects.create(
            title='Deep Learning & Neural Networks',
            instructor=self.instructor,
            is_free=False,
            price=Decimal('80.00'),
            discount_price=Decimal('60.00'),
            description='Modern neural networks.',
        )
        self.assertFalse(course.is_free)
        self.assertEqual(course.price, Decimal('80.00'))
        self.assertEqual(course.discount_price, Decimal('60.00'))
        self.assertEqual(course.effective_price, Decimal('60.00'))
        self.assertTrue(course.has_discount)
        self.assertEqual(course.discount_percentage, 25)
        self.assertEqual(course.savings_amount, Decimal('20.00'))
        self.assertEqual(course.formatted_price, '$60.00')

    def test_invalid_discount_price_reset(self):
        course = Course.objects.create(
            title='Fault Tolerance',
            instructor=self.instructor,
            is_free=False,
            price=Decimal('50.00'),
            discount_price=Decimal('50.00'),  # Equal to price -> invalid
            description='Fault tolerant systems.',
        )
        self.assertIsNone(course.discount_price)
        self.assertFalse(course.has_discount)
        self.assertEqual(course.effective_price, Decimal('50.00'))


class CoursePricingFormTests(TestCase):
    """Validation tests for CourseForm pricing rules."""

    def setUp(self):
        self.category = Category.objects.create(name='Computer Science', slug='cs')

    def test_paid_course_requires_price(self):
        form = CourseForm(data={
            'title': 'Operating Systems',
            'category': self.category.id,
            'level': 'beginner',
            'language': 'English',
            'is_free': False,
            'price': '0.00',
            'description': 'OS fundamentals.',
            'status': 'published',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)

    def test_discount_price_must_be_less_than_regular_price(self):
        form = CourseForm(data={
            'title': 'Database Systems',
            'category': self.category.id,
            'level': 'intermediate',
            'language': 'English',
            'is_free': False,
            'price': '50.00',
            'discount_price': '60.00',  # Greater than regular price
            'description': 'Relational databases and SQL.',
            'status': 'published',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('discount_price', form.errors)

    def test_free_course_clears_price_fields(self):
        form = CourseForm(data={
            'title': 'Open Source Software',
            'category': self.category.id,
            'level': 'beginner',
            'language': 'English',
            'is_free': True,
            'price': '99.00',
            'discount_price': '49.00',
            'description': 'Contributing to OSS.',
            'status': 'published',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['price'], Decimal('0.00'))
        self.assertIsNone(form.cleaned_data['discount_price'])


class CoursePricingViewsIntegrationTests(TestCase):
    """Integration tests for course enrollment and checkout routing based on pricing."""

    def setUp(self):
        self.client = Client()
        self.instructor = User.objects.create_user(
            username='instructor_bob',
            email='bob@example.com',
            password='Password123!',
            role='instructor',
        )
        self.student = User.objects.create_user(
            username='student_alice',
            email='alice@example.com',
            password='Password123!',
            role='student',
        )
        self.free_course = Course.objects.create(
            title='Free Python Basics',
            slug='free-python-basics',
            instructor=self.instructor,
            is_free=True,
            price=Decimal('0.00'),
            description='Learn Python 3 from scratch.',
            status=Course.Status.PUBLISHED,
        )
        self.paid_course = Course.objects.create(
            title='Mastering Distributed Systems',
            slug='mastering-distributed-systems',
            instructor=self.instructor,
            is_free=False,
            price=Decimal('100.00'),
            discount_price=Decimal('75.00'),
            description='Consensus, Raft, and Paxos.',
            status=Course.Status.PUBLISHED,
        )

    def test_course_detail_shows_pricing(self):
        # Paid course shows discount price and savings
        res = self.client.get(reverse('courses:course_detail', kwargs={'slug': self.paid_course.slug}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '$75.00')
        self.assertContains(res, '$100.00')
        self.assertContains(res, 'Save $25.00')

        # Free course shows Free
        res_free = self.client.get(reverse('courses:course_detail', kwargs={'slug': self.free_course.slug}))
        self.assertEqual(res_free.status_code, 200)
        self.assertContains(res_free, 'Free')

    def test_student_enroll_free_course_success(self):
        self.client.login(username='student_alice', password='Password123!')
        res = self.client.get(reverse('enrollments:enroll', kwargs={'course_slug': self.free_course.slug}))
        self.assertRedirects(res, reverse('courses:course_detail', kwargs={'slug': self.free_course.slug}))
        self.assertTrue(Enrollment.objects.filter(student=self.student, course=self.free_course).exists())

    def test_student_enroll_paid_course_redirects_to_checkout(self):
        self.client.login(username='student_alice', password='Password123!')
        res = self.client.get(reverse('enrollments:enroll', kwargs={'course_slug': self.paid_course.slug}))
        # Must redirect to payments:checkout, preventing payment bypass!
        expected_checkout_url = reverse('payments:checkout', kwargs={'course_slug': self.paid_course.slug})
        self.assertRedirects(res, expected_checkout_url)
        self.assertFalse(Enrollment.objects.filter(student=self.student, course=self.paid_course).exists())
