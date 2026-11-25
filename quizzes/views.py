import json
import random
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import deny_json, deny_role_redirect, is_course_manager, is_student_user
from courses.models import Course
from courses.services.curriculum import is_quiz_accessible_by_module
from .forms import QuestionForm, QuizForm
from .models import Choice, Question, Quiz, QuizAttempt, QuizAttemptAnswer


@login_required
def quiz_detail(request, pk):
    """
    Displays the quiz lobby or the active proctored quiz attempt.
    Enforces student enrollment, attempt limits, and sets up anti-cheat session.
    """
    quiz = get_object_or_404(
        Quiz.objects.select_related('course', 'course__instructor').prefetch_related('questions__choices'),
        pk=pk,
    )
    course = quiz.course
    is_manager = is_course_manager(request.user, course)
    is_student = is_student_user(request.user)
    is_enrolled = is_student and course.enrollments.filter(student=request.user).exists()

    if not is_enrolled and not is_manager:
        messages.error(request, "You must be enrolled in this course to access this assessment.")
        return redirect('courses:course_detail', slug=course.slug)

    if not is_manager:
        quiz_unlocked, lock_reason = is_quiz_accessible_by_module(quiz, request.user)
        if not quiz_unlocked:
            messages.warning(request, lock_reason or "This assessment is currently locked.")
            return redirect('courses:course_detail', slug=course.slug)

    past_attempts = (
        QuizAttempt.objects.filter(quiz=quiz, student=request.user).order_by('-started_at')
        if is_enrolled
        else QuizAttempt.objects.none()
    )
    attempt_count = past_attempts.count()
    has_passed = past_attempts.filter(passed=True).exists()
    attempts_exhausted = (quiz.max_attempts > 0 and attempt_count >= quiz.max_attempts)

    # Check if student clicked "Start Assessment"
    action = request.GET.get('action')
    if action == 'start' or request.method == 'POST':
        if not is_enrolled:
            return deny_role_redirect(
                request,
                "Only enrolled students can take assessments.",
                'quizzes:quiz_detail',
                pk=pk,
            )

        if attempts_exhausted:
            messages.error(request, f"You have reached the maximum allowed attempts ({quiz.max_attempts}) for this assessment.")
            return redirect('quizzes:quiz_detail', pk=pk)

        # Look for an incomplete active attempt started recently within time limit
        active_attempt = past_attempts.filter(submitted_at__isnull=True).first()
        now = timezone.now()

        if active_attempt:
            # Check if active attempt has already expired
            if quiz.time_limit_minutes > 0:
                elapsed_seconds = (now - active_attempt.started_at).total_seconds()
                max_seconds = quiz.time_limit_minutes * 60
                if elapsed_seconds > (max_seconds + 30):
                    # Expire past attempt
                    active_attempt.submitted_at = now
                    active_attempt.completed_at = now
                    active_attempt.score = 0
                    active_attempt.passed = False
                    active_attempt.save()
                    active_attempt = None

        if not active_attempt:
            active_attempt = QuizAttempt.objects.create(
                quiz=quiz,
                student=request.user,
                started_at=now,
            )

        # Prepare questions
        questions = list(quiz.questions.prefetch_related('choices').all())
        if quiz.shuffle_questions:
            random.seed(active_attempt.pk)
            random.shuffle(questions)

        for q in questions:
            choices = list(q.choices.all())
            if quiz.shuffle_choices and q.question_type in ['single_choice', 'multiple_choice']:
                random.seed(active_attempt.pk + q.pk)
                random.shuffle(choices)
            q.shuffled_choices = choices

        # Calculate seconds remaining
        seconds_remaining = 0
        if quiz.time_limit_minutes > 0:
            elapsed = (now - active_attempt.started_at).total_seconds()
            seconds_remaining = max(0, int((quiz.time_limit_minutes * 60) - elapsed))

        return render(request, 'quizzes/quiz_take.html', {
            'quiz': quiz,
            'course': course,
            'attempt': active_attempt,
            'questions': questions,
            'seconds_remaining': seconds_remaining,
            'enforce_anticheat': quiz.enforce_anticheat,
        })

    return render(request, 'quizzes/quiz_detail.html', {
        'quiz': quiz,
        'course': course,
        'is_instructor': is_manager,
        'is_enrolled': is_enrolled,
        'past_attempts': past_attempts,
        'attempt_count': attempt_count,
        'has_passed': has_passed,
        'attempts_exhausted': attempts_exhausted,
    })


