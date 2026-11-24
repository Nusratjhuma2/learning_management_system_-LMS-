/* ===== INVOICE PAGE JS ===== */
document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var printBtn = document.getElementById('btn-print-invoice');
    if (printBtn) {
        printBtn.addEventListener('click', function () {
            window.print();
        });
    }
});
