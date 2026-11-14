from django import forms
from .models import DiscussionReply, DiscussionThread


class ThreadForm(forms.ModelForm):
    """Form to start a course discussion or question."""

    class Meta:
        model = DiscussionThread
        fields = ['title', 'content', 'lesson']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'What is your question or topic?'}),
            'content': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe your question with details...'}),
        }

    def __init__(self, course, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lesson'].queryset = course.lessons.all()
        self.fields['lesson'].required = False
        self.fields['lesson'].empty_label = "General (Course-wide)"


class ReplyForm(forms.ModelForm):
    """Form to reply to a discussion thread."""

    class Meta:
        model = DiscussionReply
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write your reply or answer...'}),
        }