@login_required
@require_POST
def quiz_submit(request, pk):
    """
    Grades student quiz submission supporting Single Choice, Multiple Choice,
    True/False, and Short Answer question types.
    Enforces student enrollment, module unlock, and anti-cheat tab-switch disqualification.
    """
    quiz = get_object_or_404(
        Quiz.objects.select_related('course').prefetch_related('questions__choices'),
        pk=pk,
    )
    course = quiz.course
    if not is_student_user(request.user):
        return deny_role_redirect(
            request,
            "Only enrolled students can submit quiz attempts.",
            'quizzes:quiz_detail',
            pk=pk,
        )
    if not course.enrollments.filter(student=request.user).exists():
        messages.error(request, "You must be enrolled in this course to submit this assessment.")
        return redirect('courses:course_detail', slug=course.slug)

    quiz_unlocked, lock_reason = is_quiz_accessible_by_module(quiz, request.user)
    if not quiz_unlocked:
        messages.warning(request, lock_reason or "This assessment is currently locked.")
        return redirect('courses:course_detail', slug=course.slug)

    attempt_id = request.POST.get('attempt_id')
    now = timezone.now()

    if attempt_id:
        attempt = QuizAttempt.objects.filter(pk=attempt_id, quiz=quiz, student=request.user).first()
    else:
        attempt = QuizAttempt.objects.filter(quiz=quiz, student=request.user, submitted_at__isnull=True).order_by('-started_at').first()

    if not attempt:
        attempt = QuizAttempt.objects.create(
            quiz=quiz,
            student=request.user,
            started_at=now,
        )

    # Disqualification check from frontend or repeated violations
    tab_switches = int(request.POST.get('tab_switch_count', '0') or '0')
    is_disqualified = request.POST.get('is_disqualified') == 'true' or tab_switches >= 3

    attempt.tab_switch_count = tab_switches
    attempt.is_disqualified = is_disqualified
    attempt.submitted_at = now
    attempt.completed_at = now

    questions = quiz.questions.all()
    total_points = sum(q.points for q in questions) or 1
    earned_points = 0.0

    if not is_disqualified:
        for question in questions:
            is_q_correct = False
            points_awarded = 0.0

            if question.question_type in ['single_choice', 'true_false']:
                selected_choice_id = request.POST.get(f'question_{question.pk}')
                selected_choice = None
                if selected_choice_id:
                    try:
                        selected_choice = Choice.objects.get(pk=selected_choice_id, question=question)
                        if selected_choice.is_correct:
                            is_q_correct = True
                            points_awarded = question.points
                    except Choice.DoesNotExist:
                        pass

                answer = QuizAttemptAnswer.objects.create(
                    attempt=attempt,
                    question=question,
                    selected_choice=selected_choice,
                    is_correct=is_q_correct,
                    points_awarded=points_awarded,
                )
                if selected_choice:
                    answer.selected_choices.add(selected_choice)

            elif question.question_type == 'multiple_choice':
                selected_ids = request.POST.getlist(f'question_{question.pk}')
                selected_choices = list(Choice.objects.filter(pk__in=selected_ids, question=question))
                correct_choices = list(question.choices.filter(is_correct=True))

                selected_set = set(c.pk for c in selected_choices)
                correct_set = set(c.pk for c in correct_choices)

                if selected_set == correct_set and len(correct_set) > 0:
                    is_q_correct = True
                    points_awarded = question.points

                answer = QuizAttemptAnswer.objects.create(
                    attempt=attempt,
                    question=question,
                    is_correct=is_q_correct,
                    points_awarded=points_awarded,
                )
                if selected_choices:
                    answer.selected_choices.set(selected_choices)

            elif question.question_type == 'short_answer':
                text_ans = request.POST.get(f'question_{question.pk}', '').strip()
                target_ans = (question.short_answer_solution or '').strip().lower()

                if target_ans and text_ans.lower() == target_ans:
                    is_q_correct = True
                    points_awarded = question.points

                QuizAttemptAnswer.objects.create(
                    attempt=attempt,
                    question=question,
                    text_answer=text_ans,
                    is_correct=is_q_correct,
                    points_awarded=points_awarded,
                )

            earned_points += points_awarded

        final_percentage = round((earned_points / total_points) * 100, 1)
        passed = final_percentage >= quiz.pass_mark_percent
        attempt.score = final_percentage
        attempt.passed = passed
    else:
        attempt.score = 0.0
        attempt.passed = False

    attempt.save()

    # Progress Engine check if student passed
    try:
        from enrollments.services.certificate_service import update_enrollment_progress
        update_enrollment_progress(request.user, quiz.course)
    except Exception:
        pass

    if is_disqualified:
        messages.error(request, "Assessment Disqualified: Multiple tab-switch violations were recorded. Score set to 0%.")
    elif attempt.passed:
        messages.success(request, f"Congratulations! You passed with a score of {attempt.score}%.")
    else:
        messages.warning(request, f"Assessment completed. Your score is {attempt.score}% (Passing mark is {quiz.pass_mark_percent}%).")

    return redirect('quizzes:quiz_result', attempt_id=attempt.pk)


