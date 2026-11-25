/* ===== BASE.JS — Dynamic Role Theme + Hover Dropdowns + Search Autocomplete ===== */
(function () {
    'use strict';

    /* ---- DYNAMIC ROLE THEME APPLICATION ---- */
    if (typeof window.applyRoleTheme === 'function') {
        var authRole = (window.LMS_AUTH_CONTEXT && window.LMS_AUTH_CONTEXT.role)
            || (document.body && document.body.getAttribute('data-role'))
            || 'student';
        window.applyRoleTheme(authRole);
    }

    /* ---- RESPONSIVE HOVER + TOUCH DROPDOWN MENUS ---- */
    var HOVER_CLOSE_DELAY_MS = 160;
    var HOVER_CLICK_GUARD_MS = 260;
    var hoverCloseTimers = new WeakMap();
    var hoverOpenTimestamps = new WeakMap();
    var initializedDropdowns = new WeakSet();

    function isHoverCapable() {
        if (window.matchMedia) {
            try {
                return window.matchMedia('(hover: hover) and (pointer: fine)').matches;
            } catch (err) {
                // Fallback to desktop width check
            }
        }
        return (window.innerWidth || 0) >= 992;
    }

    function clampMenuWithinViewport(dropdownEl, menuEl) {
        if (!menuEl || (dropdownEl && dropdownEl.closest && dropdownEl.closest('.lms-sidebar'))) {
            return;
        }
        menuEl.style.maxWidth = 'calc(100vw - 24px)';
        if (typeof menuEl.getBoundingClientRect !== 'function') {
            return;
        }
        menuEl.style.marginLeft = '';
        var rect = menuEl.getBoundingClientRect();
        var vpWidth = window.innerWidth || document.documentElement.clientWidth || 0;
        if (!vpWidth || (!rect.width && !rect.right && !rect.left)) {
            return;
        }
        var minMargin = 12;
        if (rect.right > vpWidth - minMargin) {
            var overflowRight = rect.right - (vpWidth - minMargin);
            menuEl.style.marginLeft = '-' + Math.ceil(overflowRight) + 'px';
        } else if (rect.left < minMargin) {
            var overflowLeft = minMargin - rect.left;
            menuEl.style.marginLeft = Math.ceil(overflowLeft) + 'px';
        }
    }

    function openHoverDropdown(dropdownEl) {
        if (!dropdownEl) return;
        var pendingTimer = hoverCloseTimers.get(dropdownEl);
        if (pendingTimer) {
            clearTimeout(pendingTimer);
            hoverCloseTimers.delete(dropdownEl);
        }

        // Close any sibling dropdowns so menus never overlap
        document.querySelectorAll('.dropdown').forEach(function (other) {
            if (other !== dropdownEl) {
                closeHoverDropdown(other, true);
            }
        });

        var toggle = dropdownEl.querySelector('[data-bs-toggle="dropdown"]');
        var menu = dropdownEl.querySelector('.dropdown-menu');
        if (!toggle || !menu) return;

        var wasOpen = menu.classList.contains('show');
        if (!wasOpen) {
            hoverOpenTimestamps.set(dropdownEl, Date.now());
        }

        if (window.bootstrap && window.bootstrap.Dropdown && typeof window.bootstrap.Dropdown.getOrCreateInstance === 'function') {
            try {
                window.bootstrap.Dropdown.getOrCreateInstance(toggle).show();
            } catch (err) {
                dropdownEl.classList.add('show');
                menu.classList.add('show');
                toggle.setAttribute('aria-expanded', 'true');
            }
        } else {
            dropdownEl.classList.add('show');
            menu.classList.add('show');
            toggle.setAttribute('aria-expanded', 'true');
        }

        requestAnimationFrame(function () {
            clampMenuWithinViewport(dropdownEl, menu);
        });
    }

    function closeHoverDropdown(dropdownEl, immediate) {
        if (!dropdownEl) return;
        var existingTimer = hoverCloseTimers.get(dropdownEl);
        if (existingTimer) {
            clearTimeout(existingTimer);
            hoverCloseTimers.delete(dropdownEl);
        }

        function doHide() {
            var toggle = dropdownEl.querySelector('[data-bs-toggle="dropdown"]');
            var menu = dropdownEl.querySelector('.dropdown-menu');
            if (!toggle || !menu) return;

            if (window.bootstrap && window.bootstrap.Dropdown && typeof window.bootstrap.Dropdown.getOrCreateInstance === 'function') {
                try {
                    window.bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
                } catch (err) {
                    dropdownEl.classList.remove('show');
                    menu.classList.remove('show');
                    toggle.setAttribute('aria-expanded', 'false');
                }
            } else {
                dropdownEl.classList.remove('show');
                menu.classList.remove('show');
                toggle.setAttribute('aria-expanded', 'false');
            }
            menu.style.marginLeft = '';
        }

        if (immediate) {
            doHide();
            return;
        }

        var timerId = setTimeout(function () {
            hoverCloseTimers.delete(dropdownEl);
            doHide();
        }, HOVER_CLOSE_DELAY_MS);
        hoverCloseTimers.set(dropdownEl, timerId);
    }

    function bindHoverDropdown(dropdownEl) {
        if (!dropdownEl || initializedDropdowns.has(dropdownEl)) return;
        var toggle = dropdownEl.querySelector('[data-bs-toggle="dropdown"]');
        var menu = dropdownEl.querySelector('.dropdown-menu');
        if (!toggle || !menu) return;

        initializedDropdowns.add(dropdownEl);

        dropdownEl.addEventListener('mouseenter', function () {
            if (!isHoverCapable()) return;
            openHoverDropdown(dropdownEl);
        });

        dropdownEl.addEventListener('mouseleave', function () {
            if (!isHoverCapable()) return;
            closeHoverDropdown(dropdownEl, false);
        });

        menu.addEventListener('mouseenter', function () {
            if (!isHoverCapable()) return;
            var pending = hoverCloseTimers.get(dropdownEl);
            if (pending) {
                clearTimeout(pending);
                hoverCloseTimers.delete(dropdownEl);
            }
        });

        // Prevent rapid click right after hover-open from collapsing the menu accidentally
        toggle.addEventListener('click', function (e) {
            if (!isHoverCapable()) return;
            var openedAt = hoverOpenTimestamps.get(dropdownEl) || 0;
            if (menu.classList.contains('show') && (Date.now() - openedAt) < HOVER_CLICK_GUARD_MS) {
                e.preventDefault();
                e.stopPropagation();
            }
        });
    }

    function initHoverDropdowns() {
        document.querySelectorAll('.dropdown').forEach(bindHoverDropdown);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initHoverDropdowns);
    } else {
        initHoverDropdowns();
    }

    window.addEventListener('resize', function () {
        document.querySelectorAll('.dropdown .dropdown-menu.show').forEach(function (menuEl) {
            clampMenuWithinViewport(menuEl.closest('.dropdown'), menuEl);
        });
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.dropdown').forEach(function (dd) {
                closeHoverDropdown(dd, true);
            });
        }
    });

    window.LMSHoverDropdowns = {
        init: initHoverDropdowns,
        openDropdown: openHoverDropdown,
        closeDropdown: closeHoverDropdown,
        clampMenuWithinViewport: clampMenuWithinViewport,
        isHoverCapable: isHoverCapable
    };

    /* ---- SEARCH AUTOCOMPLETE + COMPACT FLOATING CHIP ---- */
    var input = document.getElementById('topbarSearchInput');
    var suggBox = document.getElementById('searchSuggestions');
    var form = document.getElementById('topbarSearchForm');
    var btn = document.getElementById('topbarSearchBtn');
    var clearBtn = document.getElementById('topbarClearBtn');
    var wrap = document.getElementById('topbarSearchWrap');
    var floatChip = document.getElementById('floatingSearchChip');
    var debounceTimer = null;
    var abortController = null;
    var selectedIndex = -1;
    var currentItems = [];

    if (!input || !suggBox) return;

    function escapeHtml(text) {
        var map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
        return (text || '').replace(/[&<>"']/g, function (m) { return map[m]; });
    }

    function highlightQuery(title, query) {
        if (!query) return escapeHtml(title);
        var re = new RegExp('(' + query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        return escapeHtml(title).replace(re, '<mark>$1</mark>');
    }

    function renderSuggestions(items, q) {
        currentItems = items;
        selectedIndex = -1;
        if (!items || items.length === 0) {
            suggBox.innerHTML = '<div class="sg-empty">No matching courses found for "<strong>' + escapeHtml(q) + '</strong>"</div>';
            suggBox.style.display = 'block';
            return;
        }

        var html = '<div class="sg-header">Suggested Courses (' + items.length + ')</div>';
        items.forEach(function (item, idx) {
            var thumbHtml = item.thumbnail
                ? '<img class="sg-thumb" src="' + escapeHtml(item.thumbnail) + '" referrerpolicy="no-referrer" alt="" onerror="this.onerror=null;this.outerHTML=\'<div class=sg-thumb-fallback>' + escapeHtml((item.category || 'LMS').substring(0, 4)) + '</div>\'">'
                : '<div class="sg-thumb-fallback">' + escapeHtml((item.category || 'LMS').substring(0, 4)) + '</div>';

            var priceHtml = item.is_enrolled
                ? '<span class="sg-price-enrolled">✓ Enrolled</span>'
                : (item.is_free
                    ? '<span class="sg-price-free">FREE</span>'
                    : '$' + parseFloat(item.price || 0).toFixed(2));

            html += '<div class="sg-item" data-url="' + escapeHtml(item.url) + '" data-index="' + idx + '" role="option">'
                + thumbHtml
                + '<div class="sg-details">'
                + '<div class="sg-title">' + highlightQuery(item.title, q) + '</div>'
                + '<div class="sg-meta">'
                + (item.category ? '<span class="sg-meta-badge">' + escapeHtml(item.category) + '</span>' : '')
                + (item.level ? '<span>' + escapeHtml(item.level) + '</span>' : '')
                + (item.instructor ? '<span>• ' + escapeHtml(item.instructor) + '</span>' : '')
                + '</div>'
                + '</div>'
                + '<div class="sg-price">' + priceHtml + '</div>'
                + '</div>';
        });

        html += '<div class="sg-footer">'
            + '<span>Press <strong>Enter</strong> to search all</span>'
            + '<a href="/courses/?q=' + encodeURIComponent(q) + '">View all results &rarr;</a>'
            + '</div>';

        suggBox.innerHTML = html;
        suggBox.style.display = 'block';

        suggBox.querySelectorAll('.sg-item').forEach(function (el) {
            el.addEventListener('click', function () {
                var url = this.getAttribute('data-url');
                if (url) window.location.href = url;
            });
        });
    }

    function closeSuggestions() {
        suggBox.style.display = 'none';
        suggBox.innerHTML = '';
        selectedIndex = -1;
        currentItems = [];
    }

    function updateSelection(items) {
        items.forEach(function (el, i) {
            if (i === selectedIndex) {
                el.classList.add('sg-active');
                el.scrollIntoView({ block: 'nearest' });
            } else {
                el.classList.remove('sg-active');
            }
        });
    }

    function fetchSuggestions(query) {
        if (!query || query.length < 1) {
            closeSuggestions();
            return;
        }

        if (abortController) abortController.abort();
        abortController = new AbortController();

        fetch('/courses/api/suggest/?q=' + encodeURIComponent(query), { signal: abortController.signal })
            .then(function (res) {
                if (!res.ok) throw new Error('Network error');
                return res.json();
            })
            .then(function (data) {
                renderSuggestions(data.suggestions || [], query);
            })
            .catch(function (err) {
                if (err.name !== 'AbortError') closeSuggestions();
            });
    }

    input.addEventListener('input', function () {
        var val = this.value.trim();
        if (clearBtn) {
            clearBtn.style.display = val.length > 0 ? 'inline-flex' : 'none';
        }
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () {
            fetchSuggestions(val);
        }, 200);
    });

    input.addEventListener('keydown', function (e) {
        var items = suggBox.querySelectorAll('.sg-item');
        if (suggBox.style.display === 'block' && items.length > 0) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = (selectedIndex + 1) >= items.length ? 0 : selectedIndex + 1;
                updateSelection(items);
                if (selectedIndex >= 0 && currentItems[selectedIndex]) {
                    input.value = currentItems[selectedIndex].title;
                }
                return;
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = (selectedIndex - 1) < 0 ? items.length - 1 : selectedIndex - 1;
                updateSelection(items);
                if (selectedIndex >= 0 && currentItems[selectedIndex]) {
                    input.value = currentItems[selectedIndex].title;
                }
                return;
            } else if (e.key === 'Enter') {
                if (selectedIndex >= 0 && currentItems[selectedIndex]) {
                    e.preventDefault();
                    window.location.href = currentItems[selectedIndex].url;
                    return;
                }
            } else if (e.key === 'Escape') {
                closeSuggestions();
                return;
            }
        }
    });

    if (clearBtn) {
        clearBtn.addEventListener('click', function (e) {
            e.preventDefault();
            input.value = '';
            clearBtn.style.display = 'none';
            closeSuggestions();
            input.focus();
            if (window.location.search.indexOf('q=') !== -1) {
                window.location.href = '/courses/';
            }
        });
    }

    if (form) {
        form.addEventListener('submit', function () {
            if (btn) {
                btn.classList.add('is-compact-floating');
                btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" style="width:11px;height:11px;border-width:2px;"></span><span>Searching...</span>';
            }
            closeSuggestions();
        });
    }

    document.addEventListener('click', function (e) {
        if (wrap && !wrap.contains(e.target)) {
            closeSuggestions();
        }
    });

    if (floatChip) {
        floatChip.addEventListener('click', function (e) {
            if (e.target.closest('.cfs-clear')) return;
            window.scrollTo({ top: 0, behavior: 'smooth' });
            setTimeout(function () {
                input.focus();
                input.select();
            }, 300);
        });
    }

    /* ---- DECLARATIVE FORM CONFIRMATION, AUTO-SUBMIT & CLICKABLE CARDS ---- */
    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form || !form.getAttribute) return;
        var message = form.getAttribute('data-confirm');
        if (message && !window.confirm(message)) {
            e.preventDefault();
        }
    });

    document.addEventListener('change', function (e) {
        var el = e.target;
        if (el && el.matches && el.matches('select[data-auto-submit="true"]') && el.form) {
            el.form.submit();
        }
    });

    document.addEventListener('click', function (e) {
        var card = e.target && e.target.closest ? e.target.closest('[data-card-href]') : null;
        if (!card) return;
        if (e.target.closest('a, button, input, select, textarea, form')) return;
        var href = card.getAttribute('data-card-href');
        if (href) {
            window.location.href = href;
        }
    });
})();
