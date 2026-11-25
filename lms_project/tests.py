import json
import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.signing import TimestampSigner
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ActiveUserSession, SecurityAuditLog
from courses.models import Category, Course
from enrollments.models import Certificate, Enrollment
from enrollments.services.certificate_service import update_enrollment_progress
from lessons.models import Lesson, LessonProgress
from lessons.services.hls_transcoder import generate_aes_key, generate_aes_iv
from quizzes.models import Choice, Question, Quiz, QuizAttempt

User = get_user_model()


class EnterpriseLMSTestSuite(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Computer Science", slug="cs")
        self.instructor = User.objects.create_user(
            username="instructor_test",
            password="password123",
            role="instructor",
            email="instructor@test.local",
        )
        self.student = User.objects.create_user(
            username="student_test",
            password="password123",
            role="student",
            email="student@test.local",
        )
        self.other_student = User.objects.create_user(
            username="other_student",
            password="password123",
            role="student",
            email="other@test.local",
        )
        self.course = Course.objects.create(
            title="Distributed Systems Test Course",
            slug="distributed-systems-test",
            category=self.category,
            instructor=self.instructor,
            price=Decimal("50.00"),
            is_free=False,
            status=Course.Status.PUBLISHED,
        )
        self.lesson = Lesson.objects.create(
            course=self.course,
            title="Test Lecture 1",
            order=1,
            lesson_type="video",
            duration_seconds=100,
            min_watch_percent=85,
            aes_key=generate_aes_key(),
            aes_iv=generate_aes_iv(),
        )

    def test_single_session_enforcement(self):
        """
        Verify that a second login by the same user invalidates the first session,
        logging out the initial device via SingleSessionEnforcementMiddleware.
        """
        client1 = Client()
        client2 = Client()

        # Login Device 1
        login1_ok = client1.login(username="student_test", password="password123")
        self.assertTrue(login1_ok)
        session1_key = client1.session.session_key

        # Verify device 1 active session registered
        active_sess = ActiveUserSession.objects.get(user=self.student)
        self.assertEqual(active_sess.session_key, session1_key)

        # Device 1 can browse authenticated pages
        resp1 = client1.get(reverse('courses:course_list'))
        self.assertEqual(resp1.status_code, 200)

        # Login Device 2 with same credentials
        login2_ok = client2.login(username="student_test", password="password123")
        self.assertTrue(login2_ok)
        session2_key = client2.session.session_key
        self.assertNotEqual(session1_key, session2_key)

        # Active session updated to device 2
        active_sess.refresh_from_db()
        self.assertEqual(active_sess.session_key, session2_key)

        # Device 1 tries to make another request -> kicked out and redirected to login
        resp1_kicked = client1.get(reverse('courses:course_list'))
        self.assertEqual(resp1_kicked.status_code, 302)
        self.assertIn('/accounts/login/', resp1_kicked.url)

        # Device 2 continues unaffected
        resp2 = client2.get(reverse('courses:course_list'))
        self.assertEqual(resp2.status_code, 200)

    def test_hls_security_authorization(self):
        """
        Verify that unenrolled users are forbidden (403) from accessing HLS manifests,
        while enrolled students receive valid 200 playlists.
        """
        from pathlib import Path
        from lessons.services.hls_transcoder import get_private_media_root

        # Set up mock manifest on disk for test lecture
        private_root = Path(get_private_media_root())
        hls_dir = private_root / 'hls' / str(self.lesson.id)
        hls_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = hls_dir / 'index.m3u8'
        with open(manifest_file, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n#EXT-X-KEY:METHOD=AES-128,URI=\"key.bin\",IV=0x1234567890abcdef1234567890abcdef\n#EXTINF:10.0,\nsegment0.ts\n#EXT-X-ENDLIST\n")

        self.lesson.hls_playlist_relpath = f"hls/{self.lesson.id}/index.m3u8"
        self.lesson.save()

        client = Client()
        client.login(username="other_student", password="password123")

        signer = TimestampSigner(salt='hls')
        signed_token = signer.sign(f"{self.other_student.id}:{self.lesson.id}")

        manifest_url = reverse('lessons:hls_manifest', args=[self.course.slug, self.lesson.id])

        # Unenrolled access returns 403 Forbidden
        resp_unenrolled = client.get(f"{manifest_url}?token={signed_token}")
        self.assertEqual(resp_unenrolled.status_code, 403)

        # Enroll student in the course
        Enrollment.objects.create(student=self.other_student, course=self.course)

        # Enrolled access returns 200 OK with HLS content-type
        resp_enrolled = client.get(f"{manifest_url}?token={signed_token}")
        self.assertEqual(resp_enrolled.status_code, 200)
        self.assertIn("application/vnd.apple.mpegurl", resp_enrolled['Content-Type'])

    def test_progress_engine_and_certificate_issuance(self):
        """
        Verify that 100% course completion triggers automatic accreditation,
        creates a verifiable Certificate, and awards 100 XP to the candidate.
        """
        # Enroll student
        enrollment = Enrollment.objects.create(student=self.student, course=self.course)

        # Complete the lesson
        LessonProgress.objects.create(
            student=self.student,
            lesson=self.lesson,
            is_completed=True,
            watched_seconds=100,
        )

        initial_xp = self.student.xp_points or 0
        update_enrollment_progress(self.student, self.course)

        enrollment.refresh_from_db()
        self.assertTrue(enrollment.is_completed)
        self.assertEqual(enrollment.progress_percent, Decimal('100.00'))

        # Verify Certificate generated
        self.assertTrue(hasattr(enrollment, 'certificate'))
        cert = enrollment.certificate
        self.assertIsNotNone(cert.certificate_uid)
        self.assertTrue(cert.certificate_id.startswith('CERT-'))

        # Verify candidate XP awarded
        self.student.refresh_from_db()
        self.assertEqual(self.student.xp_points, initial_xp + 100)

        # Verify public certificate verification endpoint
        client = Client()
        verify_url = reverse('enrollments:verify_certificate', args=[cert.certificate_uid])
        verify_resp = client.get(verify_url)
        self.assertEqual(verify_resp.status_code, 200)
        self.assertContains(verify_resp, cert.certificate_id)
        self.assertContains(verify_resp, "Valid Accreditation")

    def test_quiz_anticheat_disqualification(self):
        """
        Verify that a student who commits >= 3 tab-switch violations during a proctored assessment
        is automatically disqualified with a score of 0.0%.
        """
        client = Client()
        client.login(username="student_test", password="password123")

        # Enroll student so they can take the quiz
        Enrollment.objects.create(student=self.student, course=self.course)

        quiz = Quiz.objects.create(
            course=self.course,
            title="Anti-Cheat Test Assessment",
            time_limit_minutes=10,
            pass_mark_percent=70,
            enforce_anticheat=True,
        )

        q1 = Question.objects.create(
            quiz=quiz,
            text="Test Question 1",
            question_type="single_choice",
            points=1,
        )
        c1 = Choice.objects.create(question=q1, text="Correct Option", is_correct=True)

        # Submit with tab_switch_count = 3 (disqualification trigger)
        submit_url = reverse('quizzes:quiz_submit', args=[quiz.pk])
        resp = client.post(submit_url, {
            f'question_{q1.pk}': c1.pk,
            'tab_switch_count': '3',
            'is_disqualified': 'true',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)

        # Verify attempt recorded as disqualified
        attempt = QuizAttempt.objects.filter(quiz=quiz, student=self.student).first()
        self.assertIsNotNone(attempt)
        self.assertTrue(attempt.is_disqualified)
        self.assertEqual(attempt.score, 0.0)
        self.assertFalse(attempt.passed)
        self.assertEqual(attempt.tab_switch_count, 3)


class RoleIsolationAndGovernanceTests(TestCase):
    """
    Verifies strict role-based actor isolation across Student, Instructor, and Admin,
    plus Admin platform governance overrides.
    """

    def setUp(self):
        from assignments.models import Assignment, AssignmentSubmission
        from courses.models import CourseReview, Wishlist
        from discussions.models import CourseAnnouncement, DiscussionThread
        from payments.models import Order

        self.Assignment = Assignment
        self.AssignmentSubmission = AssignmentSubmission
        self.CourseReview = CourseReview
        self.Wishlist = Wishlist
        self.CourseAnnouncement = CourseAnnouncement
        self.DiscussionThread = DiscussionThread
        self.Order = Order

        self.category = Category.objects.create(name="Software Engineering", slug="swe")
        self.student = User.objects.create_user(
            username="role_student",
            password="Password123!",
            role=User.Role.STUDENT,
            email="r_stud@test.local",
        )
        self.outsider_student = User.objects.create_user(
            username="role_outsider",
            password="Password123!",
            role=User.Role.STUDENT,
            email="r_out@test.local",
        )
        self.instructor = User.objects.create_user(
            username="role_instructor",
            password="Password123!",
            role=User.Role.INSTRUCTOR,
            email="r_inst@test.local",
        )
        self.other_instructor = User.objects.create_user(
            username="role_other_instructor",
            password="Password123!",
            role=User.Role.INSTRUCTOR,
            email="r_other_inst@test.local",
        )
        self.admin_user = User.objects.create_user(
            username="role_admin",
            password="Password123!",
            role=User.Role.ADMIN,
            email="r_admin@test.local",
        )

        self.free_course = Course.objects.create(
            title="Free Systems Course",
            slug="free-systems-course",
            category=self.category,
            instructor=self.instructor,
            price=Decimal("0.00"),
            is_free=True,
            status=Course.Status.PUBLISHED,
        )
        self.paid_course = Course.objects.create(
            title="Paid Architecture Course",
            slug="paid-architecture-course",
            category=self.category,
            instructor=self.instructor,
            price=Decimal("90.00"),
            is_free=False,
            status=Course.Status.PUBLISHED,
        )
        self.lesson = Lesson.objects.create(
            course=self.free_course,
            title="Core Lecture 1",
            order=1,
            lesson_type=Lesson.LessonType.ARTICLE,
            text_content="Architecture foundations and distributed consensus.",
        )
        self.quiz = Quiz.objects.create(
            course=self.free_course,
            title="Core Quiz",
            pass_mark_percent=50,
            enforce_anticheat=False,
        )
        self.question = Question.objects.create(
            quiz=self.quiz,
            text="Is consensus important?",
            question_type="true_false",
            points=1,
        )
        Choice.objects.create(question=self.question, text="True", is_correct=True)
        Choice.objects.create(question=self.question, text="False", is_correct=False)
        self.assignment = Assignment.objects.create(
            course=self.free_course,
            title="Architecture Essay",
            description="Write a brief design doc.",
            max_score=100,
        )

        Enrollment.objects.create(student=self.student, course=self.free_course)

    def test_dashboards_and_topbar_strictly_isolated_by_role(self):
        # Student dashboard: only student allowed
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('dashboard:student_dashboard')).status_code, 200)
        self.assertRedirects(
            self.client.get(reverse('dashboard:instructor_dashboard')),
            reverse('dashboard:student_dashboard'),
        )
        self.assertRedirects(
            self.client.get(reverse('dashboard:admin_dashboard')),
            reverse('dashboard:student_dashboard'),
        )

        # Instructor dashboard: only instructor allowed
        self.client.force_login(self.instructor)
        self.assertEqual(self.client.get(reverse('dashboard:instructor_dashboard')).status_code, 200)
        self.assertRedirects(
            self.client.get(reverse('dashboard:student_dashboard')),
            reverse('dashboard:instructor_dashboard'),
        )
        self.assertRedirects(
            self.client.get(reverse('dashboard:admin_dashboard')),
            reverse('dashboard:instructor_dashboard'),
        )

        # Admin dashboard: only admin allowed (even non-superuser role='admin')
        self.client.force_login(self.admin_user)
        admin_res = self.client.get(reverse('dashboard:admin_dashboard'))
        self.assertEqual(admin_res.status_code, 200)
        self.assertNotContains(admin_res, reverse('enrollments:my_courses'))
        self.assertNotContains(admin_res, reverse('enrollments:my_certificates'))
        self.assertRedirects(
            self.client.get(reverse('dashboard:student_dashboard')),
            reverse('dashboard:admin_dashboard'),
        )
        self.assertRedirects(
            self.client.get(reverse('dashboard:instructor_dashboard')),
            reverse('dashboard:admin_dashboard'),
        )
        self.assertEqual(self.client.get(reverse('dashboard:admin_dashboard_api')).status_code, 200)

    def test_profile_and_catalog_ui_scoped_by_role(self):
        # Student sees Purchased & Enrolled Courses on profile and Enroll/Purchase on catalog
        self.client.force_login(self.student)
        stud_prof = self.client.get(reverse('accounts:profile'))
        self.assertContains(stud_prof, 'My Purchased &amp; Enrolled Courses')
        stud_cat = self.client.get(reverse('courses:course_list'))
        self.assertContains(stud_cat, 'Purchase &rarr;')

        # Instructor & Admin do not see student purchase ledger or student enroll/purchase buttons
        for actor in (self.instructor, self.admin_user):
            self.client.force_login(actor)
            prof_res = self.client.get(reverse('accounts:profile'))
            self.assertEqual(prof_res.status_code, 200)
            self.assertNotContains(prof_res, 'My Purchased &amp; Enrolled Courses')

            cat_res = self.client.get(reverse('courses:course_list'))
            self.assertEqual(cat_res.status_code, 200)
            self.assertNotContains(cat_res, 'Enroll Free')
            self.assertNotContains(cat_res, 'Purchase &rarr;')

            det_res = self.client.get(reverse('courses:course_detail', args=[self.paid_course.slug]))
            self.assertEqual(det_res.status_code, 200)
            self.assertNotContains(det_res, 'Add to Wishlist')
            self.assertNotContains(det_res, 'Purchase &amp; Enroll Now')

    def test_student_only_actions_blocked_for_instructors_and_admins(self):
        for actor in (self.instructor, self.other_instructor, self.admin_user):
            self.client.force_login(actor)

            # Enroll / unenroll / my_courses / my_certificates
            self.client.get(reverse('enrollments:enroll', args=[self.free_course.slug]))
            self.assertFalse(Enrollment.objects.filter(student=actor, course=self.free_course).exists())
            self.assertEqual(self.client.get(reverse('enrollments:my_courses')).status_code, 302)
            self.assertEqual(self.client.get(reverse('enrollments:my_certificates')).status_code, 302)

            # Checkout / order history
            self.assertEqual(self.client.get(reverse('payments:checkout', args=[self.paid_course.slug])).status_code, 302)
            self.assertFalse(self.Order.objects.filter(user=actor).exists())
            self.assertEqual(self.client.get(reverse('payments:order_history')).status_code, 302)

            # Wishlist & Course Review
            self.client.post(reverse('courses:toggle_wishlist', args=[self.paid_course.slug]))
            self.assertFalse(self.Wishlist.objects.filter(student=actor).exists())
            self.client.post(reverse('courses:add_review', args=[self.free_course.slug]), {'rating': 5, 'comment': 'Great'})
            self.assertFalse(self.CourseReview.objects.filter(student=actor).exists())

            # Lesson progress & notes
            self.assertEqual(self.client.post(reverse('lessons:mark_completed_api', args=[self.lesson.id])).status_code, 403)
            self.assertEqual(
                self.client.post(
                    reverse('lessons:heartbeat_api', args=[self.lesson.id]),
                    data=json.dumps({'current_position': 10, 'delta_watched': 10}),
                    content_type='application/json',
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    reverse('lessons:save_note_api', args=[self.lesson.id]),
                    data=json.dumps({'timestamp_seconds': 5, 'note_text': 'Should fail'}),
                    content_type='application/json',
                ).status_code,
                403,
            )
            self.assertFalse(LessonProgress.objects.filter(student=actor).exists())

            # Quiz taking & Assignment submission
            self.client.get(reverse('quizzes:quiz_detail', args=[self.quiz.pk]) + '?action=start')
            self.client.post(reverse('quizzes:quiz_submit', args=[self.quiz.pk]), {})
            self.assertFalse(QuizAttempt.objects.filter(student=actor).exists())
            self.assertEqual(
                self.client.post(
                    reverse('quizzes:log_tab_switch', args=[self.quiz.pk]),
                    data=json.dumps({'tab_switch_count': 1}),
                    content_type='application/json',
                ).status_code,
                403,
            )

            self.client.post(
                reverse('assignments:submit_assignment', args=[self.assignment.pk]),
                {'submission_text': 'Non-student submission'},
            )
            self.assertFalse(self.AssignmentSubmission.objects.filter(student=actor).exists())

    def test_instructor_ownership_isolation_and_admin_override(self):
        # Other instructor cannot edit/delete/add module/add lesson/block/create quiz/grade on instructor's course
        self.client.force_login(self.other_instructor)
        self.assertEqual(
            self.client.get(reverse('courses:course_update', args=[self.free_course.slug])).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(reverse('courses:module_create', args=[self.free_course.slug]), {'title': 'Hijack'}).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(reverse('courses:toggle_block', args=[self.free_course.slug])).status_code,
            302,
        )
        self.assertEqual(
            self.client.get(reverse('lessons:lesson_create', args=[self.free_course.slug])).status_code,
            302,
        )
        self.assertEqual(
            self.client.get(reverse('quizzes:quiz_edit', args=[self.quiz.pk])).status_code,
            302,
        )
        self.assertEqual(
            self.client.get(reverse('assignments:submissions_list', args=[self.assignment.pk])).status_code,
            302,
        )

        # Owning instructor cannot block courses (Admin only)
        self.client.force_login(self.instructor)
        self.client.post(reverse('courses:toggle_block', args=[self.free_course.slug]))
        self.free_course.refresh_from_db()
        self.assertFalse(self.free_course.is_blocked)

        # Admin (even without superuser flag) CAN override: block/unblock, inspect lesson, edit quiz, list all assignments
        self.client.force_login(self.admin_user)
        self.client.post(reverse('courses:toggle_block', args=[self.free_course.slug]))
        self.free_course.refresh_from_db()
        self.assertTrue(self.free_course.is_blocked)

        # Blocked course cannot be enrolled or checked out by students
        self.client.force_login(self.outsider_student)
        self.assertEqual(self.client.get(reverse('enrollments:enroll', args=[self.free_course.slug])).status_code, 404)

        self.client.force_login(self.admin_user)
        self.client.post(reverse('courses:toggle_block', args=[self.free_course.slug]))
        self.free_course.refresh_from_db()
        self.assertFalse(self.free_course.is_blocked)

        self.assertEqual(
            self.client.get(reverse('lessons:lesson_detail', args=[self.free_course.slug, self.lesson.pk])).status_code,
            200,
        )
        self.assertEqual(self.client.get(reverse('quizzes:quiz_edit', args=[self.quiz.pk])).status_code, 200)
        inst_assigns = self.client.get(reverse('assignments:instructor_assignments'))
        self.assertEqual(inst_assigns.status_code, 200)
        self.assertContains(inst_assigns, self.assignment.title)

    def test_discussions_and_announcements_role_and_enrollment_isolation(self):
        thread = self.DiscussionThread.objects.create(
            course=self.free_course,
            lesson=self.lesson,
            author=self.student,
            title="Question about Consensus",
            content="How does Raft elect leaders?",
        )

        # Unenrolled student and non-owning instructor cannot view or post in discussions
        for user in (self.outsider_student, self.other_instructor):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('discussions:course_discussions', args=[self.free_course.slug])).status_code, 302)
            self.assertEqual(self.client.get(reverse('discussions:thread_detail', args=[thread.pk])).status_code, 302)
            self.assertEqual(
                self.client.post(
                    reverse('discussions:create_thread_api', args=[self.lesson.id]),
                    data=json.dumps({'title': 'Nope', 'body': 'Denied'}),
                    content_type='application/json',
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    reverse('discussions:reply_thread_api', args=[thread.pk]),
                    data=json.dumps({'body': 'Denied reply'}),
                    content_type='application/json',
                ).status_code,
                403,
            )

        # Enrolled student, owning instructor, and admin CAN participate; only instructor/admin can announce
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('discussions:thread_detail', args=[thread.pk])).status_code, 200)
        self.client.post(reverse('discussions:create_announcement', args=[self.free_course.slug]), {'title': 'Spam', 'content': 'No'})
        self.assertFalse(self.CourseAnnouncement.objects.exists())

        self.client.force_login(self.instructor)
        self.assertEqual(self.client.get(reverse('discussions:thread_detail', args=[thread.pk])).status_code, 200)
        self.client.post(
            reverse('discussions:create_announcement', args=[self.free_course.slug]),
            {'title': 'Exam Notice', 'content': 'Quiz opens Friday'},
        )
        self.assertTrue(self.CourseAnnouncement.objects.filter(title='Exam Notice').exists())

        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(reverse('discussions:thread_detail', args=[thread.pk])).status_code, 200)
