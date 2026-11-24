/* ===== COURSE LIST PAGE JS — Promotional Carousel ===== */
(function () {
    'use strict';

    // ============================================================
    // SLIDE DURATION (Change this number to adjust speed in seconds)
    // ============================================================
    var SLIDE_SECONDS = 5; // e.g. 3, 5, 6
    var SLIDE_INTERVAL_MS = SLIDE_SECONDS * 1000;

    var carouselEl = document.getElementById('promoCarousel');
    var progress = document.getElementById('promoProgress');
    var slideLabel = document.getElementById('promoSlideLabel');
    var pauseLabel = document.getElementById('promoPauseLabel');
    var totalEl = document.getElementById('promoTotal');
    var total = parseInt(
        carouselEl.getAttribute('data-total') ||
        (totalEl ? totalEl.getAttribute('data-total') : '0'),
        10
    ) || 0;

    if (!carouselEl) return;

    // Apply interval to carousel
    carouselEl.setAttribute('data-bs-interval', SLIDE_INTERVAL_MS);
    var bsCarousel = bootstrap.Carousel.getInstance(carouselEl) || new bootstrap.Carousel(carouselEl, {
        interval: SLIDE_INTERVAL_MS,
        ride: 'carousel'
    });

    function setAdvancingText() {
        if (pauseLabel) {
            pauseLabel.innerHTML = '&#9654; Auto-advancing every ' + SLIDE_SECONDS + 's &mdash; hover to pause';
        }
    }

    function resetProgress() {
        if (!progress) return;
        progress.style.transition = 'none';
        progress.style.width = '0%';
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                progress.style.transition = 'width ' + SLIDE_SECONDS + 's linear';
                progress.style.width = '100%';
            });
        });
    }

    function updateLabel(idx) {
        if (slideLabel) slideLabel.textContent = 'Slide ' + (idx + 1) + ' of ' + total;
    }

    setAdvancingText();
    resetProgress();

    carouselEl.addEventListener('slide.bs.carousel', function (e) {
        updateLabel(e.to);
        resetProgress();
    });

    // Pause on hover, resume on mouse leave
    var wrap = carouselEl.closest('.promo-carousel-wrap') || carouselEl;
    if (wrap) {
        wrap.addEventListener('mouseenter', function () {
            bsCarousel.pause();
            if (progress) progress.style.animationPlayState = 'paused';
            if (pauseLabel) pauseLabel.innerHTML = '&#9208; Paused &mdash; move cursor away to resume';
        });
        wrap.addEventListener('mouseleave', function () {
            bsCarousel.cycle();
            resetProgress();
            setAdvancingText();
        });
    }
})();
