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

    def test_purchased_course_price_hidden_everywhere_except_personal_profile(self):
        """Once a student buys a course, prices are hidden on public pages/search and shown only on their personal profile."""
        from payments.models import Order

        # Anonymous user sees the course price across catalog, detail, instructor page, and search API
        res_anon_list = self.client.get(reverse('courses:course_list'))
        self.assertContains(res_anon_list, '$75.00')

        res_anon_suggest = self.client.get(reverse('courses:course_suggest'), {'q': 'Distributed Systems'})
        self.assertEqual(res_anon_suggest.status_code, 200)
        anon_data = res_anon_suggest.json()['suggestions'][0]
        self.assertFalse(anon_data['is_enrolled'])
        self.assertEqual(anon_data['price'], '75.00')

        # Student buys the paid course via completed order + enrollment
        order = Order.objects.create(
            user=self.student,
            course=self.paid_course,
            original_amount=Decimal('75.00'),
            discount_amount=Decimal('0.00'),
            final_amount=Decimal('75.00'),
            status=Order.Status.COMPLETED,
            transaction_id='TXN-TEST-OWNED1',
        )
        Enrollment.objects.create(student=self.student, course=self.paid_course)

        # Log in as buyer
        self.client.login(username='student_alice', password='Password123!')

        # 1. Course catalog hides price and promo discount % badge for the purchased course
        res_list = self.client.get(reverse('courses:course_list'))
        self.assertEqual(res_list.status_code, 200)
        self.assertNotContains(res_list, '$75.00')
        self.assertNotContains(res_list, '$100.00')
        self.assertContains(res_list, 'Enrolled')

        # 2. Course detail hides price for the purchased course
        res_detail = self.client.get(reverse('courses:course_detail', kwargs={'slug': self.paid_course.slug}))
        self.assertEqual(res_detail.status_code, 200)
        self.assertNotContains(res_detail, '$75.00')
        self.assertNotContains(res_detail, '$100.00')
        self.assertContains(res_detail, 'ENROLLED')

        # 3. Instructor detail page hides price for the purchased course
        res_inst = self.client.get(reverse('accounts:instructor_detail', kwargs={'username': self.instructor.username}))
        self.assertEqual(res_inst.status_code, 200)
        self.assertNotContains(res_inst, '$75.00')
        self.assertNotContains(res_inst, '$100.00')
        self.assertContains(res_inst, 'Enrolled')

        # 4. Search autocomplete API hides price for the purchased course
        res_suggest = self.client.get(reverse('courses:course_suggest'), {'q': 'Distributed Systems'})
        self.assertEqual(res_suggest.status_code, 200)
        buyer_data = res_suggest.json()['suggestions'][0]
        self.assertTrue(buyer_data['is_enrolled'])
        self.assertIsNone(buyer_data['price'])

        # 5. Buyer's Personal Profile shows the purchased course and its price
        res_profile = self.client.get(reverse('accounts:profile'))
        self.assertEqual(res_profile.status_code, 200)
        self.assertContains(res_profile, self.paid_course.title)
        self.assertContains(res_profile, '$75.00')
        self.assertContains(res_profile, order.order_id)

        # 6. Another user who has NOT bought the course still sees the public price and nothing in their profile
        other_user = User.objects.create_user(
            username='student_bob2',
            email='bob2@example.com',
            password='Password123!',
            role='student',
        )
        other_client = Client()
        other_client.login(username='student_bob2', password='Password123!')
        res_other_detail = other_client.get(reverse('courses:course_detail', kwargs={'slug': self.paid_course.slug}))
        self.assertContains(res_other_detail, '$75.00')
        res_other_profile = other_client.get(reverse('accounts:profile'))
        self.assertNotContains(res_other_profile, '$75.00')
        self.assertNotContains(res_other_profile, order.order_id)


