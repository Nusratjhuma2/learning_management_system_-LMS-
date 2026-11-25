/* ===== STUDENT HEADER BEHAVIOR ===== */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var promoBar = document.getElementById('studentPromoBar');
        var closeBtn = document.getElementById('studentPromoCloseBtn');
        var STORAGE_KEY = 'lmsStudentPromoDismissed';

        if (!promoBar) {
            return;
        }

        try {
            if (sessionStorage.getItem(STORAGE_KEY) === '1') {
                promoBar.classList.add('is-dismissed');
            }
        } catch (err) {
            // Ignore storage restrictions
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', function () {
                promoBar.classList.add('is-dismissed');
                try {
                    sessionStorage.setItem(STORAGE_KEY, '1');
                } catch (err) {
                    // Ignore storage restrictions
                }
            });
        }
    });
})();
