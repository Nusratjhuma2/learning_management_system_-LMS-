/**
 * Centralized Role-Based Theme Configuration (Single Frontend Source of Truth)
 * Implements the 60-30-10 visual system for Student, Instructor, and Admin roles.
 */
(function (root) {
    'use strict';

    var ROLE_THEMES = {
        student: {
            key: 'student',
            label: 'Student',
            pageBg: 'bg-sky-50',
            sidebarBg: 'bg-sky-600',
            badge: 'bg-sky-100 text-sky-700',
            button: 'bg-sky-600 hover:bg-sky-700 text-white',
            cardSurface: 'bg-white text-slate-800 border-slate-200',
            pageBgHex: '#F0F9FF',
            sidebarBgHex: '#0284C7',
            sidebarHoverHex: 'rgba(255, 255, 255, 0.14)',
            sidebarActiveHex: 'rgba(255, 255, 255, 0.24)',
            sidebarBorderHex: 'rgba(255, 255, 255, 0.20)',
            badgeBgHex: '#E0F2FE',
            badgeTextHex: '#0369A1',
            badgeBorderHex: '#BAE6FD',
            buttonBgHex: '#0284C7',
            buttonHoverHex: '#0369A1',
            buttonActiveHex: '#075985',
            accentHex: '#0284C7',
            accentSoftHex: 'rgba(2, 132, 199, 0.12)',
            cardBgHex: '#FFFFFF',
            cardTextHex: '#1E293B',
            cardBorderHex: '#E2E8F0'
        },
        instructor: {
            key: 'instructor',
            label: 'Instructor',
            pageBg: 'bg-emerald-50',
            sidebarBg: 'bg-emerald-600',
            badge: 'bg-emerald-100 text-emerald-700',
            button: 'bg-emerald-600 hover:bg-emerald-700 text-white',
            cardSurface: 'bg-white text-slate-800 border-slate-200',
            pageBgHex: '#ECFDF5',
            sidebarBgHex: '#059669',
            sidebarHoverHex: 'rgba(255, 255, 255, 0.14)',
            sidebarActiveHex: 'rgba(255, 255, 255, 0.24)',
            sidebarBorderHex: 'rgba(255, 255, 255, 0.20)',
            badgeBgHex: '#D1FAE5',
            badgeTextHex: '#047857',
            badgeBorderHex: '#A7F3D0',
            buttonBgHex: '#059669',
            buttonHoverHex: '#047857',
            buttonActiveHex: '#065F46',
            accentHex: '#059669',
            accentSoftHex: 'rgba(5, 150, 105, 0.12)',
            cardBgHex: '#FFFFFF',
            cardTextHex: '#1E293B',
            cardBorderHex: '#E2E8F0'
        },
        admin: {
            key: 'admin',
            label: 'Admin',
            pageBg: 'bg-slate-100',
            sidebarBg: 'bg-slate-800',
            badge: 'bg-slate-200 text-slate-700',
            button: 'bg-slate-800 hover:bg-slate-900 text-white',
            cardSurface: 'bg-white text-slate-800 border-slate-200',
            pageBgHex: '#F1F5F9',
            sidebarBgHex: '#1E293B',
            sidebarHoverHex: 'rgba(255, 255, 255, 0.10)',
            sidebarActiveHex: 'rgba(255, 255, 255, 0.18)',
            sidebarBorderHex: 'rgba(255, 255, 255, 0.14)',
            badgeBgHex: '#E2E8F0',
            badgeTextHex: '#334155',
            badgeBorderHex: '#CBD5E1',
            buttonBgHex: '#1E293B',
            buttonHoverHex: '#0F172A',
            buttonActiveHex: '#0F172A',
            accentHex: '#1E293B',
            accentSoftHex: 'rgba(30, 41, 59, 0.12)',
            cardBgHex: '#FFFFFF',
            cardTextHex: '#1E293B',
            cardBorderHex: '#E2E8F0'
        }
    };

    var ALL_PAGE_BG_CLASSES = ['bg-sky-50', 'bg-emerald-50', 'bg-slate-100'];
    var ALL_SIDEBAR_BG_CLASSES = ['bg-sky-600', 'bg-emerald-600', 'bg-slate-800'];
    var ALL_BADGE_CLASSES = [
        'bg-sky-100', 'text-sky-700',
        'bg-emerald-100', 'text-emerald-700',
        'bg-slate-200', 'text-slate-700'
    ];
    var ALL_THEME_CLASSES = ['lms-theme-student', 'lms-theme-instructor', 'lms-theme-admin'];

    function normalizeRoleKey(role) {
        if (!role || typeof role !== 'string') {
            return 'student';
        }
        var cleaned = role.trim().toLowerCase();
        if (cleaned === 'admin' || cleaned === 'administrator' || cleaned === 'superuser') {
            return 'admin';
        }
        if (cleaned === 'instructor' || cleaned === 'teacher' || cleaned === 'faculty') {
            return 'instructor';
        }
        return 'student';
    }

    function getRoleTheme(role) {
        var key = normalizeRoleKey(role);
        return ROLE_THEMES[key] || ROLE_THEMES.student;
    }

    function splitClasses(classString) {
        return (classString || '').split(/\s+/).filter(Boolean);
    }

    function applyRoleTheme(role) {
        var theme = getRoleTheme(role);
        if (typeof document === 'undefined') {
            return theme;
        }

        var docEl = document.documentElement;
        var body = document.body;

        docEl.setAttribute('data-role', theme.key);
        docEl.style.setProperty('--role-page-bg', theme.pageBgHex);
        docEl.style.setProperty('--role-sidebar-bg', theme.sidebarBgHex);
        docEl.style.setProperty('--role-sidebar-hover', theme.sidebarHoverHex);
        docEl.style.setProperty('--role-sidebar-active', theme.sidebarActiveHex);
        docEl.style.setProperty('--role-sidebar-border', theme.sidebarBorderHex);
        docEl.style.setProperty('--role-badge-bg', theme.badgeBgHex);
        docEl.style.setProperty('--role-badge-text', theme.badgeTextHex);
        docEl.style.setProperty('--role-badge-border', theme.badgeBorderHex);
        docEl.style.setProperty('--role-button-bg', theme.buttonBgHex);
        docEl.style.setProperty('--role-button-hover', theme.buttonHoverHex);
        docEl.style.setProperty('--role-button-active', theme.buttonActiveHex);
        docEl.style.setProperty('--role-accent', theme.accentHex);
        docEl.style.setProperty('--role-accent-soft', theme.accentSoftHex);
        docEl.style.setProperty('--color-canvas', theme.pageBgHex);
        docEl.style.setProperty('--color-primary', theme.buttonBgHex);
        docEl.style.setProperty('--color-primary-hover', theme.buttonHoverHex);
        docEl.style.setProperty('--color-primary-active', theme.buttonActiveHex);
        docEl.style.setProperty('--sidebar-bg', theme.sidebarBgHex);

        if (body) {
            body.setAttribute('data-role', theme.key);
            ALL_THEME_CLASSES.forEach(function (cls) { body.classList.remove(cls); });
            body.classList.add('lms-theme-' + theme.key);
        }

        var mainWrapper = document.getElementById('lmsMain');
        if (mainWrapper) {
            ALL_PAGE_BG_CLASSES.forEach(function (cls) { mainWrapper.classList.remove(cls); });
            splitClasses(theme.pageBg).forEach(function (cls) { mainWrapper.classList.add(cls); });
        }

        var brandMarks = document.querySelectorAll('.topbar-brand-mark');
        brandMarks.forEach(function (mark) {
            ALL_SIDEBAR_BG_CLASSES.forEach(function (cls) { mark.classList.remove(cls); });
            splitClasses(theme.sidebarBg).forEach(function (cls) { mark.classList.add(cls); });
        });

        var headerBadge = document.getElementById('topbarRoleBadge');
        if (headerBadge) {
            ALL_BADGE_CLASSES.forEach(function (cls) { headerBadge.classList.remove(cls); });
            splitClasses(theme.badge).forEach(function (cls) { headerBadge.classList.add(cls); });
            headerBadge.setAttribute('data-role-badge', theme.key);
            if (!headerBadge.textContent || !headerBadge.textContent.trim()) {
                headerBadge.textContent = theme.label;
            }
        }

        return theme;
    }

    root.ROLE_THEMES = ROLE_THEMES;
    root.normalizeRoleKey = normalizeRoleKey;
    root.getRoleTheme = getRoleTheme;
    root.applyRoleTheme = applyRoleTheme;

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            ROLE_THEMES: ROLE_THEMES,
            normalizeRoleKey: normalizeRoleKey,
            getRoleTheme: getRoleTheme,
            applyRoleTheme: applyRoleTheme
        };
    }
})(typeof window !== 'undefined' ? window : globalThis);
