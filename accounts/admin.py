from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Permission
from django.db import models

from .models import ActiveUserSession, Administrator, SecurityAuditLog, TrustedDevice, User

admin.site.site_header = "LMS Governance Administration"
admin.site.site_title = "Enterprise LMS Admin Portal"
admin.site.index_title = "System Management & Permissions Control Center"


class StandardUserChangeForm(forms.ModelForm):
    """Restricts role selection to student and instructor in the standard User admin."""
    role = forms.ChoiceField(
        choices=[(User.Role.STUDENT, 'Student'), (User.Role.INSTRUCTOR, 'Instructor')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = User
        fields = '__all__'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Standard User administration interface.
    Administrators are strictly excluded from this section and managed exclusively
    in the dedicated 'Administrators' governance section.
    """
    form = StandardUserChangeForm
    list_display = ['username', 'email', 'role', 'xp_points', 'streak_days', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['username']

    # Standard users do not expose superuser/staff or full permission grant checkboxes
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('LMS Profile & Role', {
            'fields': ('role', 'bio', 'profile_picture', 'phone_number', 'max_devices', 'xp_points', 'streak_days')
        }),
        ('Permissions & Status', {
            'fields': ('is_active',),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    def get_queryset(self, request):
        """Exclude all administrators and superusers from the standard user list."""
        qs = super().get_queryset(request)
        return qs.exclude(
            models.Q(role=User.Role.ADMIN) | models.Q(is_superuser=True)
        )

    def save_model(self, request, obj, form, change):
        # Guarantee non-admin role in this section
        if obj.role == User.Role.ADMIN:
            obj.role = User.Role.STUDENT
        obj.is_staff = False
        obj.is_superuser = False
        super().save_model(request, obj, form, change)


@admin.register(Administrator)
class AdministratorAdmin(BaseUserAdmin):
    """
    Dedicated Administrator governance interface.
    Every administrator in this section receives full administrative privileges,
    superuser access, and every permission across the LMS.
    """
    list_display = ['username', 'email', 'is_active', 'is_staff', 'is_superuser', 'last_login', 'date_joined']
    list_filter = ['is_active', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['username']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Administrative Role & Access', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser'),
            'description': 'Administrators have full system privileges and permissions across all modules.',
        }),
        ('LMS Profile', {'fields': ('bio', 'profile_picture', 'phone_number', 'max_devices')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    def get_queryset(self, request):
        """Only include administrators and superusers in this dedicated governance section."""
        qs = super().get_queryset(request)
        return qs.filter(
            models.Q(role=User.Role.ADMIN) | models.Q(is_superuser=True)
        )

    def save_model(self, request, obj, form, change):
        """Automatically grant superuser access and all system permissions upon save."""
        obj.role = User.Role.ADMIN
        obj.is_staff = True
        obj.is_superuser = True
        super().save_model(request, obj, form, change)
        all_perms = Permission.objects.all()
        obj.user_permissions.set(all_perms)

    actions = ['grant_all_permissions', 'revoke_admin_access']

    @admin.action(description="Grant superuser access & all system permissions")
    def grant_all_permissions(self, request, queryset):
        all_perms = list(Permission.objects.all())
        updated = 0
        for admin_user in queryset:
            admin_user.role = User.Role.ADMIN
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.save()
            admin_user.user_permissions.set(all_perms)
            updated += 1
        self.message_user(
            request,
            f"Successfully verified superuser access and assigned all {len(all_perms)} permissions to {updated} administrator(s)."
        )

    @admin.action(description="Demote to standard student (revoke admin access)")
    def revoke_admin_access(self, request, queryset):
        # Prevent user from revoking own access
        if queryset.filter(pk=request.user.pk).exists():
            self.message_user(request, "Error: You cannot revoke your own administrator account.", level='ERROR')
            queryset = queryset.exclude(pk=request.user.pk)

        updated = 0
        for user in queryset:
            user.role = User.Role.STUDENT
            user.is_staff = False
            user.is_superuser = False
            user.user_permissions.clear()
            user.save()
            updated += 1
        self.message_user(request, f"Revoked administrator status and permissions from {updated} user(s).")


@admin.register(ActiveUserSession)
class ActiveUserSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'session_key', 'ip_address', 'updated_at']
    search_fields = ['user__username', 'session_key', 'ip_address']
    actions = ['terminate_sessions']

    @admin.action(description="Terminate selected active sessions")
    def terminate_sessions(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"Terminated {count} active user session(s).")


@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
    list_display = ['user', 'device_name', 'device_fingerprint', 'ip_address', 'last_used_at']
    search_fields = ['user__username', 'device_fingerprint', 'device_name']


@admin.register(SecurityAuditLog)
class SecurityAuditLogAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'user', 'ip_address', 'created_at']
    list_filter = ['event_type', 'created_at']
    search_fields = ['user__username', 'ip_address', 'user_agent']
    readonly_fields = ['created_at']
