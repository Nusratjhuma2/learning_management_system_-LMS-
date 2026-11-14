import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from assignments.models import Assignment, AssignmentSubmission
from courses.models import Category, Course, CoursePrerequisite, Module
from discussions.models import CourseAnnouncement, DiscussionReply, DiscussionThread
from enrollments.models import Badge, Certificate, Enrollment, StudentBadge
from enrollments.services.certificate_service import generate_certificate_pdf
from lessons.models import Lesson, LessonProgress
from lessons.services.hls_transcoder import generate_aes_key, generate_aes_iv
from payments.models import Coupon, Order, PaymentTransaction
from quizzes.models import Choice, Question, Quiz, QuizAttempt, QuizAttemptAnswer

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds comprehensive Enterprise LMS demo data with pure SQLite configuration."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("--> Seeding Enterprise LMS Demo Data..."))

        # 1. Accounts
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@enterprise.lms',
                'first_name': 'System',
                'last_name': 'Administrator',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin_user.set_password('admin12345')
        admin_user.save()

        instructor, _ = User.objects.get_or_create(
            username='instructor1',
            defaults={
                'email': 'instructor@enterprise.lms',
                'first_name': 'Dr. Alan',
                'last_name': 'Turing',
                'role': 'instructor',
                'bio': 'Senior Distributed Systems Architect & Security Researcher.',
                'is_staff': True,
            }
        )
        instructor.set_password('instructor123')
        instructor.save()

        student, _ = User.objects.get_or_create(
            username='student1',
            defaults={
                'email': 'student@enterprise.lms',
                'first_name': 'Ada',
                'last_name': 'Lovelace',
                'role': 'student',
                'bio': 'Passionate computer science scholar.',
                'xp_points': 150,
                'streak_days': 5,
            }
        )
        student.set_password('student123')
        student.save()

        self.stdout.write(self.style.SUCCESS("[+] Users created: admin (admin12345), instructor1 (instructor123), student1 (student123)"))

        # 2. Badges
        b1, _ = Badge.objects.get_or_create(
            name="First Step",
            defaults={'description': "Enrolled in your first academic curriculum.", 'icon': "🌱", 'xp_required': 0}
        )
        b2, _ = Badge.objects.get_or_create(
            name="Master Learner",
            defaults={'description': "Completed a certified curriculum with distinction.", 'icon': "🏆", 'xp_required': 100}
        )
        b3, _ = Badge.objects.get_or_create(
            name="Security Specialist",
            defaults={'description': "Demonstrated excellence in anti-tamper security.", 'icon': "🛡️", 'xp_required': 200}
        )
        StudentBadge.objects.get_or_create(student=student, badge=b1)
        StudentBadge.objects.get_or_create(student=student, badge=b2)

        # 3. Categories & Courses
        cs_cat, _ = Category.objects.get_or_create(
            slug='computer-science',
            defaults={'name': 'Computer Science & Distributed Systems', 'description': 'Cloud computing, fault tolerance, and security.'}
        )

        course1, _ = Course.objects.get_or_create(
            slug='distributed-systems-architecture',
            defaults={
                'title': 'Enterprise Distributed Systems & Cloud Architecture',
                'category': cs_cat,
                'instructor': instructor,
                'description': 'A comprehensive graduate-level curriculum covering consensus protocols, high-availability data layers, and multi-region microservices.',
                'level': 'advanced',
                'language': 'English',
                'price': Decimal('99.00'),
                'discount_price': Decimal('49.00'),
                'is_free': False,
                'status': Course.Status.PUBLISHED,
                'what_you_will_learn': 'Master CAP Theorem, Raft Consensus, and Zero-Trust Architectures.',
                'requirements': 'Proficiency in systems programming and basic networking.',
            }
        )

        prereq_course, _ = Course.objects.get_or_create(
            slug='foundations-of-computing',
            defaults={
                'title': 'Foundations of Computer Systems & Networks',
                'category': cs_cat,
                'instructor': instructor,
                'description': 'Introductory systems computing and network primitives.',
                'level': 'beginner',
                'price': Decimal('0.00'),
                'is_free': True,
                'status': Course.Status.PUBLISHED,
            }
        )

        CoursePrerequisite.objects.get_or_create(
            course=course1,
            required_course=prereq_course,
        )

        prereq_mod, _ = Module.objects.get_or_create(
            course=prereq_course,
            order=1,
            defaults={'title': 'Module 1: Systems Fundamentals'}
        )
        Lesson.objects.get_or_create(
            course=prereq_course,
            module=prereq_mod,
            order=1,
            defaults={
                'title': '1.1 Binary Representation, Registers & Memory Bus',
                'lesson_type': 'video',
                'video_url': 'https://www.youtube.com/watch?v=k-Yaq8AHlFA',
                'duration_seconds': 300,
                'min_watch_percent': 85,
                'text_content': 'Fundamental introduction to machine computation, memory hierarchy, and register sets.',
            }
        )

        # 4. Modules & Lessons
        mod1, _ = Module.objects.get_or_create(
            course=course1,
            order=1,
            defaults={'title': 'Module 1: Principles of Consistency & Distributed Storage'}
        )
        mod2, _ = Module.objects.get_or_create(
            course=course1,
            order=2,
            defaults={'title': 'Module 2: High Availability, Security & Consensus'}
        )

        # Create demo encrypted HLS lesson
        lesson1, _ = Lesson.objects.get_or_create(
            course=course1,
            module=mod1,
            order=1,
            defaults={
                'title': '1.1 The CAP Theorem and Partition Tolerant Replication',
                'lesson_type': 'video',
                'video_url': 'https://www.youtube.com/watch?v=k-Yaq8AHlFA',
                'is_free_preview': True,
                'duration_seconds': 480,
                'min_watch_percent': 85,
                'aes_key': generate_aes_key(),
                'aes_iv': generate_aes_iv(),
                'text_content': 'In this lecture, we examine Eric Brewer’s CAP Theorem and dissect linearizable consistency models.',
            }
        )

        lesson2, _ = Lesson.objects.get_or_create(
            course=course1,
            module=mod1,
            order=2,
            defaults={
                'title': '1.2 Fault-Tolerant State Machine Replication',
                'lesson_type': 'video',
                'video_url': 'https://www.youtube.com/watch?v=YbZ3zDzDnrw',
                'is_free_preview': False,
                'duration_seconds': 600,
                'min_watch_percent': 85,
                'aes_key': generate_aes_key(),
                'aes_iv': generate_aes_iv(),
                'text_content': 'Understanding Paxos vs Raft state transitions during network partitions.',
            }
        )

        # 5. Quiz with multiple question types
        quiz, _ = Quiz.objects.get_or_create(
            course=course1,
            module=mod1,
            title='Distributed Systems Architecture Examination',
            defaults={
                'description': 'Monitored assessment covering consensus theorems, fault tolerance, and replica models.',
                'time_limit_minutes': 15,
                'pass_mark_percent': 70,
                'max_attempts': 3,
                'enforce_anticheat': True,
                'shuffle_questions': True,
                'shuffle_choices': True,
            }
        )

        if not quiz.questions.exists():
            # Q1: Single Choice
            q1 = Question.objects.create(
                quiz=quiz,
                text="Which theorem states that a distributed data store can simultaneously provide at most two out of three guarantees: Consistency, Availability, and Partition Tolerance?",
                question_type='single_choice',
                points=2,
                order=1,
                explanation="Brewer's CAP Theorem demonstrates the fundamental trade-off between Consistency, Availability, and Partition tolerance in distributed networks."
            )
            Choice.objects.create(question=q1, text="CAP Theorem", is_correct=True)
            Choice.objects.create(question=q1, text="PACELC Theorem", is_correct=False)
            Choice.objects.create(question=q1, text="Amdahl's Law", is_correct=False)
            Choice.objects.create(question=q1, text="Moore's Law", is_correct=False)

            # Q2: Multiple Choice
            q2 = Question.objects.create(
                quiz=quiz,
                text="Select all fundamental attributes of a resilient cloud-native distributed architecture:",
                question_type='multiple_choice',
                points=3,
                order=2,
                explanation="Fault tolerance, horizontal scaling, and network partition resilience are hallmarks of resilient distributed architectures."
            )
            Choice.objects.create(question=q2, text="Byzantine Fault Tolerance", is_correct=True)
            Choice.objects.create(question=q2, text="Dynamic Horizontal Scalability", is_correct=True)
            Choice.objects.create(question=q2, text="Single Central Point of Failure", is_correct=False)
            Choice.objects.create(question=q2, text="Network Partition Resilience", is_correct=True)

            # Q3: True/False
            q3 = Question.objects.create(
                quiz=quiz,
                text="In an eventual consistency model, if no new updates are made to a data item, all accesses will eventually return the last updated value.",
                question_type='true_false',
                points=2,
                order=3,
                explanation="Eventual consistency guarantees convergence given a sufficient quiescence period."
            )
            Choice.objects.create(question=q3, text="True", is_correct=True)
            Choice.objects.create(question=q3, text="False", is_correct=False)

            # Q4: Short Answer
            Question.objects.create(
                quiz=quiz,
                text="Which distributed consensus algorithm decomposes consensus into leader election, log replication, and safety?",
                question_type='short_answer',
                points=3,
                short_answer_solution="raft",
                order=4,
                explanation="The Raft consensus algorithm was explicitly formulated for comprehensibility compared to Multi-Paxos."
            )

        # 6. Assignment
        assign, _ = Assignment.objects.get_or_create(
            course=course1,
            module=mod2,
            title="Consensus Node Implementation & RPC Load Balancer",
            defaults={
                'description': 'Develop a 3-node cluster prototype in Python or Go utilizing heartbeat signals and leader election logic. Submit your GitHub repository URL and benchmarking documentation.',
                'max_score': 100,
                'repo_url_required': True,
                'due_date': timezone.now() + timezone.timedelta(days=14),
            }
        )

        # 7. Student Enrollment & Completed Prerequisite Course
        Enrollment.objects.get_or_create(
            student=student,
            course=prereq_course,
            defaults={
                'is_completed': True,
                'completed': True,
                'progress_percent': Decimal('100.00'),
                'completed_at': timezone.now(),
            }
        )

        # Enroll student in course1
        enr1, _ = Enrollment.objects.get_or_create(
            student=student,
            course=course1,
            defaults={
                'progress_percent': Decimal('50.00'),
            }
        )

        # 8. Promotional Coupons
        Coupon.objects.get_or_create(
            code="WELCOME100",
            defaults={
                'discount_percent': 100,
                'max_uses': 500,
                'is_active': True,
            }
        )
        Coupon.objects.get_or_create(
            code="SAVE20",
            defaults={
                'discount_percent': 20,
                'max_uses': 1000,
                'is_active': True,
            }
        )

        # 9. Announcements & Discussions
        CourseAnnouncement.objects.get_or_create(
            course=course1,
            instructor=instructor,
            title="Welcome to Advanced Distributed Systems 2026 Academic Term!",
            defaults={
                'content': 'Welcome everyone! Lectures 1.1 and 1.2 are now available with AES-128 secure playback. Review the syllabus and guidelines.',
            }
        )

        thread, _ = DiscussionThread.objects.get_or_create(
            course=course1,
            lesson=lesson1,
            author=student,
            title="Clarification regarding network split recovery in Raft",
            defaults={
                'content': 'When a network partition heals and two clusters reconnect, how does Raft resolve conflicting log indices between stale and current leaders?',
                'is_resolved': True,
            }
        )
        DiscussionReply.objects.get_or_create(
            thread=thread,
            author=instructor,
            defaults={
                'content': 'The term number governs authority. Nodes compare terms, and the leader with the highest term and longer log forces uncommitted entries in the stale partition to be overwritten.',
                'is_instructor_reply': True,
                'is_instructor_solution': True,
            }
        )

        self.stdout.write(self.style.SUCCESS("--> Successfully populated Enterprise LMS Demo Seed Data!"))

