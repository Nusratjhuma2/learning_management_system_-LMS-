/* ===== ADMIN DASHBOARD JS ===== */
/* Chart and API configuration is provided by window.ADMIN_DASHBOARD_CONFIG
   in templates/dashboard/admin_dashboard.html. */

function activateTab(btn) {
    document.querySelectorAll('.gw-nav-pill').forEach(function (b) {
        b.classList.remove('active');
    });
    if (btn) {
        btn.classList.add('active');
    }
}

function filterSecurityLogs() {
    var input = document.getElementById('securityLogSearch');
    var table = document.getElementById('securityLogsTable');
    if (!input || !table) return;

    var filter = input.value.toLowerCase();
    var tr = table.getElementsByTagName('tr');

    for (var i = 1; i < tr.length; i++) {
        var text = tr[i].textContent || tr[i].innerText || '';
        tr[i].style.display = text.toLowerCase().indexOf(filter) > -1 ? '' : 'none';
    }
}

window.activateTab = activateTab;
window.filterSecurityLogs = filterSecurityLogs;

document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var config = window.ADMIN_DASHBOARD_CONFIG || {};

    // Bind navigation pill active highlight
    document.querySelectorAll('.gw-nav-pill').forEach(function (pill) {
        pill.addEventListener('click', function () {
            activateTab(pill);
        });
    });

    // Bind live search filter for security logs
    var logSearchInput = document.getElementById('securityLogSearch');
    if (logSearchInput) {
        logSearchInput.addEventListener('input', filterSecurityLogs);
    }

    // Initialize Chart.js Visualizations using Role Theme Accent
    if (window.Chart) {
        var activeTheme = (typeof window.getRoleTheme === 'function')
            ? window.getRoleTheme((window.LMS_AUTH_CONTEXT && window.LMS_AUTH_CONTEXT.role) || 'admin')
            : { accentHex: '#1E293B', buttonHoverHex: '#0F172A' };
        var accentHex = activeTheme.accentHex || '#1E293B';
        var accentHoverHex = activeTheme.buttonHoverHex || '#0F172A';

        Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
        Chart.defaults.color = '#64748b';

        // 1. Enrollment Longitudinal Trend (Line Chart)
        var enrollCtx = document.getElementById('enrollmentTrendChart');
        if (enrollCtx) {
            var gradientEnroll = enrollCtx.getContext('2d').createLinearGradient(0, 0, 0, 260);
            gradientEnroll.addColorStop(0, 'rgba(30, 41, 59, 0.14)');
            gradientEnroll.addColorStop(1, 'rgba(30, 41, 59, 0.00)');

            new Chart(enrollCtx, {
                type: 'line',
                data: {
                    labels: config.enrollLabels || [],
                    datasets: [{
                        label: 'New Student Enrollments',
                        data: config.enrollData || [],
                        borderColor: accentHex,
                        borderWidth: 2.5,
                        backgroundColor: gradientEnroll,
                        fill: true,
                        tension: 0.35,
                        pointBackgroundColor: accentHex,
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2,
                        pointRadius: 4.5,
                        pointHoverRadius: 7
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: accentHex,
                            titleColor: '#ffffff',
                            bodyColor: '#ffffff',
                            padding: 10,
                            cornerRadius: 6,
                            callbacks: {
                                label: function (context) {
                                    return context.raw + ' Student Enrollments';
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { font: { size: 11 } }
                        },
                        y: {
                            beginAtZero: true,
                            ticks: {
                                precision: 0,
                                font: { size: 11 }
                            },
                            grid: {
                                color: '#e2e8f0',
                                borderDash: [3, 3]
                            }
                        }
                    }
                }
            });
        }

        // 2. Gross Tuition & Revenue Volume (Bar Chart)
        var revCtx = document.getElementById('revenueVolumeChart');
        if (revCtx) {
            new Chart(revCtx, {
                type: 'bar',
                data: {
                    labels: config.revLabels || [],
                    datasets: [{
                        label: 'Gross Tuition ($)',
                        data: config.revData || [],
                        backgroundColor: accentHex,
                        hoverBackgroundColor: accentHoverHex,
                        borderRadius: 6,
                        borderSkipped: false,
                        maxBarThickness: 38
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: accentHex,
                            titleColor: '#ffffff',
                            bodyColor: '#ffffff',
                            padding: 10,
                            cornerRadius: 6,
                            callbacks: {
                                label: function (context) {
                                    return 'Revenue: $' + Number(context.raw).toLocaleString('en-US', { minimumFractionDigits: 2 });
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { font: { size: 11 } }
                        },
                        y: {
                            beginAtZero: true,
                            ticks: {
                                font: { size: 11 },
                                callback: function (val) { return '$' + val; }
                            },
                            grid: {
                                color: '#e2e8f0',
                                borderDash: [3, 3]
                            }
                        }
                    }
                }
            });
        }

        // 3. Course Status Distribution (Doughnut Chart)
        var statusCtx = document.getElementById('courseStatusChart');
        if (statusCtx) {
            new Chart(statusCtx, {
                type: 'doughnut',
                data: {
                    labels: config.courseStatusLabels || [],
                    datasets: [{
                        data: config.courseStatusData || [],
                        backgroundColor: ['#0f172a', '#64748b', '#cbd5e1'],
                        borderColor: '#ffffff',
                        borderWidth: 2,
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '68%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                boxWidth: 12,
                                padding: 14,
                                font: { size: 11, weight: '500' }
                            }
                        }
                    }
                }
            });
        }

        // 4. User Role Demographics (Doughnut Chart)
        var roleCtx = document.getElementById('userRolesChart');
        if (roleCtx) {
            new Chart(roleCtx, {
                type: 'doughnut',
                data: {
                    labels: config.roleLabels || [],
                    datasets: [{
                        data: config.roleData || [],
                        backgroundColor: ['#0f172a', '#475569', '#cbd5e1'],
                        borderColor: '#ffffff',
                        borderWidth: 2,
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '68%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                boxWidth: 12,
                                padding: 14,
                                font: { size: 11, weight: '500' }
                            }
                        }
                    }
                }
            });
        }
    }

    // 5. Live Numbers Refresh Button via AJAX API
    var refreshBtn = document.getElementById('btnRefreshStats');
    var spinner = document.getElementById('refreshSpinner');
    var icon = document.getElementById('refreshIcon');
    var toastEl = document.getElementById('liveRefreshToast');
    var lastUpdated = document.getElementById('lastUpdatedTime');

    if (refreshBtn && config.refreshApiUrl) {
        refreshBtn.addEventListener('click', function () {
            if (spinner) spinner.classList.remove('d-none');
            if (icon) icon.classList.add('d-none');
            refreshBtn.disabled = true;

            fetch(config.refreshApiUrl)
                .then(function (response) {
                    if (!response.ok) throw new Error('Network error');
                    return response.json();
                })
                .then(function (data) {
                    if (data.total_users !== undefined) {
                        document.getElementById('stat-total-users').innerText = data.total_users;
                    }
                    if (data.total_enrollments !== undefined) {
                        document.getElementById('stat-total-enrollments').innerText = data.total_enrollments;
                    }
                    if (data.total_volume !== undefined) {
                        document.getElementById('stat-total-volume').innerText = '$' + Number(data.total_volume).toFixed(2);
                    }
                    if (data.total_certificates !== undefined) {
                        document.getElementById('stat-total-certificates').innerText = data.total_certificates;
                    }
                    if (data.total_courses !== undefined) {
                        document.getElementById('stat-total-courses').innerText = data.total_courses;
                    }
                    if (data.active_sessions !== undefined) {
                        document.getElementById('stat-active-sessions').innerText = data.active_sessions;
                        var badge = document.getElementById('activeSessionsBadge');
                        if (badge) badge.innerText = data.active_sessions + ' Active';
                    }

                    if (lastUpdated) {
                        var now = new Date();
                        lastUpdated.innerText = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                    }

                    if (window.bootstrap && toastEl) {
                        var toast = new bootstrap.Toast(toastEl, { delay: 2500 });
                        toast.show();
                    }
                })
                .catch(function (err) {
                    console.error('Failed to refresh stats:', err);
                })
                .finally(function () {
                    if (spinner) spinner.classList.add('d-none');
                    if (icon) icon.classList.remove('d-none');
                    refreshBtn.disabled = false;
                });
        });
    }
});
