/**
 * Enterprise Video Anti-Download & Anti-Screen-Recording Engine
 * - Floating dynamic watermark randomized every 7s
 * - DOM MutationObserver anti-tamper enforcement
 * - Keyboard, DevTools, and Screen Capture Interception with Privacy Curtain
 * - Heartbeat watch-time tracking with server synchronization
 */

(function () {
    'use strict';

    window.LMSVideoSecurity = function (options) {
        const config = Object.assign({
            wrapperId: 'lms-player-container',
            videoId: 'lms-video-player',
            watermarkId: 'lms-watermark',
            curtainId: 'lms-privacy-curtain',
            violationOverlayId: 'lms-violation-overlay',
            hlsManifestUrl: '',
            heartbeatUrl: '',
            securityLogUrl: '',
            csrfToken: '',
            lessonId: null,
            minWatchPercent: 85,
            durationSeconds: 0,
            watermarkText: 'LMS Student'
        }, options);

        const wrapper = document.getElementById(config.wrapperId);
        const video = document.getElementById(config.videoId);
        const watermark = document.getElementById(config.watermarkId);
        const curtain = document.getElementById(config.curtainId);
        const violationOverlay = document.getElementById(config.violationOverlayId);

        if (!wrapper || !video) return;

        let lastPosition = video.currentTime || 0;
        let lastHeartbeatTime = Date.now();
        let isTampered = false;
        let hlsInstance = null;

        // 1. Prevent Right Click on player
        wrapper.addEventListener('contextmenu', function (e) {
            e.preventDefault();
            return false;
        });

        // 2. Dynamic Floating Watermark: Reposition every 7s randomly
        function randomizeWatermark() {
            if (isTampered || !watermark) return;
            const top = Math.floor(Math.random() * 65) + 15;   // 15% to 80%
            const left = Math.floor(Math.random() * 60) + 15;  // 15% to 75%
            const opacity = (Math.random() * 0.35 + 0.35).toFixed(2); // 0.35 to 0.70

            watermark.style.top = top + '%';
            watermark.style.left = left + '%';
            watermark.style.opacity = opacity;
        }

        if (watermark) {
            randomizeWatermark();
            setInterval(randomizeWatermark, 7000);
        }

        // 3. Log Security Violations to Server
        function logViolation(eventType, details) {
            if (!config.securityLogUrl) return;
            try {
                fetch(config.securityLogUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': config.csrfToken
                    },
                    body: JSON.stringify({
                        event_type: eventType,
                        details: details || {}
                    })
                }).catch(function () {});
            } catch (err) {}
        }

        // 4. Trigger Tamper Lockdown State
        function triggerLockdown(reason) {
            if (isTampered) return;
            isTampered = true;
            try {
                video.pause();
                if (hlsInstance) {
                    hlsInstance.destroy();
                }
            } catch (e) {}

            if (violationOverlay) {
                violationOverlay.classList.remove('d-none');
            }
            logViolation('WATERMARK_TAMPER', { reason: reason });
        }

        // 5. MutationObserver: Enforce Watermark & Container Integrity
        if (window.MutationObserver && watermark) {
            const observer = new MutationObserver(function (mutations) {
                mutations.forEach(function (mutation) {
                    if (mutation.type === 'childList') {
                        mutation.removedNodes.forEach(function (node) {
                            if (node === watermark || (node.contains && node.contains(watermark))) {
                                triggerLockdown('watermark_removed_from_dom');
                            }
                        });
                    } else if (mutation.type === 'attributes') {
                        const style = window.getComputedStyle(watermark);
                        if (
                            style.display === 'none' ||
                            style.visibility === 'hidden' ||
                            parseFloat(style.opacity) < 0.1 ||
                            watermark.offsetWidth === 0 ||
                            watermark.offsetHeight === 0
                        ) {
                            triggerLockdown('watermark_style_tampered');
                        }
                    }
                });
            });

            observer.observe(wrapper, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
            observer.observe(watermark, { attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
        }

        // 6. Privacy Curtain Management
        function showPrivacyCurtain(reason) {
            if (isTampered) return;
            if (curtain) {
                curtain.style.display = 'flex';
            }
            try { video.pause(); } catch (e) {}
            if (reason && reason !== 'window_blur') {
                logViolation('SCREEN_CAPTURE_ATTEMPT', { trigger: reason });
            }
        }

        function hidePrivacyCurtain() {
            if (isTampered) return;
            if (curtain) {
                curtain.style.display = 'none';
            }
        }

        window.LMSResumePlayback = function () {
            hidePrivacyCurtain();
            try { video.play(); } catch (e) {}
        };

        // Click on curtain to dismiss and resume
        if (curtain) {
            curtain.style.cursor = 'pointer';
            curtain.addEventListener('click', function () {
                window.LMSResumePlayback();
            });
        }

        // Visibility Change: Hide when tab switched, restore when student returns
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                showPrivacyCurtain('document_hidden');
            } else {
                hidePrivacyCurtain();
            }
        });

        window.addEventListener('focus', function () {
            hidePrivacyCurtain();
        });

        // Intercept display media / screen capture API if called
        if (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) {
            navigator.mediaDevices.getDisplayMedia = function () {
                showPrivacyCurtain('getDisplayMedia_called');
                logViolation('SCREEN_CAPTURE_ATTEMPT', { method: 'getDisplayMedia' });
                return Promise.reject(new Error('Screen capture disabled by policy.'));
            };
        }

        // 7. Keyboard Interception (PrintScreen, DevTools, Capture Hotkeys)
        window.addEventListener('keydown', function (e) {
            const key = e.key;
            const isCtrlShift = e.ctrlKey && e.shiftKey;
            const isMetaShift = e.metaKey && e.shiftKey;

            // PrintScreen
            if (key === 'PrintScreen') {
                showPrivacyCurtain('PrintScreen_pressed');
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(''); // Clear clipboard
                }
                setTimeout(hidePrivacyCurtain, 2000);
                return;
            }

            // DevTools Hotkeys (F12, Ctrl+Shift+I/J/C)
            if (
                key === 'F12' ||
                (isCtrlShift && (key === 'I' || key === 'J' || key === 'C')) ||
                (e.ctrlKey && key === 'U') ||
                (isMetaShift && (key === '3' || key === '4' || key === '5'))
            ) {
                e.preventDefault();
                showPrivacyCurtain('devtools_hotkey');
                logViolation('DEVTOOLS_OPENED', { key: key });
                return false;
            }
        });

        // 8. HLS.js Initialization
        if (config.hlsManifestUrl) {
            if (window.Hls && window.Hls.isSupported()) {
                hlsInstance = new window.Hls({
                    debug: false,
                    enableWorker: true,
                    lowLatencyMode: false,
                    backBufferLength: 30
                });
                hlsInstance.loadSource(config.hlsManifestUrl);
                hlsInstance.attachMedia(video);
                hlsInstance.on(window.Hls.Events.MANIFEST_PARSED, function () {
                    if (config.lastPositionSeconds && config.lastPositionSeconds > 0) {
                        video.currentTime = config.lastPositionSeconds;
                    }
                });
                hlsInstance.on(window.Hls.Events.ERROR, function (event, data) {
                    if (data.fatal) {
                        switch (data.type) {
                            case window.Hls.ErrorTypes.NETWORK_ERROR:
                                hlsInstance.startLoad();
                                break;
                            case window.Hls.ErrorTypes.MEDIA_ERROR:
                                hlsInstance.recoverMediaError();
                                break;
                            default:
                                hlsInstance.destroy();
                                break;
                        }
                    }
                });
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                // Native Safari iOS HLS support
                video.src = config.hlsManifestUrl;
                if (config.lastPositionSeconds && config.lastPositionSeconds > 0) {
                    video.addEventListener('loadedmetadata', function () {
                        video.currentTime = config.lastPositionSeconds;
                    }, { once: true });
                }
            }
        }

        // 9. Playback Watch Time & Position Heartbeat (Every 10s of active playback)
        function sendHeartbeat() {
            if (video.paused || video.ended || isTampered) return;

            const now = Date.now();
            const elapsedWallTime = (now - lastHeartbeatTime) / 1000.0;
            lastHeartbeatTime = now;

            const currentPos = video.currentTime;
            const delta = Math.min(elapsedWallTime, 12.0); // Never credit more than 12s per pulse
            lastPosition = currentPos;

            if (!config.heartbeatUrl) return;

            fetch(config.heartbeatUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken
                },
                body: JSON.stringify({
                    current_position: currentPos,
                    delta_watched: delta
                })
            })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (res && res.is_completed) {
                    const badge = document.getElementById('lesson-completion-indicator');
                    if (badge) {
                        badge.classList.remove('d-none');
                        badge.innerText = 'Completed ✓';
                    }
                }
            })
            .catch(function () {});
        }

        video.addEventListener('play', function () {
            hidePrivacyCurtain();
            lastHeartbeatTime = Date.now();
        });

        setInterval(sendHeartbeat, 10000);
    };
})();