class CurriculumModuleProgressionAndShortVideoTests(TestCase):
    """Tests structured modules/lectures, short video metadata, progress calculation, and sequential module unlocking."""

    def setUp(self):
        self.client = Client()
        self.instructor = User.objects.create_user(
            username='prof_curriculum',
            email='prof_curr@example.com',
            password='Password123!',
            role='instructor',
        )
        self.student = User.objects.create_user(
            username='student_curriculum',
            email='stud_curr@example.com',
            password='Password123!',
            role='student',
        )
        self.course = Course.objects.create(
            title='Structured Curriculum Course',
            slug='structured-curriculum-course',
            instructor=self.instructor,
            is_free=True,
            status=Course.Status.PUBLISHED,
        )

        from courses.models import Module
        from lessons.models import Lesson
        from quizzes.models import Quiz

        self.mod1 = Module.objects.create(course=self.course, title='Module 1: Foundations', order=1)
        self.mod2 = Module.objects.create(course=self.course, title='Module 2: Advanced Topics', order=2)

        self.les1 = Lesson.objects.create(
            course=self.course,
            module=self.mod1,
            title='Lecture 1A: Intro Video',
            order=1,
            lesson_type=Lesson.LessonType.VIDEO,
            video_url='https://youtu.be/xAcTmDO6NTI?si=test',
        )
        self.les2 = Lesson.objects.create(
            course=self.course,
            module=self.mod1,
            title='Lecture 1B: Reading',
            order=2,
            lesson_type=Lesson.LessonType.ARTICLE,
            text_content='Detailed study notes for module 1.',
        )
        self.les3 = Lesson.objects.create(
            course=self.course,
            module=self.mod2,
            title='Lecture 2A: Deep Dive Video',
            order=3,
            lesson_type=Lesson.LessonType.VIDEO,
            video_url='https://youtu.be/dQw4w9WgXcQ',
        )
        self.quiz2 = Quiz.objects.create(
            course=self.course,
            module=self.mod2,
            title='Module 2 Checkpoint Quiz',
        )
        Enrollment.objects.create(student=self.student, course=self.course)

    def test_module_1_unlocked_module_2_locked_until_module_1_complete(self):
        self.client.login(username='student_curriculum', password='Password123!')

        # Initial curriculum page: Module 1 unlocked with short video embed URL; Module 2 locked
        res = self.client.get(reverse('courses:course_detail', kwargs={'slug': self.course.slug}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Module 1: Foundations')
        self.assertContains(res, 'Module 2: Advanced Topics')
        self.assertContains(res, 'https://www.youtube.com/embed/xAcTmDO6NTI')
        self.assertNotContains(res, 'https://www.youtube.com/embed/dQw4w9WgXcQ')
        self.assertContains(res, '0% (0/4)')

        # Direct access to Module 2 lesson or quiz is blocked while Module 1 is incomplete
        res_les3 = self.client.get(reverse('lessons:lesson_detail', args=[self.course.slug, self.les3.id]))
        self.assertEqual(res_les3.status_code, 302)
        res_quiz2 = self.client.get(reverse('quizzes:quiz_detail', args=[self.quiz2.pk]))
        self.assertEqual(res_quiz2.status_code, 302)
        res_lock_api = self.client.post(reverse('lessons:mark_completed_api', args=[self.les3.id]))
        self.assertEqual(res_lock_api.status_code, 403)

        # Complete Lecture 1A (partial Module 1 progress -> Module 2 remains locked)
        r1 = self.client.post(reverse('lessons:mark_completed_api', args=[self.les1.id]))
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        self.assertFalse(d1['module_completed'])
        self.assertIsNone(d1['unlocked_next_module'])
        self.assertEqual(d1['module_progress_percent'], 50)
        self.assertEqual(d1['overall_progress_percent'], 25)

        # Complete Lecture 1B -> Module 1 reaches 100% and automatically unlocks Module 2
        r2 = self.client.post(reverse('lessons:mark_completed_api', args=[self.les2.id]))
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertTrue(d2['module_completed'])
        self.assertEqual(d2['module_progress_percent'], 100)
        self.assertEqual(d2['overall_progress_percent'], 50)
        self.assertEqual(d2['unlocked_next_module']['id'], self.mod2.id)

        # Now Module 2 video short-window URL, lesson detail, and quiz are all unlocked
        res_after = self.client.get(reverse('courses:course_detail', kwargs={'slug': self.course.slug}))
        self.assertContains(res_after, 'https://www.youtube.com/embed/dQw4w9WgXcQ')
        self.assertContains(res_after, '50% (2/4)')

        res_les3_ok = self.client.get(reverse('lessons:lesson_detail', args=[self.course.slug, self.les3.id]))
        self.assertEqual(res_les3_ok.status_code, 200)
        res_quiz2_ok = self.client.get(reverse('quizzes:quiz_detail', args=[self.quiz2.pk]))
        self.assertEqual(res_quiz2_ok.status_code, 200)

    def test_instructor_can_add_module_from_course_detail(self):
        from courses.models import Module

        self.client.login(username='prof_curriculum', password='Password123!')
        res = self.client.post(
            reverse('courses:module_create', kwargs={'slug': self.course.slug}),
            {'title': 'Module 3: Capstone', 'description': 'Final project work', 'order': 3},
            follow=True,
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(Module.objects.filter(course=self.course, title='Module 3: Capstone', order=3).exists())
        self.assertContains(res, 'Module 3: Capstone')