@login_required
@require_POST
def log_tab_switch(request, pk):
    """Real-time AJAX tracking of student tab switch events during proctoring."""
    quiz = get_object_or_404(Quiz.objects.select_related('course'), pk=pk)
    if not is_student_user(request.user) or not quiz.course.enrollments.filter(student=request.user).exists():
        return deny_json("Enrolled student account required.")

    try:
        data = json.loads(request.body.decode('utf-8'))
        attempt_id = data.get('attempt_id')
        tab_switches = int(data.get('tab_switch_count', 0))
        is_disqualified = bool(data.get('is_disqualified', False))

        if attempt_id:
            attempt = QuizAttempt.objects.filter(pk=attempt_id, quiz=quiz, student=request.user).first()
            if attempt:
                attempt.tab_switch_count = tab_switches
                if is_disqualified or tab_switches >= 3:
                    attempt.is_disqualified = True
                    attempt.score = 0.0
                    attempt.passed = False
                attempt.save(update_fields=['tab_switch_count', 'is_disqualified', 'score', 'passed'])
        return JsonResponse({'status': 'ok', 'tab_switches': tab_switches})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
def quiz_result(request, attempt_id):
    """Detailed review of quiz results with explanations and answers."""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related('quiz', 'quiz__course', 'student').prefetch_related(
            'answers__question__choices',
            'answers__selected_choices',
            'answers__selected_choice',
        ),
        pk=attempt_id,
    )

    is_author = is_student_user(request.user) and request.user == attempt.student
    is_instructor = is_course_manager(request.user, attempt.quiz.course)

    if not is_author and not is_instructor:
        messages.error(request, "Permission denied.")
        return redirect('courses:course_list')

    answers = attempt.answers.all()
    total = answers.count()
    correct = answers.filter(is_correct=True).count()

    return render(request, 'quizzes/quiz_result.html', {
        'attempt': attempt,
        'quiz': attempt.quiz,
        'course': attempt.quiz.course,
        'answers': answers,
        'total': total,
        'correct': correct,
        'is_author': is_author,
    })


@login_required
def quiz_create(request, course_slug):
    """Instructor or admin creates a new quiz."""
    course = get_object_or_404(Course, slug=course_slug)
    if not is_course_manager(request.user, course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=course.slug)

    if request.method == 'POST':
        form = QuizForm(request.POST)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.course = course
            quiz.save()
            messages.success(request, f"Quiz '{quiz.title}' created! Now add some questions.")
            return redirect('quizzes:quiz_edit', pk=quiz.pk)
    else:
        form = QuizForm()

    return render(request, 'quizzes/quiz_form.html', {
        'form': form,
        'course': course,
        'title': 'Create Quiz',
    })


