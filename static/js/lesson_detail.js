/* ===== LESSON DETAIL PAGE JS — Custom Player, Transcript Sync, Notes & Lecture Q&A ===== */
/* Expects window.LESSON_DETAIL_CONFIG injected by templates/lessons/lesson_detail.html */
document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var config = window.LESSON_DETAIL_CONFIG || {};
    var video = document.getElementById('lms-video-player');

    if (video) {
        video.addEventListener('contextmenu', function (e) {
            e.preventDefault();
            return false;
        });
    }

    var resumeBtn = document.getElementById('btn-resume-playback');
    if (resumeBtn) {
        resumeBtn.addEventListener('click', function () {
            if (window.LMSResumePlayback) {
                window.LMSResumePlayback();
            }
        });
    }

    // Initialize Structured Web Player & Transcript Sync Engine
    var playerController = null;
    if (window.LMSWebPlayer) {
        playerController = window.LMSWebPlayer.init({
            durationSeconds: config.durationSeconds || 0,
            transcriptDurationSeconds: config.transcriptDurationSeconds || 0,
            transcriptCues: config.transcriptCues || []
        });
    }

    // Initialize Protected LMS Video Security + Adaptive HLS
    if (video && window.LMSVideoSecurity) {
        window.LMSVideoSecurity({
            wrapperId: 'lms-player-container',
            videoId: 'lms-video-player',
            watermarkId: 'lms-watermark',
            curtainId: 'lms-privacy-curtain',
            violationOverlayId: 'lms-violation-overlay',
            hlsManifestUrl: config.hlsManifestUrl || '',
            heartbeatUrl: config.heartbeatUrl || '',
            securityLogUrl: config.securityLogUrl || '',
            csrfToken: config.csrfToken || '',
            lessonId: config.lessonId,
            minWatchPercent: config.minWatchPercent || 85,
            durationSeconds: config.transcriptDurationSeconds || config.durationSeconds || 0,
            lastPositionSeconds: config.lastPositionSeconds || 0,
            onLevelsLoaded: function (levels, hlsInstance) {
                if (playerController) {
                    playerController.attachHlsLevels(levels, hlsInstance);
                }
            }
        });
    }

    // Instructor / Admin Transcript Generator & Length Sync Controls
    var genTranscriptBtn = document.getElementById('btn-generate-transcript');
    var genOutlineBtn = document.getElementById('btn-generate-outline-transcript');
    var transcriptInput = document.getElementById('transcript-source-input');
    var targetLengthInput = document.getElementById('transcript-target-length');
    var transcriptFeedback = document.getElementById('transcript-gen-feedback');

    function triggerTranscriptGeneration(createDefault) {
        if (!config.generateTranscriptUrl) return;
        var rawText = transcriptInput ? transcriptInput.value : '';
        var targetLen = targetLengthInput && targetLengthInput.value ? parseInt(targetLengthInput.value, 10) : null;

        if (transcriptFeedback) {
            transcriptFeedback.className = 'small text-muted mt-2';
            transcriptFeedback.textContent = 'Generating synced transcript cues...';
        }

        fetch(config.generateTranscriptUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': config.csrfToken || ''
            },
            body: JSON.stringify({
                raw_text: rawText,
                target_duration_seconds: targetLen,
                create_default: Boolean(createDefault)
            })
        })
        .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, body: d }; }); })
        .then(function (result) {
            if (result.ok && result.body && result.body.status === 'ok') {
                if (playerController) {
                    playerController.setCues(result.body.cues || [], result.body.transcript_duration_seconds || 0);
                }
                if (transcriptFeedback) {
                    transcriptFeedback.className = 'small text-success fw-semibold mt-2';
                    transcriptFeedback.textContent = 'Synced ' + (result.body.cues || []).length + ' transcript lines (length: ' + (result.body.transcript_duration_seconds || 0) + 's). Click any line to jump and play!';
                }
            } else if (transcriptFeedback) {
                transcriptFeedback.className = 'small text-danger mt-2';
                transcriptFeedback.textContent = (result.body && result.body.message) || 'Could not generate transcript.';
            }
        })
        .catch(function () {
            if (transcriptFeedback) {
                transcriptFeedback.className = 'small text-danger mt-2';
                transcriptFeedback.textContent = 'Network error generating transcript.';
            }
        });
    }

    if (genTranscriptBtn) {
        genTranscriptBtn.addEventListener('click', function () {
            triggerTranscriptGeneration(false);
        });
    }

    if (genOutlineBtn) {
        genOutlineBtn.addEventListener('click', function () {
            triggerTranscriptGeneration(true);
        });
    }

    // Mark Lecture Completed Button (for embedded or text lectures)
    var markCompleteBtn = document.getElementById('btn-mark-completed');
    if (markCompleteBtn && config.markCompletedUrl) {
        markCompleteBtn.addEventListener('click', function () {
            fetch(config.markCompletedUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken || ''
                }
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.status === 'ok') {
                    markCompleteBtn.textContent = 'Completed ✓';
                    markCompleteBtn.classList.remove('btn-dark');
                    markCompleteBtn.classList.add('btn-secondary');
                    var indicator = document.getElementById('lesson-completion-indicator');
                    if (indicator) {
                        indicator.classList.remove('d-none');
                        indicator.classList.add('bg-dark', 'text-white');
                        indicator.textContent = 'Completed ✓';
                    }
                }
            })
            .catch(function () {});
        });
    }

    // Save Study Note API Call
    var saveNoteBtn = document.getElementById('save-note-btn');
    var noteInput = document.getElementById('note-input');
    var notesList = document.getElementById('notes-list');

    if (saveNoteBtn && noteInput && config.saveNoteUrl) {
        saveNoteBtn.addEventListener('click', function () {
            var text = noteInput.value.trim();
            if (!text) return;
            var currentSec = Math.floor(video ? video.currentTime : 0);

            fetch(config.saveNoteUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken || ''
                },
                body: JSON.stringify({
                    timestamp_seconds: currentSec,
                    note_text: text
                })
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.status === 'ok') {
                    noteInput.value = '';
                    var noNotes = document.getElementById('no-notes-text');
                    if (noNotes) noNotes.remove();

                    var item = document.createElement('div');
                    item.className = 'p-2.5 bg-white rounded border mb-2 d-flex justify-content-between align-items-center';

                    var leftWrap = document.createElement('div');
                    var timeBadge = document.createElement('span');
                    timeBadge.className = 'badge bg-light text-dark border me-2';
                    timeBadge.textContent = (data.timestamp !== undefined ? data.timestamp : currentSec) + 's';

                    var noteSpan = document.createElement('span');
                    noteSpan.className = 'text-secondary small';
                    noteSpan.textContent = data.text || text;

                    leftWrap.appendChild(timeBadge);
                    leftWrap.appendChild(noteSpan);

                    var timeMeta = document.createElement('span');
                    timeMeta.className = 'text-muted small';
                    timeMeta.textContent = data.created_at || '';

                    item.appendChild(leftWrap);
                    item.appendChild(timeMeta);
                    if (notesList) notesList.prepend(item);
                }
            })
            .catch(function () {});
        });
    }

    // Save Q&A Thread API Call
    var saveQaBtn = document.getElementById('save-qa-btn');
    var qaTitleInput = document.getElementById('qa-title-input');
    var qaBodyInput = document.getElementById('qa-body-input');
    var qaThreadsList = document.getElementById('qa-threads-list');

    if (saveQaBtn && qaTitleInput && qaBodyInput && config.createThreadUrl) {
        saveQaBtn.addEventListener('click', function () {
            var title = qaTitleInput.value.trim();
            var body = qaBodyInput.value.trim();
            if (!title || !body) return;

            fetch(config.createThreadUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken || ''
                },
                body: JSON.stringify({
                    title: title,
                    body: body
                })
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.status === 'ok') {
                    qaTitleInput.value = '';
                    qaBodyInput.value = '';
                    var noQa = document.getElementById('no-qa-text');
                    if (noQa) noQa.remove();

                    var item = document.createElement('div');
                    item.className = 'p-3 bg-white rounded border mb-2';

                    var headerRow = document.createElement('div');
                    headerRow.className = 'd-flex justify-content-between align-items-center mb-1';

                    var titleWrap = document.createElement('span');
                    titleWrap.className = 'fw-bold text-dark small';
                    var threadLink = document.createElement('a');
                    threadLink.href = '/discussions/thread/' + encodeURIComponent(data.thread_id) + '/';
                    threadLink.className = 'text-dark text-decoration-none';
                    threadLink.textContent = data.title || title;
                    titleWrap.appendChild(threadLink);

                    var statusBadge = document.createElement('span');
                    statusBadge.className = 'badge bg-light text-secondary border';
                    statusBadge.style.fontSize = '0.65rem';
                    statusBadge.textContent = 'New';

                    headerRow.appendChild(titleWrap);
                    headerRow.appendChild(statusBadge);

                    var bodyEl = document.createElement('p');
                    bodyEl.className = 'text-secondary small mb-1';
                    bodyEl.textContent = body;

                    var metaEl = document.createElement('div');
                    metaEl.className = 'text-muted small';
                    metaEl.style.fontSize = '0.75rem';
                    metaEl.textContent = 'By ' + (data.author || 'You') + ' • Just now';

                    item.appendChild(headerRow);
                    item.appendChild(bodyEl);
                    item.appendChild(metaEl);

                    if (qaThreadsList) qaThreadsList.prepend(item);
                }
            })
            .catch(function () {});
        });
    }
});
