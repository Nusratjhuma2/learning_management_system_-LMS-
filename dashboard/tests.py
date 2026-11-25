import json
import subprocess
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from dashboard.themes import ROLE_THEMES, get_role_theme, resolve_user_role

User = get_user_model()
REPO_ROOT = Path(__file__).resolve().parent.parent


class RoleThemeConfigTests(TestCase):
    """Verify centralized ROLE_THEMES configuration parity and fallback resolution."""

    def test_resolve_user_role_and_fallback(self):
        self.assertEqual(resolve_user_role(None), 'student')
        self.assertEqual(resolve_user_role(AnonymousUser()), 'student')

        _, fallback_theme = get_role_theme('undefined_role')
        self.assertEqual(fallback_theme['key'], 'student')
        self.assertEqual(fallback_theme['pageBg'], 'bg-sky-50')
        self.assertEqual(fallback_theme['sidebarBg'], 'bg-sky-600')
        self.assertEqual(fallback_theme['badge'], 'bg-sky-100 text-sky-700')
        self.assertEqual(fallback_theme['button'], 'bg-sky-600 hover:bg-sky-700 text-white')

    def test_python_and_js_role_themes_match_spec_and_fallback(self):
        js_path = REPO_ROOT / 'static' / 'js' / 'config' / 'roleThemes.js'
        self.assertTrue(js_path.exists())

        node_script = (
            "const m = require('./static/js/config/roleThemes.js');"
            "console.log(JSON.stringify({"
            "themes: m.ROLE_THEMES,"
            "undefFallback: m.getRoleTheme(undefined).key,"
            "nullFallback: m.getRoleTheme(null).key,"
            "loadingFallback: m.getRoleTheme('loading').key"
            "}));"
        )
        proc = subprocess.run(
            ['node', '-e', node_script],
            cwd=str(REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        js_payload = json.loads(proc.stdout)

        self.assertEqual(js_payload['undefFallback'], 'student')
        self.assertEqual(js_payload['nullFallback'], 'student')
        self.assertEqual(js_payload['loadingFallback'], 'student')

        for role_key in ('student', 'instructor', 'admin'):
            py_t = ROLE_THEMES[role_key]
            js_t = js_payload['themes'][role_key]
            for field in (
                'pageBg',
                'sidebarBg',
                'badge',
                'button',
                'pageBgHex',
                'sidebarBgHex',
                'badgeBgHex',
                'badgeTextHex',
                'buttonBgHex',
                'buttonHoverHex',
                'label',
            ):
                self.assertEqual(py_t[field], js_t[field], f'Mismatch for {role_key}.{field}')


class RoleThemeRenderingTests(TestCase):
    """Verify SSR theme attributes, 60-30-10 containers, and navbar role badges across roles."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='theme_student',
            email='student_theme@example.com',
            password='Password123!',
            role=User.Role.STUDENT,
        )
        self.instructor = User.objects.create_user(
            username='theme_instructor',
            email='inst_theme@example.com',
            password='Password123!',
            role=User.Role.INSTRUCTOR,
        )
        self.admin_user = User.objects.create_superuser(
            username='theme_admin',
            email='admin_theme@example.com',
            password='Password123!',
        )

    def test_guest_falls_back_to_student_theme_with_no_sidebar(self):
        for url in (reverse('courses:course_list'), reverse('accounts:login'), reverse('accounts:signup')):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            html = resp.content.decode('utf-8')
            self.assertIn('data-role="student"', html)
            self.assertNotIn('id="lmsSidebar"', html)
            self.assertIn('class="lms-main bg-sky-50"', html)
            self.assertIn('js/config/roleThemes.js', html)
            self.assertIn('css/role_themes.css', html)
            self.assertNotIn('id="lmsStudentHeader"', html)
            self.assertIn('class="lms-topbar"', html)

    def test_student_dashboard_renders_sky_blue_theme_and_badge(self):
        self.client.force_login(self.student)
        resp = self.client.get(reverse('dashboard:student_dashboard'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn('data-role="student"', html)
        self.assertNotIn('id="lmsSidebar"', html)
        self.assertIn('class="lms-main bg-sky-50"', html)
        self.assertIn('id="topbarRoleBadge"', html)
        self.assertIn('bg-sky-100 text-sky-700', html)
        self.assertIn('>Student<', html)
        self.assertIn('bg-white', html)
        self.assertNotIn('<style', html.lower())
        # Student-only Udemy-style header rendered cleanly without sidebar
        self.assertIn('lms-student-layout', html)
        self.assertIn('id="lmsStudentHeader"', html)
        self.assertIn('id="studentPromoBar"', html)
        self.assertIn('id="studentExploreDD"', html)
        self.assertIn('class="student-category-subnav"', html)
        self.assertIn('css/student_header.css', html)
        self.assertIn('js/student_header.js', html)

    def test_student_header_category_and_wishlist_filter_on_catalog(self):
        from courses.models import Category, Course, Wishlist
        cat = Category.objects.create(name='Cloud Architecture', slug='cloud-arch')
        c1 = Course.objects.create(
            title='Saved Course Alpha',
            slug='saved-course-alpha',
            description='Saved demo',
            instructor=self.instructor,
            category=cat,
            status=Course.Status.PUBLISHED,
            is_free=True,
        )
        Course.objects.create(
            title='Unsaved Course Beta',
            slug='unsaved-course-beta',
            description='Other demo',
            instructor=self.instructor,
            category=cat,
            status=Course.Status.PUBLISHED,
            is_free=True,
        )
        Wishlist.objects.create(student=self.student, course=c1)

        self.client.force_login(self.student)
        resp = self.client.get(reverse('courses:course_list') + '?wishlist=1')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertNotIn('id="lmsSidebar"', html)
        self.assertIn('id="lmsStudentHeader"', html)
        self.assertIn('Cloud Architecture', html)
        self.assertIn('Saved Course Alpha', html)
        self.assertNotIn('Unsaved Course Beta', html)

    def test_instructor_dashboard_renders_emerald_theme_and_badge(self):
        self.client.force_login(self.instructor)
        resp = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn('data-role="instructor"', html)
        self.assertNotIn('id="lmsSidebar"', html)
        self.assertIn('topbar-brand-mark bg-emerald-600', html)
        self.assertIn('class="lms-main bg-emerald-50"', html)
        self.assertIn('id="topbarRoleBadge"', html)
        self.assertIn('bg-emerald-100 text-emerald-700', html)
        self.assertIn('>Instructor<', html)
        self.assertIn('id="topbarMyCoursesDD"', html)
        self.assertIn('id="topbarAccountDD"', html)
        self.assertIn('Sign Out', html)
        self.assertIn('css/instructor_dashboard.css', html)
        self.assertIn('bg-white', html)
        self.assertNotIn('<style', html.lower())
        self.assertNotIn('id="lmsStudentHeader"', html)
        self.assertIn('class="lms-topbar"', html)

    def test_admin_dashboard_renders_slate_theme_and_badge(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse('dashboard:admin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn('data-role="admin"', html)
        self.assertNotIn('id="lmsSidebar"', html)
        self.assertIn('topbar-brand-mark bg-slate-800', html)
        self.assertIn('class="lms-main bg-slate-100"', html)
        self.assertIn('id="topbarRoleBadge"', html)
        self.assertIn('bg-slate-200 text-slate-700', html)
        self.assertIn('>Admin<', html)
        self.assertIn('id="topbarAdminManageDD"', html)
        self.assertIn('id="topbarAccountDD"', html)
        self.assertIn('Sign Out', html)
        self.assertIn('css/admin_dashboard.css', html)
        self.assertIn('bg-white', html)
        self.assertNotIn('<style', html.lower())
        self.assertNotIn('id="lmsStudentHeader"', html)
        self.assertIn('class="lms-topbar"', html)


class NavHistoryControlsTests(TestCase):
    """Verify Back/Forward navigation buttons render across all roles and restore scroll positions."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='nav_student',
            email='nav_stud@example.com',
            password='Password123!',
            role=User.Role.STUDENT,
        )
        self.instructor = User.objects.create_user(
            username='nav_instructor',
            email='nav_inst@example.com',
            password='Password123!',
            role=User.Role.INSTRUCTOR,
        )
        self.admin_user = User.objects.create_superuser(
            username='nav_admin',
            email='nav_admin@example.com',
            password='Password123!',
        )

    def _assert_has_unique_nav_controls(self, html):
        self.assertEqual(html.count('id="lmsNavHistory"'), 1)
        self.assertEqual(html.count('id="btnNavBack"'), 1)
        self.assertEqual(html.count('id="btnNavForward"'), 1)
        self.assertIn('js/nav_history.js', html)

    def test_back_forward_controls_present_across_all_roles(self):
        # Guest
        guest_html = self.client.get(reverse('courses:course_list')).content.decode('utf-8')
        self._assert_has_unique_nav_controls(guest_html)

        # Student (inside Udemy-style student header)
        self.client.force_login(self.student)
        stud_html = self.client.get(reverse('dashboard:student_dashboard')).content.decode('utf-8')
        self._assert_has_unique_nav_controls(stud_html)
        self.assertIn('id="lmsStudentHeader"', stud_html)

        # Instructor (inside standard topbar)
        self.client.force_login(self.instructor)
        inst_html = self.client.get(reverse('dashboard:instructor_dashboard')).content.decode('utf-8')
        self._assert_has_unique_nav_controls(inst_html)

        # Admin (inside standard topbar)
        self.client.force_login(self.admin_user)
        admin_html = self.client.get(reverse('dashboard:admin_dashboard')).content.decode('utf-8')
        self._assert_has_unique_nav_controls(admin_html)

    def test_nav_history_js_preserves_scroll_and_button_states(self):
        nav_js = (REPO_ROOT / 'static' / 'js' / 'nav_history.js').read_text(encoding='utf-8')
        node_runner = r"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('./static/js/nav_history.js', 'utf8');

const storageMap = new Map();
const sessionStorage = {
    getItem: (k) => (storageMap.has(k) ? storageMap.get(k) : null),
    setItem: (k, v) => { storageMap.set(k, String(v)); },
};

function makeBtn() {
    const classes = new Set(['is-disabled']);
    const attrs = {};
    const listeners = {};
    return {
        disabled: true,
        title: '',
        classList: {
            toggle: (c, force) => { if (force) classes.add(c); else classes.delete(c); },
            contains: (c) => classes.has(c),
        },
        setAttribute: (k, v) => { attrs[k] = v; },
        addEventListener: (ev, fn) => { listeners[ev] = fn; },
        click: () => { if (listeners.click) listeners.click(); },
    };
}

function runPage(opts) {
    const backBtn = makeBtn();
    const fwdBtn = makeBtn();
    const historyCalls = { back: 0, forward: 0 };
    let lastScrollTo = null;
    const winObj = {
        location: { pathname: opts.path, search: '', hash: '' },
        scrollX: opts.scrollX || 0,
        scrollY: opts.scrollY || 0,
        scrollTo: (arg) => { lastScrollTo = arg; },
        addEventListener: () => {},
    };
    const historyObj = {
        length: opts.historyLength || 1,
        state: opts.state || null,
        replaceState: (s) => { historyObj.state = s; },
        back: () => { historyCalls.back++; },
        forward: () => { historyCalls.forward++; },
    };
    winObj.history = historyObj;
    const docObj = {
        readyState: 'complete',
        title: opts.title,
        referrer: opts.referrer || '',
        visibilityState: 'visible',
        getElementById: (id) => (id === 'btnNavBack' ? backBtn : (id === 'btnNavForward' ? fwdBtn : null)),
        addEventListener: () => {},
    };
    const sandbox = {
        window: winObj,
        document: docObj,
        history: historyObj,
        sessionStorage,
        performance: { getEntriesByType: () => [{ type: opts.navType || 'navigate' }] },
        requestAnimationFrame: (fn) => fn(),
        setTimeout: () => 0,
        clearTimeout: () => {},
    };
    vm.runInNewContext(code, sandbox);
    return {
        win: sandbox.window,
        history: historyObj,
        backBtn,
        fwdBtn,
        historyCalls,
        getLastScroll: () => lastScrollTo,
    };
}

// 1. Page A fresh load -> scroll down to Y=480 -> save position
const pageA = runPage({ path: '/courses/', title: 'Courses', navType: 'navigate', historyLength: 1 });
if (!pageA.backBtn.disabled || !pageA.fwdBtn.disabled) throw new Error('Initial buttons should be disabled');
const keyA = pageA.history.state.lmsNavKey;
pageA.win.scrollY = 480;
pageA.win.LMSNavHistory.saveCurrentScrollPosition();

// 2. Navigate forward to Page B -> scroll down to Y=215
const pageB = runPage({ path: '/courses/python/', title: 'Python', navType: 'navigate', historyLength: 2 });
if (pageB.backBtn.disabled || !pageB.fwdBtn.disabled) throw new Error('On Page B, Back must be enabled and Forward disabled');
const keyB = pageB.history.state.lmsNavKey;
pageB.win.scrollY = 215;
pageB.win.LMSNavHistory.saveCurrentScrollPosition();

// 3. Back click -> Page A reloads via back_forward with preserved state keyA -> restores Y=480 & enables Forward
pageB.backBtn.click();
if (pageB.historyCalls.back !== 1) throw new Error('Expected Back button to invoke window.history.back()');
const backToA = runPage({ path: '/courses/', title: 'Courses', navType: 'back_forward', historyLength: 2, state: { lmsNavKey: keyA }, scrollY: 0 });
if (!backToA.getLastScroll() || backToA.getLastScroll().top !== 480) {
    throw new Error('Expected exact scrollY=480 restore, got: ' + JSON.stringify(backToA.getLastScroll()));
}
if (backToA.fwdBtn.disabled) throw new Error('Forward button should be enabled after navigating back');

// 4. Forward click -> Page B restores Y=215 & enables Back / disables Forward
backToA.fwdBtn.click();
if (backToA.historyCalls.forward !== 1) throw new Error('Expected Forward button to invoke window.history.forward()');
const fwdToB = runPage({ path: '/courses/python/', title: 'Python', navType: 'back_forward', historyLength: 2, state: { lmsNavKey: keyB }, scrollY: 0 });
if (!fwdToB.getLastScroll() || fwdToB.getLastScroll().top !== 215) {
    throw new Error('Expected exact forward scrollY=215 restore, got: ' + JSON.stringify(fwdToB.getLastScroll()));
}
if (fwdToB.backBtn.disabled || !fwdToB.fwdBtn.disabled) throw new Error('Expected Back enabled and Forward disabled on Page B');
console.log('NAV_HISTORY_VM_OK');
"""
        proc = subprocess.run(
            ['node', '-e', node_runner],
            cwd=str(REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn('NAV_HISTORY_VM_OK', proc.stdout)
        self.assertIn('window.history.back()', nav_js)
        self.assertIn('window.history.forward()', nav_js)


class HoverDropdownTests(TestCase):
    """Verify cursor-hover auto-open dropdowns and responsive viewport containment."""

    def setUp(self):
        self.student = User.objects.create_user(
            username='hover_student',
            email='hover_stud@example.com',
            password='Password123!',
            role=User.Role.STUDENT,
        )
        self.instructor = User.objects.create_user(
            username='hover_instructor',
            email='hover_inst@example.com',
            password='Password123!',
            role=User.Role.INSTRUCTOR,
        )

    def test_responsive_hover_dropdown_css_and_template_hooks(self):
        css_text = (REPO_ROOT / 'static' / 'css' / 'role_themes.css').read_text(encoding='utf-8')
        self.assertIn('.dropdown-menu.show::before', css_text)
        self.assertIn('max-width: calc(100vw - 24px)', css_text)
        self.assertIn('.lms-sidebar .dropdown-menu.show', css_text)

        self.client.force_login(self.student)
        stud_html = self.client.get(reverse('dashboard:student_dashboard')).content.decode('utf-8')
        self.assertIn('id="studentExploreDD"', stud_html)
        self.assertIn('id="studentAccountDD"', stud_html)
        self.assertIn('js/base.js', stud_html)

        self.client.force_login(self.instructor)
        inst_html = self.client.get(reverse('dashboard:instructor_dashboard')).content.decode('utf-8')
        self.assertIn('id="topbarMyCoursesDD"', inst_html)
        self.assertIn('id="topbarAccountDD"', inst_html)

    def test_hover_dropdown_js_opens_on_hover_and_clamps_responsively(self):
        node_script = r"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('./static/js/base.js', 'utf8');

function makeClassList(initial) {
    const set = new Set(initial || []);
    return {
        add: (...cs) => cs.forEach((c) => set.add(c)),
        remove: (...cs) => cs.forEach((c) => set.delete(c)),
        contains: (c) => set.has(c),
        toggle: (c, force) => { if (force === undefined ? !set.has(c) : force) set.add(c); else set.delete(c); },
    };
}

function makeDropdown(id, rect) {
    const ddListeners = {};
    const toggleListeners = {};
    const menuListeners = {};
    const attrs = { 'aria-expanded': 'false' };

    const toggle = {
        id,
        setAttribute: (k, v) => { attrs[k] = String(v); },
        getAttribute: (k) => attrs[k],
        addEventListener: (ev, fn) => { toggleListeners[ev] = fn; },
    };
    const menu = {
        classList: makeClassList(['dropdown-menu']),
        style: {},
        addEventListener: (ev, fn) => { menuListeners[ev] = fn; },
        getBoundingClientRect: () => rect || { left: 100, right: 320, width: 220 },
        closest: () => dropdown,
    };
    const dropdown = {
        classList: makeClassList(['dropdown']),
        addEventListener: (ev, fn) => { ddListeners[ev] = fn; },
        closest: () => null,
        querySelector: (sel) => {
            if (sel === '[data-bs-toggle="dropdown"]') return toggle;
            if (sel === '.dropdown-menu') return menu;
            return null;
        },
        trigger: (ev) => { if (ddListeners[ev]) ddListeners[ev](); },
        triggerMenu: (ev) => { if (menuListeners[ev]) menuListeners[ev](); },
        toggle,
        menu,
        attrs,
    };
    return dropdown;
}

let hoverSupported = true;
const explore = makeDropdown('explore', { left: 120, right: 360, width: 240 });
const account = makeDropdown('account', { left: 900, right: 1120, width: 220 });
const allDropdowns = [explore, account];
const scheduledTimers = [];

const winObj = {
    innerWidth: 1024,
    location: { search: '' },
    matchMedia: () => ({ matches: hoverSupported }),
    addEventListener: () => {},
    bootstrap: {
        Dropdown: {
            getOrCreateInstance: (tog) => {
                const dd = allDropdowns.find((d) => d.toggle === tog);
                return {
                    show: () => { dd.classList.add('show'); dd.menu.classList.add('show'); tog.setAttribute('aria-expanded', 'true'); },
                    hide: () => { dd.classList.remove('show'); dd.menu.classList.remove('show'); tog.setAttribute('aria-expanded', 'false'); },
                };
            },
        },
    },
};

const docObj = {
    readyState: 'complete',
    documentElement: { clientWidth: 1024 },
    body: { classList: makeClassList([]), getAttribute: () => 'student', style: {} },
    getElementById: () => null,
    querySelectorAll: (sel) => {
        if (sel === '.dropdown') return allDropdowns;
        if (sel === '.dropdown .dropdown-menu.show') return allDropdowns.map((d) => d.menu).filter((m) => m.classList.contains('show'));
        return [];
    },
    addEventListener: () => {},
};

const sandbox = {
    window: winObj,
    document: docObj,
    localStorage: { getItem: () => null, setItem: () => {} },
    requestAnimationFrame: (fn) => fn(),
    setTimeout: (fn) => { scheduledTimers.push(fn); return scheduledTimers.length; },
    clearTimeout: (id) => { scheduledTimers[id - 1] = null; },
    Date,
    WeakMap,
    WeakSet,
};

vm.runInNewContext(code, sandbox);

// 1. Desktop hover opens explore without clicking
explore.trigger('mouseenter');
if (!explore.menu.classList.contains('show') || explore.attrs['aria-expanded'] !== 'true') {
    throw new Error('Expected explore dropdown to open on mouseenter');
}

// 2. Hovering account closes explore automatically and clamps menu inside 1024px viewport (1120 > 1012 -> -108px)
account.trigger('mouseenter');
if (explore.menu.classList.contains('show')) throw new Error('Expected sibling explore dropdown to close');
if (!account.menu.classList.contains('show')) throw new Error('Expected account dropdown to open on mouseenter');
if (account.menu.style.marginLeft !== '-108px') {
    throw new Error('Expected right-overflow clamping marginLeft -108px, got: ' + account.menu.style.marginLeft);
}

// 3. Leaving account then re-entering menu cancels auto-close; leaving without re-enter closes on timer flush
account.trigger('mouseleave');
account.triggerMenu('mouseenter');
scheduledTimers.filter(Boolean).forEach((fn) => fn());
if (!account.menu.classList.contains('show')) throw new Error('Expected menu re-enter to cancel scheduled hide');

account.trigger('mouseleave');
scheduledTimers.filter(Boolean).forEach((fn) => fn());
if (account.menu.classList.contains('show')) throw new Error('Expected dropdown to close after mouseleave timer');

// 4. Touch / non-hover mobile mode does not hijack mouseenter
hoverSupported = false;
winObj.innerWidth = 375;
explore.trigger('mouseenter');
if (explore.menu.classList.contains('show')) throw new Error('Hover open should stay inactive on touch devices');

console.log('HOVER_DROPDOWN_VM_OK');
"""
        proc = subprocess.run(
            ['node', '-e', node_script],
            cwd=str(REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn('HOVER_DROPDOWN_VM_OK', proc.stdout)
