/* ===== NAV_HISTORY.JS — Cross-Page Back/Forward History + Exact Scroll Position Restoration ===== */
(function (root) {
    'use strict';

    var STACK_STORAGE_KEY = 'lmsTabNavStack_v1';
    var URL_SCROLL_STORAGE_KEY = 'lmsUrlScrolls_v1';
    var MAX_STACK_ENTRIES = 50;

    var stack = { entries: [], index: -1 };
    var currentKey = null;
    var scrollSaveTimer = null;
    var restoreAttemptTimers = [];

    function readJsonStorage(key, fallback) {
        try {
            var raw = sessionStorage.getItem(key);
            if (!raw) return fallback;
            var parsed = JSON.parse(raw);
            return parsed || fallback;
        } catch (err) {
            return fallback;
        }
    }

    function writeJsonStorage(key, value) {
        try {
            sessionStorage.setItem(key, JSON.stringify(value));
        } catch (err) {
            // Ignore private mode / quota errors cleanly
        }
    }

    function getCurrentUrlKey() {
        return window.location.pathname + window.location.search + window.location.hash;
    }

    function generateNavKey() {
        return 'lms_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    }

    function getNavigationType() {
        try {
            var entries = performance.getEntriesByType && performance.getEntriesByType('navigation');
            if (entries && entries.length > 0 && entries[0].type) {
                return entries[0].type;
            }
            if (performance.navigation) {
                if (performance.navigation.type === 2) return 'back_forward';
                if (performance.navigation.type === 1) return 'reload';
            }
        } catch (err) {
            // Fallback to navigate
        }
        return 'navigate';
    }

    function loadStack() {
        var data = readJsonStorage(STACK_STORAGE_KEY, { entries: [], index: -1 });
        if (!Array.isArray(data.entries)) {
            data.entries = [];
        }
        if (typeof data.index !== 'number' || data.index >= data.entries.length) {
            data.index = data.entries.length - 1;
        }
        return data;
    }

    function saveStack() {
        if (stack.entries.length > MAX_STACK_ENTRIES) {
            var trim = stack.entries.length - MAX_STACK_ENTRIES;
            stack.entries = stack.entries.slice(trim);
            stack.index = Math.max(0, stack.index - trim);
        }
        writeJsonStorage(STACK_STORAGE_KEY, stack);
    }

    function findEntryIndexByKey(key) {
        if (!key) return -1;
        for (var i = stack.entries.length - 1; i >= 0; i--) {
            if (stack.entries[i].key === key) {
                return i;
            }
        }
        return -1;
    }

    function findEntryIndexByUrl(urlKey) {
        for (var i = stack.entries.length - 1; i >= 0; i--) {
            if (stack.entries[i].url === urlKey) {
                return i;
            }
        }
        return -1;
    }

    function saveCurrentScrollPosition() {
        var scrollX = Math.round(window.scrollX || window.pageXOffset || 0);
        var scrollY = Math.round(window.scrollY || window.pageYOffset || 0);
        var urlKey = getCurrentUrlKey();

        var urlScrolls = readJsonStorage(URL_SCROLL_STORAGE_KEY, {});
        urlScrolls[urlKey] = { x: scrollX, y: scrollY, t: Date.now() };
        writeJsonStorage(URL_SCROLL_STORAGE_KEY, urlScrolls);

        if (stack.index >= 0 && stack.entries[stack.index]) {
            stack.entries[stack.index].scrollX = scrollX;
            stack.entries[stack.index].scrollY = scrollY;
            stack.entries[stack.index].title = document.title || stack.entries[stack.index].title;
            stack.entries[stack.index].url = urlKey;
            saveStack();
        }
    }

    function scheduleScrollSave() {
        if (scrollSaveTimer) return;
        scrollSaveTimer = setTimeout(function () {
            scrollSaveTimer = null;
            saveCurrentScrollPosition();
        }, 120);
    }

    function getSavedScrollForCurrentEntry() {
        if (stack.index >= 0 && stack.entries[stack.index]) {
            var entry = stack.entries[stack.index];
            if (typeof entry.scrollY === 'number') {
                return { x: entry.scrollX || 0, y: entry.scrollY || 0 };
            }
        }
        var urlScrolls = readJsonStorage(URL_SCROLL_STORAGE_KEY, {});
        var rec = urlScrolls[getCurrentUrlKey()];
        if (rec && typeof rec.y === 'number') {
            return { x: rec.x || 0, y: rec.y || 0 };
        }
        return null;
    }

    function applyExactScrollRestore(targetPos) {
        if (!targetPos || (targetPos.y <= 0 && targetPos.x <= 0)) {
            return;
        }
        restoreAttemptTimers.forEach(clearTimeout);
        restoreAttemptTimers = [];

        function doScroll() {
            if (typeof targetPos.y !== 'number') return;
            window.scrollTo({
                top: targetPos.y,
                left: targetPos.x || 0,
                behavior: 'instant'
            });
        }

        doScroll();
        requestAnimationFrame(doScroll);
        restoreAttemptTimers.push(setTimeout(doScroll, 50));
        restoreAttemptTimers.push(setTimeout(doScroll, 180));
    }

    function updateHistoryButtons() {
        var btnBack = document.getElementById('btnNavBack');
        var btnForward = document.getElementById('btnNavForward');

        var hasBackInStack = stack.index > 0;
        var hasBrowserBack = Boolean(document.referrer) && window.history.length > 1;
        var canGoBack = hasBackInStack || (stack.index <= 0 && hasBrowserBack);
        var canGoForward = stack.index >= 0 && stack.index < (stack.entries.length - 1);

        if (btnBack) {
            btnBack.disabled = !canGoBack;
            btnBack.setAttribute('aria-disabled', canGoBack ? 'false' : 'true');
            btnBack.classList.toggle('is-disabled', !canGoBack);
            if (hasBackInStack && stack.entries[stack.index - 1]) {
                var prevTitle = stack.entries[stack.index - 1].title || 'previous page';
                btnBack.title = 'Back to ' + prevTitle;
            } else {
                btnBack.title = 'Back to previous page';
            }
        }

        if (btnForward) {
            btnForward.disabled = !canGoForward;
            btnForward.setAttribute('aria-disabled', canGoForward ? 'false' : 'true');
            btnForward.classList.toggle('is-disabled', !canGoForward);
            if (canGoForward && stack.entries[stack.index + 1]) {
                var nextTitle = stack.entries[stack.index + 1].title || 'next page';
                btnForward.title = 'Forward to ' + nextTitle;
            } else {
                btnForward.title = 'Forward to next page';
            }
        }
    }

    function syncStackStateOnLoad(isBfcache) {
        stack = loadStack();
        var navType = getNavigationType();
        var state = window.history.state || {};
        var stateKey = state.lmsNavKey || null;
        var urlKey = getCurrentUrlKey();

        var existingIdx = findEntryIndexByKey(stateKey);

        if (existingIdx !== -1) {
            stack.index = existingIdx;
            currentKey = stateKey;
            stack.entries[existingIdx].title = document.title || stack.entries[existingIdx].title;
            saveStack();

            if (!isBfcache) {
                applyExactScrollRestore(getSavedScrollForCurrentEntry());
            }
        } else if (navType === 'back_forward') {
            var matchedUrlIdx = findEntryIndexByUrl(urlKey);
            if (matchedUrlIdx !== -1) {
                stack.index = matchedUrlIdx;
                currentKey = stack.entries[matchedUrlIdx].key;
                try {
                    window.history.replaceState(Object.assign({}, state, { lmsNavKey: currentKey }), '');
                } catch (err) {
                    // Ignore history state failures
                }
                saveStack();
                if (!isBfcache) {
                    applyExactScrollRestore(getSavedScrollForCurrentEntry());
                }
            } else {
                currentKey = generateNavKey();
                stack.entries.push({
                    key: currentKey,
                    url: urlKey,
                    title: document.title || urlKey,
                    scrollX: 0,
                    scrollY: 0
                });
                stack.index = stack.entries.length - 1;
                try {
                    window.history.replaceState(Object.assign({}, state, { lmsNavKey: currentKey }), '');
                } catch (err) {
                    // Ignore
                }
                saveStack();
            }
        } else if (navType === 'reload' && stack.index >= 0 && stack.entries[stack.index] && stack.entries[stack.index].url === urlKey) {
            currentKey = stack.entries[stack.index].key;
            try {
                window.history.replaceState(Object.assign({}, state, { lmsNavKey: currentKey }), '');
            } catch (err) {
                // Ignore
            }
            applyExactScrollRestore(getSavedScrollForCurrentEntry());
        } else {
            currentKey = stateKey || generateNavKey();
            if (stack.index >= 0 && stack.index < stack.entries.length - 1) {
                stack.entries = stack.entries.slice(0, stack.index + 1);
            }
            stack.entries.push({
                key: currentKey,
                url: urlKey,
                title: document.title || urlKey,
                scrollX: 0,
                scrollY: 0
            });
            stack.index = stack.entries.length - 1;
            try {
                window.history.replaceState(Object.assign({}, state, { lmsNavKey: currentKey }), '');
            } catch (err) {
                // Ignore
            }
            saveStack();
        }

        updateHistoryButtons();
    }

    function bindButtonHandlers() {
        var btnBack = document.getElementById('btnNavBack');
        var btnForward = document.getElementById('btnNavForward');

        if (btnBack) {
            btnBack.addEventListener('click', function () {
                if (btnBack.disabled) return;
                saveCurrentScrollPosition();
                window.history.back();
            });
        }

        if (btnForward) {
            btnForward.addEventListener('click', function () {
                if (btnForward.disabled) return;
                saveCurrentScrollPosition();
                window.history.forward();
            });
        }
    }

    function init() {
        syncStackStateOnLoad(false);
        bindButtonHandlers();

        window.addEventListener('scroll', scheduleScrollSave, { passive: true });
        window.addEventListener('pagehide', saveCurrentScrollPosition);
        window.addEventListener('beforeunload', saveCurrentScrollPosition);
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'hidden') {
                saveCurrentScrollPosition();
            }
        });

        window.addEventListener('pageshow', function (event) {
            syncStackStateOnLoad(Boolean(event && event.persisted));
        });

        window.addEventListener('popstate', function () {
            syncStackStateOnLoad(false);
        });

        window.addEventListener('hashchange', function () {
            syncStackStateOnLoad(false);
        });

        window.addEventListener('load', function () {
            var navType = getNavigationType();
            if (navType === 'back_forward' || navType === 'reload') {
                applyExactScrollRestore(getSavedScrollForCurrentEntry());
            }
        });

        document.addEventListener('click', function (event) {
            var anchor = event.target && event.target.closest ? event.target.closest('a[href]') : null;
            if (anchor) {
                saveCurrentScrollPosition();
            }
        });

        document.addEventListener('submit', function () {
            saveCurrentScrollPosition();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    root.LMSNavHistory = {
        getStack: function () { return stack; },
        saveCurrentScrollPosition: saveCurrentScrollPosition,
        updateHistoryButtons: updateHistoryButtons
    };
})(typeof window !== 'undefined' ? window : globalThis);
