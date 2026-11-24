/**
 * Enterprise LMS Quiz Anti-Cheat & Proctoring Engine
 * Enforces fullscreen mode, copy/paste lock, synchronized countdown timer,
 * and tracks tab-switch/blur violations with auto-disqualification.
 */

document.addEventListener('DOMContentLoaded', () => {
    const configEl = document.getElementById('quiz-anticheat-config');
    if (!configEl) return;

    const quizId = configEl.dataset.quizId;
    const attemptId = configEl.dataset.attemptId;
    const timeLimitMinutes = parseInt(configEl.dataset.timeLimitMinutes || '0', 10);
    const initialSecondsRemaining = parseInt(configEl.dataset.secondsRemaining || '0', 10);
    const enforceAnticheat = configEl.dataset.enforceAnticheat === 'true';
    const tabSwitchApiUrl = configEl.dataset.tabSwitchUrl || '';
    const csrfToken = configEl.dataset.csrfToken || '';

    const quizForm = document.getElementById('quiz-form');
    const timerDisplay = document.getElementById('quiz-timer-display');
    const startOverlay = document.getElementById('quiz-start-overlay');
    const startBtn = document.getElementById('btn-start-fullscreen');
    const warningModal = document.getElementById('anticheat-warning-modal');
    const warningText = document.getElementById('anticheat-warning-text');
    const warningCloseBtn = document.getElementById('btn-close-warning');
    const tabSwitchInput = document.getElementById('input-tab-switch-count');
    const disqualifiedInput = document.getElementById('input-is-disqualified');

    let tabSwitches = parseInt(tabSwitchInput?.value || '0', 10);
    let secondsLeft = initialSecondsRemaining > 0 ? initialSecondsRemaining : (timeLimitMinutes * 60);
    let timerInterval = null;
    let isSubmitting = false;
    let isStarted = !enforceAnticheat;

    function formatTime(totalSecs) {
        if (totalSecs < 0) totalSecs = 0;
        const mins = Math.floor(totalSecs / 60);
        const secs = totalSecs % 60;
        return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    function updateTimerUI() {
        if (!timerDisplay) return;
        timerDisplay.textContent = formatTime(secondsLeft);
        if (secondsLeft <= 60) {
            timerDisplay.classList.add('text-danger', 'fw-bold');
        } else if (secondsLeft <= 300) {
            timerDisplay.classList.add('text-warning');
        }
    }

    function startTimer() {
        if (timeLimitMinutes <= 0 && initialSecondsRemaining <= 0) {
            if (timerDisplay) timerDisplay.textContent = 'Unlimited';
            return;
        }

        updateTimerUI();
        timerInterval = setInterval(() => {
            secondsLeft -= 1;
            updateTimerUI();

            if (secondsLeft <= 0) {
                clearInterval(timerInterval);
                autoSubmitQuiz('Time Expired! Submitting your assessment...');
            }
        }, 1000);
    }

    function autoSubmitQuiz(reason) {
        if (isSubmitting) return;
        isSubmitting = true;
        if (warningModal) warningModal.classList.add('d-none');

        const notice = document.createElement('div');
        notice.style.position = 'fixed';
        notice.style.top = '0';
        notice.style.left = '0';
        notice.style.width = '100vw';
        notice.style.height = '100vh';
        notice.style.backgroundColor = 'rgba(15, 23, 42, 0.9)';
        notice.style.color = '#fff';
        notice.style.display = 'flex';
        notice.style.alignItems = 'center';
        notice.style.justifyContent = 'center';
        notice.style.zIndex = '99999';
        notice.innerHTML = `<div class="text-center p-4"><div class="spinner-border text-light mb-3" role="status"></div><h4 class="fw-bold">${reason}</h4><p class="text-light-50">Recording your answers...</p></div>`;
        document.body.appendChild(notice);

        setTimeout(() => {
            if (quizForm) quizForm.submit();
        }, 1000);
    }

    // Suppress Right-Click, Cut, Copy, Paste
    if (enforceAnticheat) {
        document.addEventListener('contextmenu', (e) => e.preventDefault());
        document.addEventListener('copy', (e) => e.preventDefault());
        document.addEventListener('cut', (e) => e.preventDefault());
        document.addEventListener('paste', (e) => e.preventDefault());
        document.addEventListener('selectstart', (e) => {
            // Allow clicking inputs, but prevent text selection
            if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
                e.preventDefault();
            }
        });

        // Key combos (Ctrl+C, Ctrl+V, F12, Ctrl+U)
        document.addEventListener('keydown', (e) => {
            if (
                e.key === 'F12' ||
                (e.ctrlKey && ['c', 'v', 'u', 's', 'p'].includes(e.key.toLowerCase())) ||
                (e.ctrlKey && e.shiftKey && ['i', 'j', 'c'].includes(e.key.toLowerCase()))
            ) {
                e.preventDefault();
            }
        });
    }

    // Proctoring Fullscreen Activation
    if (startBtn && startOverlay) {
        startBtn.addEventListener('click', () => {
            if (document.documentElement.requestFullscreen) {
                document.documentElement.requestFullscreen().catch(() => {});
            }
            startOverlay.classList.add('d-none');
            isStarted = true;
            startTimer();
        });
    } else {
        startTimer();
    }

    function recordViolationOnServer(currentCount, isDisq) {
        if (!tabSwitchApiUrl) return;
        fetch(tabSwitchApiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({
                attempt_id: attemptId,
                tab_switch_count: currentCount,
                is_disqualified: isDisq,
            }),
        }).catch(() => {});
    }

    function handleTabSwitch() {
        if (!isStarted || isSubmitting || !enforceAnticheat) return;

        tabSwitches += 1;
        if (tabSwitchInput) tabSwitchInput.value = tabSwitches;

        if (tabSwitches === 1) {
            recordViolationOnServer(1, false);
            showWarning('Proctoring Warning (Violation 1 of 3)', 'You have navigated away from the assessment window. Tab switching is strictly monitored and logged.');
        } else if (tabSwitches === 2) {
            recordViolationOnServer(2, false);
            showWarning('Final Warning (Violation 2 of 3)', 'Repeated tab switching detected! A third violation will immediately terminate your exam with a disqualification score of 0.');
        } else if (tabSwitches >= 3) {
            if (disqualifiedInput) disqualifiedInput.value = 'true';
            recordViolationOnServer(tabSwitches, true);
            autoSubmitQuiz('Disqualified: Maximum permitted tab switch violations exceeded.');
        }
    }

    function showWarning(title, text) {
        if (!warningModal) return;
        const titleEl = document.getElementById('anticheat-warning-title');
        if (titleEl) titleEl.textContent = title;
        if (warningText) warningText.textContent = text;
        warningModal.classList.remove('d-none');
    }

    if (warningCloseBtn && warningModal) {
        warningCloseBtn.addEventListener('click', () => {
            warningModal.classList.add('d-none');
        });
    }

    // Monitor Visibility and Blur
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            handleTabSwitch();
        }
    });

    window.addEventListener('blur', () => {
        handleTabSwitch();
    });

    // Form submit confirmation
    var topSubmitBtn = document.getElementById('btn-submit-quiz-top');
    if (topSubmitBtn && quizForm) {
        topSubmitBtn.addEventListener('click', () => {
            quizForm.requestSubmit();
        });
    }

    if (quizForm) {
        quizForm.addEventListener('submit', () => {
            isSubmitting = true;
            if (timerInterval) clearInterval(timerInterval);
        });
    }
});

