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
