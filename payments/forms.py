from django import forms
from courses.models import Course
from .models import Coupon


class CouponForm(forms.ModelForm):
    """Form for creating and editing promotional coupons."""

    class Meta:
        model = Coupon
        fields = ['code', 'discount_percent', 'course', 'valid_until', 'max_uses', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control font-monospace fw-bold',
                'placeholder': 'e.g. SUMMER50',
                'style': 'text-transform: uppercase;',
            }),
            'discount_percent': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 100,
                'placeholder': 'e.g. 20',
            }),
            'course': forms.Select(attrs={'class': 'form-select'}),
            'valid_until': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'max_uses': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'placeholder': 'e.g. 100',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Format datetime-local initial value if editing
        if self.instance and self.instance.pk and self.instance.valid_until:
            self.initial['valid_until'] = self.instance.valid_until.strftime('%Y-%m-%dT%H:%M')

        if user:
            is_admin = getattr(user, 'is_admin', False) or user.is_staff or user.is_superuser
            if is_admin:
                self.fields['course'].queryset = Course.objects.all().order_by('title')
                self.fields['course'].empty_label = "All Courses (Site-Wide Coupon)"
                self.fields['course'].required = False
                self.fields['course'].help_text = "Select a specific course, or leave as 'All Courses' for a site-wide coupon."
            else:
                self.fields['course'].queryset = Course.objects.filter(instructor=user).order_by('title')
                self.fields['course'].empty_label = "Select one of your courses..."
                self.fields['course'].required = True
                self.fields['course'].help_text = "Choose the course this coupon applies to."

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip().upper()
        if not code:
            raise forms.ValidationError("Coupon code cannot be empty.")
        qs = Coupon.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Coupon code '{code}' is already taken. Please choose another code.")
        return code

    def clean_course(self):
        course = self.cleaned_data.get('course')
        if self.user:
            is_admin = getattr(self.user, 'is_admin', False) or self.user.is_staff or self.user.is_superuser
            if not is_admin:
                if not course:
                    raise forms.ValidationError("Instructors must assign coupons to one of their specific courses.")
                if course.instructor != self.user:
                    raise forms.ValidationError("You can only create coupons for your own courses.")
        return course
