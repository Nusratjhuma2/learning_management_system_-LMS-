/**
 * Screen Shield: Deactivated by configuration.
 */
(function () {
    'use strict';
    window.initLMSScreenShield = function () {
        // Disabled per admin configuration
        const existing = document.getElementById('lms-global-screen-shield');
        if (existing) existing.remove();
        const watermark = document.getElementById('lms-floating-watermark');
        if (watermark) watermark.remove();
    };
})();
