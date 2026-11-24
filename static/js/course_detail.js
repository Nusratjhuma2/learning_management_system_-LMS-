/* ===== COURSE DETAIL PAGE JS — Structured Modules, Short Video Window & Progress ===== */
document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var config = window.COURSE_DETAIL_CONFIG || {};
    var csrfToken = config.csrfToken || '';

    var playerWindow = document.getElementById('shortVideoWindow');
    var playerTitle = document.getElementById('shortVideoTitle');
    var playerModule = document.getElementById('shortVideoModule');
    var playerStage = document.getElementById('shortVideoStage');
    var playerFullLink = document.getElementById('shortVideoFullLink');
    var playerCompleteBtn = document.getElementById('shortVideoMarkCompleteBtn');
    var playerFloatBtn = document.getElementById('shortVideoFloatBtn');
    var playerCloseBtn = document.getElementById('shortVideoCloseBtn');

    var activeHlsInstance = null;
    var activeHeartbeatTimer = null;
    var activeLessonButton = null;
    var activeLessonId = null;
    var activeHeartbeatUrl = '';
    var lastHeartbeatAt = Date.now();

    function stopActiveMedia() {
        if (activeHeartbeatTimer) {
            clearInterval(activeHeartbeatTimer);
            activeHeartbeatTimer = null;
        }
        if (activeHlsInstance) {
            try {
                activeHlsInstance.destroy();
            } catch (e) {}
            activeHlsInstance = null;
        }
        if (playerStage) {
            var existingVideo = playerStage.querySelector('video');
            if (existingVideo) {
                try { existingVideo.pause(); } catch (e) {}
            }
            playerStage.innerHTML = '';
        }
        document.querySelectorAll('.lecture-row.is-active-video').forEach(function (row) {
            row.classList.remove('is-active-video');
        });
    }

    function sendShortHeartbeat(videoEl) {
        if (!activeHeartbeatUrl || !videoEl || videoEl.paused || videoEl.ended) return;
        var now = Date.now();
        var delta = Math.min((now - lastHeartbeatAt) / 1000.0, 12.0);
        lastHeartbeatAt = now;

        fetch(activeHeartbeatUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                current_position: videoEl.currentTime || 0,
                delta_watched: delta
            })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data && data.is_completed) {
                applyCompletionResponse(activeLessonId, data);
            }
        })
        .catch(function () {});
    }

    function syncPlayerCompleteButton(isCompleted, markUrl, lessonId) {
        if (!playerCompleteBtn) return;
        if (!markUrl) {
            playerCompleteBtn.classList.add('d-none');
            return;
        }
        playerCompleteBtn.classList.remove('d-none');
        playerCompleteBtn.setAttribute('data-lesson-id', lessonId || '');
        playerCompleteBtn.setAttribute('data-mark-url', markUrl);
        if (isCompleted) {
            playerCompleteBtn.disabled = true;
            playerCompleteBtn.textContent = '✓ Completed';
            playerCompleteBtn.classList.remove('btn-dark');
            playerCompleteBtn.classList.add('btn-success');
        } else {
            playerCompleteBtn.disabled = false;
            playerCompleteBtn.textContent = 'Mark Complete ✓';
            playerCompleteBtn.classList.remove('btn-success');
            playerCompleteBtn.classList.add('btn-dark');
        }
    }

    function openShortVideoWindow(triggerEl) {
        if (!playerWindow || !playerStage || !triggerEl) return;

        var videoKind = triggerEl.getAttribute('data-video-kind') || '';
        var videoSrc = triggerEl.getAttribute('data-video-src') || '';
        if (!videoSrc) return;

        var lessonId = triggerEl.getAttribute('data-lesson-id') || '';
        var title = triggerEl.getAttribute('data-lesson-title') || 'Course Lecture';
        var moduleTitle = triggerEl.getAttribute('data-module-title') || 'Curriculum';
        var detailUrl = triggerEl.getAttribute('data-detail-url') || '#';
        var markUrl = triggerEl.getAttribute('data-mark-url') || '';
        var heartbeatUrl = triggerEl.getAttribute('data-heartbeat-url') || '';
        var isCompleted = triggerEl.getAttribute('data-is-completed') === 'true';
        var lastPos = parseInt(triggerEl.getAttribute('data-last-position') || '0', 10) || 0;

        stopActiveMedia();

        activeLessonButton = triggerEl;
        activeLessonId = lessonId;
        activeHeartbeatUrl = heartbeatUrl;

        if (playerTitle) playerTitle.textContent = title;
        if (playerModule) playerModule.textContent = moduleTitle;
        if (playerFullLink) playerFullLink.setAttribute('href', detailUrl);
        syncPlayerCompleteButton(isCompleted, markUrl, lessonId);

        var row = triggerEl.closest('.lecture-row');
        if (row) row.classList.add('is-active-video');

        if (videoKind === 'embed') {
            var sep = videoSrc.indexOf('?') !== -1 ? '&' : '?';
            var embedSrc = videoSrc + sep + 'rel=0&modestbranding=1&autoplay=1';

            var ratioWrap = document.createElement('div');
            ratioWrap.className = 'ratio ratio-16x9';

            var iframe = document.createElement('iframe');
            iframe.src = embedSrc;
            iframe.title = title;
            iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
            iframe.referrerPolicy = 'strict-origin-when-cross-origin';
            iframe.allowFullscreen = true;
            iframe.className = 'border-0 w-100 h-100';

            ratioWrap.appendChild(iframe);
            playerStage.appendChild(ratioWrap);
        } else {
            var videoWrap = document.createElement('div');
            videoWrap.className = 'ratio ratio-16x9';

            var videoEl = document.createElement('video');
            videoEl.className = 'w-100 h-100 d-block';
            videoEl.controls = true;
            videoEl.setAttribute('controlsList', 'nodownload noRemotePlayback');
            videoEl.disablePictureInPicture = true;
            videoEl.addEventListener('contextmenu', function (e) {
                e.preventDefault();
                return false;
            });

            if (videoKind === 'hls' && window.Hls && window.Hls.isSupported()) {
                activeHlsInstance = new window.Hls({ debug: false });
                activeHlsInstance.loadSource(videoSrc);
                activeHlsInstance.attachMedia(videoEl);
                activeHlsInstance.on(window.Hls.Events.MANIFEST_PARSED, function () {
                    if (lastPos > 0) videoEl.currentTime = lastPos;
                    videoEl.play().catch(function () {});
                });
            } else {
                videoEl.src = videoSrc;
                videoEl.addEventListener('loadedmetadata', function () {
                    if (lastPos > 0) videoEl.currentTime = lastPos;
                }, { once: true });
                videoEl.play().catch(function () {});
            }

            videoEl.addEventListener('play', function () {
                lastHeartbeatAt = Date.now();
            });
            activeHeartbeatTimer = setInterval(function () {
                sendShortHeartbeat(videoEl);
            }, 10000);

            videoWrap.appendChild(videoEl);
            playerStage.appendChild(videoWrap);
        }

        playerWindow.classList.remove('d-none');
        if (!playerWindow.classList.contains('is-floating')) {
            playerWindow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    function applyCompletionResponse(lessonId, data) {
        if (!lessonId) return;

        // Update lecture row badge and buttons
        document.querySelectorAll('[data-play-lesson][data-lesson-id="' + lessonId + '"]').forEach(function (btn) {
            btn.setAttribute('data-is-completed', 'true');
        });
        document.querySelectorAll('.btn-mark-lesson-complete[data-lesson-id="' + lessonId + '"]').forEach(function (btn) {
            btn.disabled = true;
            btn.textContent = '✓ Completed';
            btn.classList.remove('btn-outline-dark');
            btn.classList.add('btn-success');
        });

        var statusBadge = document.getElementById('lesson-status-' + lessonId);
        if (statusBadge) {
            statusBadge.textContent = '✓ Completed';
            statusBadge.className = 'badge bg-success text-white';
        }

        if (activeLessonId && String(activeLessonId) === String(lessonId)) {
            syncPlayerCompleteButton(true, playerCompleteBtn ? playerCompleteBtn.getAttribute('data-mark-url') : '', lessonId);
        }

        // Update overall course progress UI
        if (data && typeof data.overall_progress_percent !== 'undefined') {
            var overallText = document.getElementById('overallCurriculumProgressText');
            var overallBar = document.getElementById('overallCurriculumProgressBar');
            if (overallText) {
                overallText.textContent = data.overall_progress_percent + '% (' + data.completed_items + '/' + data.total_items + ')';
            }
            if (overallBar) {
                overallBar.style.width = data.overall_progress_percent + '%';
            }
        }

        // Update module progress UI
        if (data && data.module_id) {
            var modCard = document.querySelector('.module-card[data-module-id="' + data.module_id + '"]');
            var modText = document.getElementById('module-progress-text-' + data.module_id);
            var modBar = document.getElementById('module-progress-bar-' + data.module_id);
            var modBadge = document.getElementById('module-status-badge-' + data.module_id);
            if (modText) {
                modText.textContent = data.module_completed_count + '/' + data.module_total_count + ' (' + data.module_progress_percent + '%)';
            }
            if (modBar) {
                modBar.style.width = data.module_progress_percent + '%';
            }
            if (data.module_completed) {
                if (modCard) modCard.classList.add('is-completed');
                if (modBadge) {
                    modBadge.textContent = '✓ Completed';
                    modBadge.className = 'badge bg-success text-white';
                }
            }
        }

        // If completing this module unlocked a previously locked next module, reload cleanly so locked video/lesson URLs are fetched from server
        if (data && data.module_completed && data.unlocked_next_module) {
            var unlockAlert = document.getElementById('curriculumUnlockAlert');
            if (unlockAlert) {
                unlockAlert.textContent = '🎉 Module completed! "' + data.unlocked_next_module.title + '" is now unlocked.';
                unlockAlert.classList.remove('d-none');
            }
            setTimeout(function () {
                window.location.reload();
            }, 900);
        }
    }

    function markLessonCompleted(lessonId, markUrl, triggerBtn) {
        if (!markUrl) return;
        if (triggerBtn) triggerBtn.disabled = true;

        fetch(markUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        })
        .then(function (res) {
            if (!res.ok) throw new Error('Unable to mark completed');
            return res.json();
        })
        .then(function (data) {
            if (data.status === 'ok') {
                applyCompletionResponse(lessonId, data);
            }
        })
        .catch(function () {
            if (triggerBtn) triggerBtn.disabled = false;
        });
    }

    // Bind short video play triggers
    document.addEventListener('click', function (e) {
        var playBtn = e.target.closest('[data-play-lesson]');
        if (playBtn) {
            e.preventDefault();
            openShortVideoWindow(playBtn);
            return;
        }

        var completeBtn = e.target.closest('.btn-mark-lesson-complete');
        if (completeBtn) {
            e.preventDefault();
            var lessonId = completeBtn.getAttribute('data-lesson-id');
            var markUrl = completeBtn.getAttribute('data-mark-url');
            markLessonCompleted(lessonId, markUrl, completeBtn);
        }
    });

    if (playerCompleteBtn) {
        playerCompleteBtn.addEventListener('click', function () {
            var lessonId = playerCompleteBtn.getAttribute('data-lesson-id');
            var markUrl = playerCompleteBtn.getAttribute('data-mark-url');
            markLessonCompleted(lessonId, markUrl, playerCompleteBtn);
        });
    }

    if (playerFloatBtn && playerWindow) {
        playerFloatBtn.addEventListener('click', function () {
            var isFloating = playerWindow.classList.toggle('is-floating');
            playerFloatBtn.textContent = isFloating ? 'Dock Inline' : 'Mini Float';
        });
    }

    if (playerCloseBtn && playerWindow) {
        playerCloseBtn.addEventListener('click', function () {
            stopActiveMedia();
            playerWindow.classList.remove('is-floating');
            if (playerFloatBtn) playerFloatBtn.textContent = 'Mini Float';
            playerWindow.classList.add('d-none');
        });
    }
});
