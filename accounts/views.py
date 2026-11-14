from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import redirect, render

from .forms import ProfileUpdateForm, SignUpForm


def signup_view(request):
    """Handle user registration with robust duplicate prevention."""
    if request.user.is_authenticated:
        return redirect('courses:course_list')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                login(request, user)
                messages.success(request, f"Welcome to LMS, {user.first_name or user.username}! Your account has been registered.")
                return redirect('courses:course_list')
            except IntegrityError:
                form.add_error('username', 'A user with this username already exists. Please choose another username.')
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def profile_view(request):
    """Display and update user profile."""
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect('accounts:profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(request, 'accounts/profile.html', {'form': form})
