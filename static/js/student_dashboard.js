/* ===== STUDENT DASHBOARD JS — Progress bars + Filter tabs ===== */
document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    // 1. Animate Progress Bars on Load
    setTimeout(function () {
        document.querySelectorAll('.progress-bar-animated').forEach(function (bar) {
            var target = bar.getAttribute('data-target-width') || '0%';
            bar.style.transition = 'width 0.9s cubic-bezier(0.4, 0, 0.2, 1)';
            bar.style.width = target;
        });
    }, 150);

    // 2. Bind Course Filter Tab Click Events
    document.querySelectorAll('.btn-filter-tab[data-filter]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            filterCourses(btn.getAttribute('data-filter'), btn);
        });
    });
});

// Dynamic Course Filter (All / In Progress / Completed)
function filterCourses(filterType, btn) {
    document.querySelectorAll('.btn-filter-tab').forEach(function (b) {
        b.classList.remove('active');
    });
    if (btn) {
        btn.classList.add('active');
    }

    var cards = document.querySelectorAll('.course-enrollment-card');
    cards.forEach(function (card) {
        var status = card.getAttribute('data-status');
        if (filterType === 'all' || filterType === status) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

window.filterCourses = filterCourses;
