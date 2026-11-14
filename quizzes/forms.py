from django import forms
from .models import Choice, Question, Quiz


class QuizForm(forms.ModelForm):
    """Form for instructors to create/edit quizzes."""

    class Meta:
        model = Quiz
        fields = ['title', 'description', 'time_limit_mins', 'passing_score']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Instructions or coverage of this quiz...'}),
            'time_limit_mins': forms.NumberInput(attrs={'min': 0, 'placeholder': '0 = no time limit'}),
            'passing_score': forms.NumberInput(attrs={'min': 1, 'max': 100}),
        }


class QuestionForm(forms.ModelForm):
    """Form to add/edit a question with its explanation."""

    class Meta:
        model = Question
        fields = ['text', 'order', 'explanation']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Enter question statement...'}),
            'explanation': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Explanation shown to students after submitting...'}),
        }
