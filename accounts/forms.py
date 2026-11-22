from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignUpForm(UserCreationForm):
    """Registration form with student/instructor role selection and case-insensitive uniqueness validation."""

    PUBLIC_ROLE_CHOICES = (
        (User.Role.STUDENT, 'Student'),
        (User.Role.INSTRUCTOR, 'Instructor'),
    )

    role = forms.ChoiceField(
        choices=PUBLIC_ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name != 'role':
                field.widget.attrs.update({'class': 'form-control'})

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise forms.ValidationError("Username cannot be blank.")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with that username already exists. Please choose a different username.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists. Please sign in instead.")
        return email


class ProfileUpdateForm(forms.ModelForm):
    """Form for updating user profile including personal details, contact, address, and academic information."""

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'address',
            'city',
            'state',
            'postal_code',
            'country',
            'institution_name',
            'student_id',
            'department',
            'degree_program',
            'academic_year',
            'gpa',
            'bio',
            'profile_picture',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Street Address'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State / Province'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Postal Code'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Country'}),
            'institution_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'University / College'}),
            'student_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Student ID'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Department'}),
            'degree_program': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Degree / Program'}),
            'academic_year': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Year / Level'}),
            'gpa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'GPA / CGPA'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Brief bio...'}),
            'profile_picture': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        if email:
            qs = User.objects.filter(email__iexact=email)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("An account with this email address already exists.")
        return email
