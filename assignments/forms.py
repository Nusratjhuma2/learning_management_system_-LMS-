from django import forms
from .models import Assignment, AssignmentSubmission


class AssignmentForm(forms.ModelForm):
    """Form for instructors to create/edit course assignments."""

    class Meta:
        model = Assignment
        fields = ['module', 'title', 'description', 'max_score', 'due_date', 'attachment', 'repo_url_required']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Provide clear guidelines and grading criteria...'}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class AssignmentSubmissionForm(forms.ModelForm):
    """Form for students to submit assignments."""

    class Meta:
        model = AssignmentSubmission
        fields = ['submitted_file', 'submission_text', 'repo_url', 'notes']
        widgets = {
            'submission_text': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Optional remarks or direct answer text...'}),
            'repo_url': forms.URLInput(attrs={'placeholder': 'https://github.com/username/project'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Notes for the evaluator...'}),
        }


class GradingForm(forms.ModelForm):
    """Form for instructors to grade submissions."""

    class Meta:
        model = AssignmentSubmission
        fields = ['score', 'feedback']
        widgets = {
            'feedback': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Constructive feedback for the student...'}),
        }