@login_required
def quiz_edit(request, pk):
    """Instructor or admin edits a quiz and manages its questions."""
    quiz = get_object_or_404(Quiz.objects.select_related('course'), pk=pk)
    if not is_course_manager(request.user, quiz.course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=quiz.course.slug)

    if request.method == 'POST':
        form = QuizForm(request.POST, instance=quiz)
        if form.is_valid():
            form.save()
            messages.success(request, "Quiz settings saved.")
            return redirect('quizzes:quiz_edit', pk=quiz.pk)
    else:
        form = QuizForm(instance=quiz)

    questions = quiz.questions.prefetch_related('choices').all()

    return render(request, 'quizzes/quiz_edit.html', {
        'quiz': quiz,
        'form': form,
        'questions': questions,
    })


@login_required
def quiz_delete(request, pk):
    """Instructor or admin deletes a quiz."""
    quiz = get_object_or_404(Quiz.objects.select_related('course'), pk=pk)
    course = quiz.course
    if not is_course_manager(request.user, course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=course.slug)

    if request.method == 'POST':
        quiz.delete()
        messages.success(request, "Quiz deleted successfully.")
        return redirect('courses:course_detail', slug=course.slug)

    return render(request, 'quizzes/quiz_confirm_delete.html', {'quiz': quiz})


@login_required
def question_create(request, quiz_pk):
    """Instructor or admin adds a question to a quiz."""
    quiz = get_object_or_404(Quiz.objects.select_related('course'), pk=quiz_pk)
    if not is_course_manager(request.user, quiz.course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=quiz.course.slug)

    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        q_type = request.POST.get('question_type', 'single_choice')
        points = int(request.POST.get('points', '1') or '1')
        explanation = request.POST.get('explanation', '').strip()
        short_solution = request.POST.get('short_answer_solution', '').strip()
        order = int(request.POST.get('order', quiz.questions.count() + 1) or '0')

        if not text:
            messages.error(request, "Question text cannot be empty.")
        else:
            question = Question.objects.create(
                quiz=quiz,
                text=text,
                question_type=q_type,
                points=points,
                explanation=explanation,
                short_answer_solution=short_solution,
                order=order,
            )

            if q_type in ['single_choice', 'multiple_choice']:
                choices_data = [
                    (request.POST.get('choice_1', '').strip(), request.POST.get('correct_1') == 'on'),
                    (request.POST.get('choice_2', '').strip(), request.POST.get('correct_2') == 'on'),
                    (request.POST.get('choice_3', '').strip(), request.POST.get('correct_3') == 'on'),
                    (request.POST.get('choice_4', '').strip(), request.POST.get('correct_4') == 'on'),
                ]
                for c_text, is_corr in choices_data:
                    if c_text:
                        Choice.objects.create(question=question, text=c_text, is_correct=is_corr)
            elif q_type == 'true_false':
                tf_answer = request.POST.get('tf_answer', 'True')
                Choice.objects.create(question=question, text='True', is_correct=(tf_answer == 'True'))
                Choice.objects.create(question=question, text='False', is_correct=(tf_answer == 'False'))

            messages.success(request, "Question created successfully.")
            return redirect('quizzes:quiz_edit', pk=quiz.pk)

    return render(request, 'quizzes/question_form.html', {
        'quiz': quiz,
        'next_order': quiz.questions.count() + 1,
    })


@login_required
def question_delete(request, pk):
    """Instructor or admin deletes a question."""
    question = get_object_or_404(Question.objects.select_related('quiz', 'quiz__course'), pk=pk)
    quiz = question.quiz
    if not is_course_manager(request.user, quiz.course):
        messages.error(request, "Permission denied.")
        return redirect('quizzes:quiz_edit', pk=quiz.pk)

    if request.method == 'POST':
        question.delete()
        messages.success(request, "Question removed.")
    return redirect('quizzes:quiz_edit', pk=quiz.pk)


@login_required
def quiz_attempts_list(request, pk):
    """Instructor or admin views all student attempts and performance for a quiz."""
    quiz = get_object_or_404(Quiz.objects.select_related('course'), pk=pk)
    if not is_course_manager(request.user, quiz.course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=quiz.course.slug)

    attempts = quiz.attempts.select_related('student').order_by('-started_at')
    return render(request, 'quizzes/quiz_attempts_list.html', {
        'quiz': quiz,
        'attempts': attempts,
    })
