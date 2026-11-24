/* ===== SIGNUP PAGE JS ===== */
document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var form = document.getElementById('signup-form');
    var submitBtn = document.getElementById('btn-submit-signup');

    if (form && submitBtn) {
        form.addEventListener('submit', function () {
            // Prevent multiple rapid clicks causing race conditions
            submitBtn.disabled = true;
            submitBtn.textContent = 'Registering Account...';
        });
    }
});
