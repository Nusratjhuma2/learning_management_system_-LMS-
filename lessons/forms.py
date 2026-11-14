from django import forms

from .models import Lesson


class LessonForm(forms.ModelForm):
    """Form for creating and editing lessons with support for video links, files, and modules."""

    class Meta:
        model = Lesson
        fields = [
            'module',
            'title',
            'order',
            'lesson_type',
            'is_free_preview',
            'video_url',
            'raw_video',
            'text_content',
            'file_upload',
            'drip_days',
            'min_watch_percent',
        ]
        widgets = {
            'module': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Introduction to Regression Analysis'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'lesson_type': forms.Select(attrs={'class': 'form-select'}),
            'is_free_preview': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'video_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://youtube.com/watch?v=... or direct video URL'}),
            'raw_video': forms.FileInput(attrs={'class': 'form-control'}),
            'text_content': forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': 'Lesson text or transcript...'}),
            'file_upload': forms.FileInput(attrs={'class': 'form-control'}),
            'drip_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'min_watch_percent': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 100}),
        }
