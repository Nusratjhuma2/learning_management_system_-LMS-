/* ===== CUSTOM STRUCTURED LMS WEB PLAYER & TRANSCRIPT SYNC ENGINE ===== */
(function () {
    'use strict';

    function formatClock(seconds) {
        var total = Math.max(Math.floor(seconds || 0), 0);
        var h = Math.floor(total / 3600);
        var m = Math.floor((total % 3600) / 60);
        var s = total % 60;
        var pad = function (n) { return n < 10 ? '0' + n : String(n); };
        return h > 0 ? (h + ':' + pad(m) + ':' + pad(s)) : (pad(m) + ':' + pad(s));
    }

    window.LMSWebPlayer = {
        init: function (config) {
            var shell = document.getElementById('lms-player-shell');
            var video = document.getElementById('lms-video-player');
            var embedFrame = document.getElementById('lms-embed-player');

            var playBtn = document.getElementById('btn-player-play');
            var rewBtn = document.getElementById('btn-player-rew');
            var fwdBtn = document.getElementById('btn-player-fwd');
            var muteBtn = document.getElementById('btn-player-mute');
            var volumeSlider = document.getElementById('input-player-volume');
            var speedSelect = document.getElementById('select-player-speed');
            var qualitySelect = document.getElementById('select-player-quality');
            var ccBtn = document.getElementById('btn-player-cc');
            var theaterBtn = document.getElementById('btn-player-theater');
            var fsBtn = document.getElementById('btn-player-fullscreen');

            var seekWrap = document.getElementById('lms-seekbar-outer');
            var bufferedEl = document.getElementById('lms-seekbar-buffered');
            var progressEl = document.getElementById('lms-seekbar-progress');
            var markersLayer = document.getElementById('lms-cue-markers-layer');
            var timeDisplay = document.getElementById('player-time-display');
            var liveCaptionEl = document.getElementById('lms-live-caption');
            var qualityStatusEl = document.getElementById('player-active-quality-badge');

            var cueListEl = document.getElementById('transcript-cue-list');
            var cueCountEl = document.getElementById('transcript-cue-count');
            var spanBadgeEl = document.getElementById('transcript-span-badge');
            var syncToggle = document.getElementById('chk-transcript-sync');

            var cues = Array.isArray(config.transcriptCues) ? config.transcriptCues : [];
            var transcriptDuration = Number(config.transcriptDurationSeconds || 0);
            var hlsController = null;
            var ccEnabled = true;
            var activeCueId = null;

            function isSyncEnabled() {
                if (!syncToggle) return transcriptDuration > 0;
                return syncToggle.checked && transcriptDuration > 0;
            }

            function getEffectiveDuration() {
                var rawDur = (video && video.duration && isFinite(video.duration))
                    ? video.duration
                    : Number(config.durationSeconds || 0);
                if (isSyncEnabled()) {
                    if (rawDur > 0) {
                        return Math.min(rawDur, transcriptDuration);
                    }
                    return transcriptDuration;
                }
                return rawDur || transcriptDuration || 0;
            }

            function renderSeekbarMarkers() {
                if (!markersLayer) return;
                markersLayer.innerHTML = '';
                var dur = getEffectiveDuration();
                if (!dur || !cues.length) return;
                cues.forEach(function (cue) {
                    var start = Number(cue.start || 0);
                    if (start < 0 || start > dur) return;
                    var tick = document.createElement('span');
                    tick.className = 'lms-cue-tick';
                    tick.style.left = Math.min(100, (start / dur) * 100) + '%';
                    tick.title = (cue.formatted_start || formatClock(start)) + ' — ' + (cue.text || '');
                    markersLayer.appendChild(tick);
                });
            }

            function renderTranscriptList() {
                if (cueCountEl) {
                    cueCountEl.textContent = cues.length + ' line' + (cues.length === 1 ? '' : 's');
                }
                if (spanBadgeEl) {
                    if (transcriptDuration > 0) {
                        spanBadgeEl.textContent = 'Transcript Span: 00:00 – ' + formatClock(transcriptDuration);
                        spanBadgeEl.classList.remove('d-none');
                    } else {
                        spanBadgeEl.classList.add('d-none');
                    }
                }
                if (!cueListEl) {
                    renderSeekbarMarkers();
                    return;
                }
                cueListEl.innerHTML = '';

                if (!cues.length) {
                    var emptyP = document.createElement('div');
                    emptyP.className = 'p-4 text-center text-muted small';
                    emptyP.id = 'no-transcript-cues';
                    emptyP.textContent = 'No timed transcript lines generated yet.';
                    cueListEl.appendChild(emptyP);
                    renderSeekbarMarkers();
                    return;
                }

                cues.forEach(function (cue) {
                    var row = document.createElement('div');
                    row.className = 'transcript-cue-item';
                    row.setAttribute('role', 'button');
                    row.setAttribute('tabindex', '0');
                    row.setAttribute('data-cue-id', String(cue.id || cue.order));
                    row.setAttribute('data-start', String(cue.start));
                    row.setAttribute('data-end', String(cue.end));

                    var tsBadge = document.createElement('span');
                    tsBadge.className = 'transcript-ts-badge';
                    tsBadge.textContent = cue.formatted_start || formatClock(cue.start);

                    var textWrap = document.createElement('div');
                    textWrap.className = 'flex-grow-1 small text-dark';
                    textWrap.textContent = cue.text;

                    row.appendChild(tsBadge);
                    row.appendChild(textWrap);
                    cueListEl.appendChild(row);
                });

                renderSeekbarMarkers();
            }

            function highlightCueAtTime(currentSec) {
                var matched = null;
                for (var i = 0; i < cues.length; i++) {
                    var c = cues[i];
                    if (currentSec >= Number(c.start) && currentSec <= Number(c.end)) {
                        matched = c;
                        break;
                    }
                }

                var newId = matched ? String(matched.id || matched.order) : null;
                if (newId !== activeCueId) {
                    activeCueId = newId;
                    if (cueListEl) {
                        cueListEl.querySelectorAll('.transcript-cue-item').forEach(function (el) {
                            if (newId && el.getAttribute('data-cue-id') === newId) {
                                el.classList.add('is-active');
                                el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                            } else {
                                el.classList.remove('is-active');
                            }
                        });
                    }
                }

                if (liveCaptionEl) {
                    if (ccEnabled && matched && matched.text) {
                        liveCaptionEl.textContent = matched.text;
                        liveCaptionEl.classList.remove('d-none');
                    } else {
                        liveCaptionEl.classList.add('d-none');
                    }
                }
            }

            function seekAndPlay(startSeconds) {
                var target = Math.max(Number(startSeconds || 0), 0);

                if (video) {
                    var effDur = getEffectiveDuration();
                    if (effDur > 0 && isSyncEnabled() && target >= effDur) {
                        target = Math.max(0, effDur - 0.5);
                    }
                    video.currentTime = target;
                    video.play().catch(function () {});
                    highlightCueAtTime(target);
                    return;
                }

                if (embedFrame) {
                    var src = embedFrame.getAttribute('src') || '';
                    if (src.indexOf('youtube.com/embed') !== -1 && embedFrame.contentWindow) {
                        embedFrame.contentWindow.postMessage(JSON.stringify({
                            event: 'command',
                            func: 'seekTo',
                            args: [target, true]
                        }), '*');
                        embedFrame.contentWindow.postMessage(JSON.stringify({
                            event: 'command',
                            func: 'playVideo',
                            args: []
                        }), '*');
                        highlightCueAtTime(target);
                    } else {
                        var base = embedFrame.getAttribute('data-base-embed-url') || src.split('?')[0];
                        var sep = base.indexOf('?') !== -1 ? '&' : '?';
                        embedFrame.setAttribute('src', base + sep + 'start=' + Math.floor(target) + '&autoplay=1&rel=0&modestbranding=1');
                        highlightCueAtTime(target);
                    }
                }
            }

            // Handle transcript line clicks (both play & keyboard accessibility)
            if (cueListEl) {
                cueListEl.addEventListener('click', function (e) {
                    var item = e.target.closest('.transcript-cue-item');
                    if (!item) return;
                    var start = parseFloat(item.getAttribute('data-start') || '0');
                    seekAndPlay(start);
                });
                cueListEl.addEventListener('keydown', function (e) {
                    if (e.key === 'Enter' || e.key === ' ') {
                        var item = e.target.closest('.transcript-cue-item');
                        if (!item) return;
                        e.preventDefault();
                        var start = parseFloat(item.getAttribute('data-start') || '0');
                        seekAndPlay(start);
                    }
                });
            }

            if (syncToggle) {
                syncToggle.addEventListener('change', function () {
                    renderSeekbarMarkers();
                    if (video) updatePlayerTimeline();
                });
            }

            function updatePlayerTimeline() {
                if (!video) return;
                var effDur = getEffectiveDuration();
                var cur = video.currentTime || 0;

                if (isSyncEnabled() && transcriptDuration > 0 && cur >= transcriptDuration) {
                    video.pause();
                    video.currentTime = transcriptDuration;
                    cur = transcriptDuration;
                }

                if (progressEl && effDur > 0) {
                    progressEl.style.width = Math.min(100, (cur / effDur) * 100) + '%';
                }
                if (timeDisplay) {
                    timeDisplay.textContent = formatClock(cur) + ' / ' + formatClock(effDur);
                }
                highlightCueAtTime(cur);
            }

            function updatePlayButtonIcon() {
                if (!playBtn || !video) return;
                playBtn.textContent = video.paused ? '▶ Play' : '❚❚ Pause';
            }

            if (video) {
                video.addEventListener('loadedmetadata', function () {
                    renderSeekbarMarkers();
                    updatePlayerTimeline();
                });
                video.addEventListener('timeupdate', updatePlayerTimeline);
                video.addEventListener('play', updatePlayButtonIcon);
                video.addEventListener('pause', updatePlayButtonIcon);
                video.addEventListener('progress', function () {
                    if (!bufferedEl || !video.buffered || video.buffered.length === 0) return;
                    var effDur = getEffectiveDuration();
                    if (effDur > 0) {
                        var bufEnd = video.buffered.end(video.buffered.length - 1);
                        bufferedEl.style.width = Math.min(100, (bufEnd / effDur) * 100) + '%';
                    }
                });

                video.addEventListener('click', function () {
                    if (video.paused) {
                        video.play().catch(function () {});
                    } else {
                        video.pause();
                    }
                });

                if (playBtn) {
                    playBtn.addEventListener('click', function () {
                        if (video.paused) {
                            video.play().catch(function () {});
                        } else {
                            video.pause();
                        }
                    });
                }

                if (rewBtn) {
                    rewBtn.addEventListener('click', function () {
                        video.currentTime = Math.max(0, (video.currentTime || 0) - 10);
                    });
                }

                if (fwdBtn) {
                    fwdBtn.addEventListener('click', function () {
                        var effDur = getEffectiveDuration();
                        var next = (video.currentTime || 0) + 10;
                        video.currentTime = effDur > 0 ? Math.min(effDur, next) : next;
                    });
                }

                if (muteBtn) {
                    muteBtn.addEventListener('click', function () {
                        video.muted = !video.muted;
                        muteBtn.textContent = video.muted ? '🔇' : '🔊';
                    });
                }

                if (volumeSlider) {
                    volumeSlider.addEventListener('input', function () {
                        video.volume = parseFloat(this.value);
                        video.muted = video.volume === 0;
                        if (muteBtn) muteBtn.textContent = video.muted ? '🔇' : '🔊';
                    });
                }

                if (speedSelect) {
                    speedSelect.addEventListener('change', function () {
                        video.playbackRate = parseFloat(this.value) || 1;
                    });
                }

                if (seekWrap) {
                    seekWrap.addEventListener('click', function (e) {
                        var rect = seekWrap.getBoundingClientRect();
                        if (!rect.width) return;
                        var ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
                        var effDur = getEffectiveDuration();
                        if (effDur > 0) {
                            video.currentTime = ratio * effDur;
                            updatePlayerTimeline();
                        }
                    });
                }

                if (ccBtn) {
                    ccBtn.classList.add('is-active');
                    ccBtn.addEventListener('click', function () {
                        ccEnabled = !ccEnabled;
                        ccBtn.classList.toggle('is-active', ccEnabled);
                        if (!ccEnabled && liveCaptionEl) {
                            liveCaptionEl.classList.add('d-none');
                        } else if (video) {
                            highlightCueAtTime(video.currentTime || 0);
                        }
                    });
                }

                if (theaterBtn && shell) {
                    theaterBtn.addEventListener('click', function () {
                        var active = shell.classList.toggle('is-theater');
                        theaterBtn.classList.toggle('is-active', active);
                    });
                }

                if (fsBtn && shell) {
                    fsBtn.addEventListener('click', function () {
                        if (document.fullscreenElement) {
                            document.exitFullscreen().catch(function () {});
                        } else if (shell.requestFullscreen) {
                            shell.requestFullscreen().catch(function () {});
                        }
                    });
                }

                if (qualitySelect) {
                    qualitySelect.addEventListener('change', function () {
                        if (!hlsController) return;
                        var val = this.value;
                        if (val === 'auto') {
                            hlsController.currentLevel = -1;
                            if (qualityStatusEl) qualityStatusEl.textContent = 'Adaptive Auto (1080p/720p/480p)';
                        } else {
                            var levelIndex = parseInt(val, 10);
                            if (!isNaN(levelIndex)) {
                                hlsController.currentLevel = levelIndex;
                                var opt = this.options[this.selectedIndex];
                                if (qualityStatusEl && opt) {
                                    qualityStatusEl.textContent = 'Quality: ' + opt.textContent;
                                }
                            }
                        }
                    });
                }
            }

            renderTranscriptList();
            if (video) {
                updatePlayButtonIcon();
                updatePlayerTimeline();
            }

            return {
                attachHlsLevels: function (levels, hlsInstance) {
                    hlsController = hlsInstance;
                    if (!qualitySelect || !levels || !levels.length) return;
                    qualitySelect.innerHTML = '';
                    var autoOpt = document.createElement('option');
                    autoOpt.value = 'auto';
                    autoOpt.textContent = 'Auto (ABR)';
                    qualitySelect.appendChild(autoOpt);

                    levels.forEach(function (lvl, idx) {
                        var opt = document.createElement('option');
                        opt.value = String(idx);
                        var label = lvl.height ? (lvl.height + 'p') : ('Tier ' + (idx + 1));
                        opt.textContent = label;
                        qualitySelect.appendChild(opt);
                    });
                    if (qualityStatusEl) {
                        qualityStatusEl.textContent = 'Adaptive HLS (' + levels.map(function (l) {
                            return l.height ? (l.height + 'p') : 'Stream';
                        }).join(' / ') + ')';
                    }
                },
                setCues: function (newCues, newTranscriptDuration) {
                    cues = Array.isArray(newCues) ? newCues : [];
                    transcriptDuration = Number(newTranscriptDuration || 0);
                    activeCueId = null;
                    renderTranscriptList();
                    if (video) updatePlayerTimeline();
                },
                seekAndPlay: seekAndPlay
            };
        }
    };
})();
