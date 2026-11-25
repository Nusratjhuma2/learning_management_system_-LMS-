"""Centralized Role-Based Theme Configuration mirroring static/js/config/roleThemes.js."""

ROLE_THEMES = {
    'student': {
        'key': 'student',
        'label': 'Student',
        'pageBg': 'bg-sky-50',
        'sidebarBg': 'bg-sky-600',
        'badge': 'bg-sky-100 text-sky-700',
        'button': 'bg-sky-600 hover:bg-sky-700 text-white',
        'pageBgHex': '#F0F9FF',
        'sidebarBgHex': '#0284C7',
        'badgeBgHex': '#E0F2FE',
        'badgeTextHex': '#0369A1',
        'badgeBorderHex': '#BAE6FD',
        'buttonBgHex': '#0284C7',
        'buttonHoverHex': '#0369A1',
        'accentHex': '#0284C7',
    },
    'instructor': {
        'key': 'instructor',
        'label': 'Instructor',
        'pageBg': 'bg-emerald-50',
        'sidebarBg': 'bg-emerald-600',
        'badge': 'bg-emerald-100 text-emerald-700',
        'button': 'bg-emerald-600 hover:bg-emerald-700 text-white',
        'pageBgHex': '#ECFDF5',
        'sidebarBgHex': '#059669',
        'badgeBgHex': '#D1FAE5',
        'badgeTextHex': '#047857',
        'badgeBorderHex': '#A7F3D0',
        'buttonBgHex': '#059669',
        'buttonHoverHex': '#047857',
        'accentHex': '#059669',
    },
    'admin': {
        'key': 'admin',
        'label': 'Admin',
        'pageBg': 'bg-slate-100',
        'sidebarBg': 'bg-slate-800',
        'badge': 'bg-slate-200 text-slate-700',
        'button': 'bg-slate-800 hover:bg-slate-900 text-white',
        'pageBgHex': '#F1F5F9',
        'sidebarBgHex': '#1E293B',
        'badgeBgHex': '#E2E8F0',
        'badgeTextHex': '#334155',
        'badgeBorderHex': '#CBD5E1',
        'buttonBgHex': '#1E293B',
        'buttonHoverHex': '#0F172A',
        'accentHex': '#1E293B',
    },
}


def resolve_user_role(user):
    """Return canonical theme role ('admin', 'instructor', or fallback 'student')."""
    if not user or not getattr(user, 'is_authenticated', False):
        return 'student'
    raw_role = (getattr(user, 'role', '') or '').strip().lower()
    if getattr(user, 'is_superuser', False) or raw_role in ('admin', 'administrator', 'superuser'):
        return 'admin'
    if raw_role in ('instructor', 'teacher', 'faculty'):
        return 'instructor'
    return 'student'


def get_role_theme(user_or_role):
    """Resolve (role_key, theme_dict) from a User instance, role string, or None."""
    if isinstance(user_or_role, str):
        cleaned = user_or_role.strip().lower()
        if cleaned in ROLE_THEMES:
            return cleaned, ROLE_THEMES[cleaned]
        if cleaned in ('administrator', 'superuser'):
            return 'admin', ROLE_THEMES['admin']
        if cleaned in ('teacher', 'faculty'):
            return 'instructor', ROLE_THEMES['instructor']
        return 'student', ROLE_THEMES['student']

    role_key = resolve_user_role(user_or_role)
    return role_key, ROLE_THEMES.get(role_key, ROLE_THEMES['student'])
