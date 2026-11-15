/**
 * LMS Enterprise Screen Recording & Screenshot Protection Shield
 * Multi-Device Protection for Computers, Mobile Phones & Tablets
 */
(function () {
    'use strict';

    window.initLMSScreenShield = function (options) {
        const config = Object.assign({
            enabled: true,
            isStudent: true,
            username: 'Student',
            userEmail: '',
            userId: '',
            clientIp: '127.0.0.1',
            securityLogUrl: '/lessons/api/security-violation/',
            csrfToken: '',
            watermarkContainerId: 'lms-watermark-overlay',
            shieldModalId: 'lms-global-screen-shield'
        }, options);

        if (!config.enabled || !config.isStudent) return;

        let isCurtainActive = false;
        let isTampered = false;

        // 1. CSS Injection for Print & Copy Protection
        const style = document.createElement('style');
        style.id = 'lms-screen-shield-styles';
        style.innerHTML = `
            /* Hide everything during print or Print-to-PDF export */
            @media print {
                html, body {
                    display: none !important;
                    visibility: hidden !important;
                }
            }

            /* Disable touch selection, drag & long-press on mobile and desktop */
            .lms-protected-content, .lms-protected-content * {
                -webkit-touch-callout: none !important;
                -webkit-user-select: none !important;
                -moz-user-select: none !important;
                -ms-user-select: none !important;
                user-select: none !important;
                -webkit-user-drag: none !important;
            }

            /* Privacy Shield Overlay */
            #lms-global-screen-shield {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background-color: #0f172a;
                color: #ffffff;
                z-index: 9999999;
                display: none;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                text-align: center;
                padding: 2rem;
                box-sizing: border-box;
                font-family: 'Inter', -apple-system, sans-serif;
            }

            /* Dynamic Forensic Watermark */
            .lms-forensic-watermark {
                position: fixed;
                pointer-events: none;
                z-index: 999999;
                font-size: 0.825rem;
                font-weight: 700;
                color: rgba(15, 23, 42, 0.16);
                text-shadow: 0 0 1px rgba(255, 255, 255, 0.4);
                transform: rotate(-15deg);
                white-space: nowrap;
                transition: top 1.8s ease, left 1.8s ease, opacity 1s ease;
                font-family: monospace;
                user-select: none;
                -webkit-user-select: none;
            }
        `;
        document.head.appendChild(style);

        // 2. Create Privacy Shield Curtain Modal
        let shieldModal = document.getElementById(config.shieldModalId);
        if (!shieldModal) {
            shieldModal = document.createElement('div');
            shieldModal.id = config.shieldModalId;
            shieldModal.innerHTML = `
                <div style="max-width: 500px; background: #1e293b; border: 1px solid #334155; padding: 2.5rem; border-radius: 12px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);">
                    <div style="font-size: 2.75rem; margin-bottom: 1rem;">🔒</div>
                    <h3 style="font-size: 1.35rem; font-weight: 800; margin-bottom: 0.75rem; color: #ffffff;">Protected Academic Material</h3>
                    <p style="font-size: 0.875rem; color: #94a3b8; line-height: 1.6; margin-bottom: 1.5rem;">
                        Screenshots, screen recording, and window switching are restricted to protect course curriculum integrity. Content is temporarily hidden.
                    </p>
                    <div style="background: #0f172a; border: 1px solid #334155; padding: 0.75rem; border-radius: 8px; font-size: 0.75rem; color: #cbd5e1; margin-bottom: 1.5rem; font-family: monospace;">
                        Incident Logged: ${config.username} &bull; IP ${config.clientIp}
                    </div>
                    <button type="button" id="btn-dismiss-lms-shield" style="background: #ffffff; color: #0f172a; font-weight: 700; border: none; padding: 0.65rem 1.5rem; border-radius: 6px; cursor: pointer; font-size: 0.875rem;">
                        Return to Material &rarr;
                    </button>
                </div>
            `;
            document.body.appendChild(shieldModal);

            const dismissBtn = document.getElementById('btn-dismiss-lms-shield');
            if (dismissBtn) {
                dismissBtn.addEventListener('click', function () {
                    hideShield();
                });
            }
        }

        // 3. Create Dynamic Floating Forensic Watermark
        let watermarkEl = document.getElementById('lms-floating-watermark');
        if (!watermarkEl) {
            watermarkEl = document.createElement('div');
            watermarkEl.id = 'lms-floating-watermark';
            watermarkEl.className = 'lms-forensic-watermark';
            watermarkEl.innerText = `CONFIDENTIAL • LMS STUDENT: ${config.username} • ID: ${config.userId} • IP: ${config.clientIp}`;
            document.body.appendChild(watermarkEl);

            function repositionWatermark() {
                if (isTampered || !watermarkEl) return;
                const top = Math.floor(Math.random() * 70) + 10;   // 10% to 80%
                const left = Math.floor(Math.random() * 60) + 10;  // 10% to 70%
                const opacity = (Math.random() * 0.15 + 0.12).toFixed(2);
                watermarkEl.style.top = top + 'vh';
                watermarkEl.style.left = left + 'vw';
                watermarkEl.style.opacity = opacity;
            }

            repositionWatermark();
            setInterval(repositionWatermark, 6000);
        }

        // 4. Log Security Violation to Django Server
        function sendSecurityAlert(eventType, details) {
            if (!config.securityLogUrl || !config.csrfToken) return;
            try {
                fetch(config.securityLogUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': config.csrfToken
                    },
                    body: JSON.stringify({
                        event_type: eventType,
                        details: Object.assign({
                            device: navigator.userAgent,
                            screen_width: window.innerWidth,
                            screen_height: window.innerHeight,
                            timestamp: new Date().toISOString()
                        }, details || {})
                    })
                }).catch(function () {});
            } catch (e) {}
        }

        // 5. Shield Display Controls
        function showShield(reason) {
            if (isTampered) return;
            if (shieldModal) {
                shieldModal.style.display = 'flex';
                isCurtainActive = true;
            }
            if (reason && reason !== 'normal_blur') {
                sendSecurityAlert('SCREEN_CAPTURE_ATTEMPT', { trigger: reason });
            }
        }

        function hideShield() {
            if (isTampered) return;
            if (shieldModal) {
                shieldModal.style.display = 'none';
                isCurtainActive = false;
            }
        }

        // 6. Anti-Screenshot Keyboard Interception (PrintScreen, Snipping Tool, Mac Grab)
        window.addEventListener('keydown', function (e) {
            const key = e.key;
            const isCtrlShift = e.ctrlKey && e.shiftKey;
            const isMetaShift = e.metaKey && e.shiftKey;

            // PrintScreen (Windows/Linux)
            if (key === 'PrintScreen' || e.keyCode === 44) {
                e.preventDefault();
                showShield('PrintScreen_key_pressed');
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(''); // Blank clipboard buffer
                }
                setTimeout(hideShield, 2500);
                return false;
            }

            // Mac Screenshot shortcuts (Cmd+Shift+3, Cmd+Shift+4, Cmd+Shift+5)
            if (isMetaShift && (key === '3' || key === '4' || key === '5')) {
                e.preventDefault();
                showShield('Mac_screenshot_shortcut');
                setTimeout(hideShield, 2500);
                return false;
            }

            // Windows Snipping Tool hotkey (Win+Shift+S)
            if (e.shiftKey && (key === 'S' || key === 's') && (e.metaKey || e.ctrlKey)) {
                showShield('Snipping_tool_shortcut');
                setTimeout(hideShield, 2500);
            }

            // Browser Print & Save page shortcut (Ctrl+P, Cmd+P, Ctrl+S)
            if ((e.ctrlKey || e.metaKey) && (key === 'p' || key === 'P' || key === 's' || key === 'S')) {
                e.preventDefault();
                showShield('Print_or_save_blocked');
                sendSecurityAlert('SCREEN_CAPTURE_ATTEMPT', { trigger: 'Print_or_save_shortcut' });
                return false;
            }

            // DevTools Hotkeys (F12, Ctrl+Shift+I/J/C, Ctrl+U)
            if (
                key === 'F12' ||
                (isCtrlShift && (key === 'I' || key === 'i' || key === 'J' || key === 'j' || key === 'C' || key === 'c')) ||
                ((e.ctrlKey || e.metaKey) && (key === 'u' || key === 'U'))
            ) {
                e.preventDefault();
                showShield('Devtools_shortcut_blocked');
                sendSecurityAlert('DEVTOOLS_OPENED', { key: key });
                return false;
            }
        }, true);

        window.addEventListener('keyup', function (e) {
            if (e.key === 'PrintScreen' || e.keyCode === 44) {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText('');
                }
            }
        });

        // 7. Mobile & Desktop Blur / App Switcher / Screen Recorder Detection
        // When taking screenshots on mobile (power+vol down) or opening iOS Control Center / Android notifications,
        // the browser window immediately fires 'visibilitychange' or 'blur'
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                showShield('document_visibility_hidden');
            } else {
                hideShield();
            }
        });

        window.addEventListener('blur', function () {
            // Trigger shield on window focus loss (covers Snipping tool popups and mobile Control Center)
            showShield('window_blur_app_switch');
        });

        window.addEventListener('focus', function () {
            hideShield();
        });

        window.addEventListener('beforeprint', function () {
            showShield('print_dialog_opened');
        });

        window.addEventListener('afterprint', function () {
            hideShield();
        });

        // 8. Screen Recording API Blocker (WebRTC getDisplayMedia)
        if (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) {
            const originalGetDisplayMedia = navigator.mediaDevices.getDisplayMedia;
            navigator.mediaDevices.getDisplayMedia = function () {
                showShield('screen_recording_api_called');
                sendSecurityAlert('SCREEN_CAPTURE_ATTEMPT', { method: 'getDisplayMedia' });
                return Promise.reject(new DOMException('Screen recording is restricted on this platform.', 'NotAllowedError'));
            };
        }

        // 9. Mobile Touch Context Menu & Selection Blocker
        document.addEventListener('contextmenu', function (e) {
            // Allow inputs for writing notes, but block image/text context menus
            if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
                e.preventDefault();
                return false;
            }
        });

        document.addEventListener('selectstart', function (e) {
            if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
                e.preventDefault();
                return false;
            }
        });

        document.addEventListener('dragstart', function (e) {
            e.preventDefault();
            return false;
        });

        // 10. MutationObserver Anti-Tamper Protection
        if (window.MutationObserver && watermarkEl) {
            const observer = new MutationObserver(function (mutations) {
                mutations.forEach(function (mutation) {
                    if (mutation.type === 'childList') {
                        mutation.removedNodes.forEach(function (node) {
                            if (node === watermarkEl) {
                                isTampered = true;
                                showShield('watermark_element_removed');
                                sendSecurityAlert('WATERMARK_TAMPER', { reason: 'watermark_removed' });
                            }
                        });
                    } else if (mutation.type === 'attributes') {
                        const compStyle = window.getComputedStyle(watermarkEl);
                        if (
                            compStyle.display === 'none' ||
                            compStyle.visibility === 'hidden' ||
                            parseFloat(compStyle.opacity) === 0
                        ) {
                            isTampered = true;
                            showShield('watermark_hidden_via_css');
                            sendSecurityAlert('WATERMARK_TAMPER', { reason: 'watermark_styled_none' });
                        }
                    }
                });
            });

            observer.observe(document.body, { childList: true });
            observer.observe(watermarkEl, { attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
        }
    };
})();
