/**
 * Boss Sentinel — 前端交互逻辑
 * Apple 风格单页应用控制器
 */

/* ================================================================
   应用状态
   ================================================================ */

const app = {
    // SSE 连接
    _logSource: null,
    _alertSource: null,
    _statusTimer: null,

    // FPS 计算
    _fpsFrames: 0,
    _fpsLast: Date.now(),

    // 告警冷却
    _lastAlertTime: 0,

    /* ----------------------------------------------------------------
       初始化
       ---------------------------------------------------------------- */

    init() {
        this._bindVideoFeed();
        this._connectLogStream();
        this._connectAlertStream();
        this._startStatusPolling();
        this._requestNotificationPermission();
        this._prepareAudio();
    },

    /* ----------------------------------------------------------------
       监控控制
       ---------------------------------------------------------------- */

    async startMonitoring() {
        const config = this._readConfigForm();
        const btn = document.getElementById('btnStart');
        btn.disabled = true;

        try {
            const res = await this._api('POST', '/api/start', config);
            if (!res.ok) {
                const data = await res.json();
                this._showToast('启动失败', data.error || '未知错误', 'alert');
            }
        } catch (e) {
            this._showToast('连接错误', e.message, 'alert');
        }
    },

    async stopMonitoring() {
        try {
            await this._api('POST', '/api/stop');
        } catch (e) {
            this._showToast('连接错误', e.message, 'alert');
        }
    },

    /* ----------------------------------------------------------------
       配置管理
       ---------------------------------------------------------------- */

    async loadConfig() {
        try {
            const res = await this._api('GET', '/api/config');
            const config = await res.json();
            this._fillConfigForm(config);
            this._showToast('配置已加载', '', 'info');
        } catch (e) {
            this._showToast('加载失败', e.message, 'alert');
        }
    },

    async saveConfig() {
        const config = this._readConfigForm();
        try {
            const res = await this._api('PUT', '/api/config', config);
            const data = await res.json();
            if (data.ok) {
                this._showToast('配置已保存', '', 'info');
            } else {
                this._showToast('保存失败', data.error || '未知错误', 'alert');
            }
        } catch (e) {
            this._showToast('保存失败', e.message, 'alert');
        }
    },

    toggleSection(id) {
        const body = document.getElementById(id);
        const toggle = document.getElementById('toggle' + id.charAt(0).toUpperCase() + id.slice(1));
        if (!body) return;

        body.classList.toggle('collapsed');
        if (toggle) {
            toggle.classList.toggle('expanded');
        }
    },

    /* ----------------------------------------------------------------
       日志
       ---------------------------------------------------------------- */

    clearLogs() {
        const container = document.getElementById('logContainer');
        container.innerHTML = '';
    },

    _appendLog(entry) {
        const container = document.getElementById('logContainer');
        const div = document.createElement('div');

        let cls = 'log-entry';
        if (entry.message && entry.message.includes('[错误]')) cls += ' alert';
        else if (entry.message && entry.message.startsWith('[系统]')) cls += ' system';
        else if (entry.message && entry.message.includes('检测到目标')) cls += ' alert';

        div.className = cls;
        div.innerHTML =
            '<span class="log-time">' + this._escHtml(entry.time || '') + '</span>' +
            '<span class="log-msg">' + this._escHtml(entry.message || '') + '</span>';

        container.appendChild(div);

        // 限制日志条数
        while (container.children.length > 200) {
            container.removeChild(container.firstChild);
        }

        // 自动滚动到底部
        container.scrollTop = container.scrollHeight;
    },

    /* ----------------------------------------------------------------
       视频流
       ---------------------------------------------------------------- */

    _bindVideoFeed() {
        const img = document.getElementById('videoFeed');
        const placeholder = document.getElementById('videoPlaceholder');

        img.onload = () => {
            // FPS 计算
            this._fpsFrames++;
            const now = Date.now();
            const elapsed = now - this._fpsLast;
            if (elapsed >= 1000) {
                const fps = Math.round((this._fpsFrames * 1000) / elapsed);
                document.getElementById('badgeFps').textContent = fps + ' FPS';
                this._fpsFrames = 0;
                this._fpsLast = now;
            }
        };

        img.onerror = () => {
            img.style.display = 'none';
            placeholder.style.display = 'flex';
        };
    },

    _startVideo() {
        const img = document.getElementById('videoFeed');
        const placeholder = document.getElementById('videoPlaceholder');
        img.src = '/api/video?t=' + Date.now();
        img.style.display = 'block';
        placeholder.style.display = 'none';
        document.getElementById('badgeStatus').textContent = '在线';
        document.getElementById('badgeStatus').style.color = 'var(--accent-green)';
    },

    _stopVideo() {
        const img = document.getElementById('videoFeed');
        const placeholder = document.getElementById('videoPlaceholder');
        img.src = '';
        img.style.display = 'none';
        placeholder.style.display = 'flex';
        document.getElementById('badgeFps').textContent = '-- FPS';
        document.getElementById('badgeStatus').textContent = '离线';
        document.getElementById('badgeStatus').style.color = '';
    },

    /* ----------------------------------------------------------------
       SSE 连接
       ---------------------------------------------------------------- */

    _connectLogStream() {
        if (this._logSource) this._logSource.close();
        this._logSource = new EventSource('/api/logs');

        this._logSource.onmessage = (e) => {
            try {
                const entry = JSON.parse(e.data);
                this._appendLog(entry);
            } catch (_) {}
        };

        this._logSource.onerror = () => {
            // SSE 断开后自动重连（EventSource 内置机制）
        };
    },

    _connectAlertStream() {
        if (this._alertSource) this._alertSource.close();
        this._alertSource = new EventSource('/api/alerts');

        this._alertSource.onmessage = (e) => {
            try {
                const alert = JSON.parse(e.data);
                this._handleAlert(alert);
            } catch (_) {}
        };

        this._alertSource.onerror = () => {};
    },

    /* ----------------------------------------------------------------
       状态轮询
       ---------------------------------------------------------------- */

    _startStatusPolling() {
        const poll = async () => {
            try {
                const res = await this._api('GET', '/api/status');
                const data = await res.json();
                this._updateUI(data);
            } catch (_) {}
        };

        poll();
        this._statusTimer = setInterval(poll, 1000);
    },

    _updateUI(data) {
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        const startBtn = document.getElementById('btnStart');
        const stopBtn = document.getElementById('btnStop');

        // 清除所有状态类
        dot.className = 'status-dot';

        switch (data.status) {
            case 'idle':
                text.textContent = '就绪';
                startBtn.disabled = false;
                stopBtn.disabled = true;
                this._stopVideo();
                break;
            case 'starting':
                dot.classList.add('starting');
                text.textContent = data.init_message || '启动中...';
                startBtn.disabled = true;
                stopBtn.disabled = true;
                break;
            case 'monitoring':
                dot.classList.add('monitoring');
                text.textContent = '监控中';
                startBtn.disabled = true;
                stopBtn.disabled = false;
                this._startVideo();
                break;
            case 'stopping':
                dot.classList.add('stopping');
                text.textContent = '正在停止...';
                startBtn.disabled = true;
                stopBtn.disabled = true;
                break;
            case 'error':
                dot.classList.add('error');
                text.textContent = '错误: ' + (data.error || '');
                startBtn.disabled = false;
                stopBtn.disabled = true;
                this._stopVideo();
                break;
        }

        // 更新特性仪表板
        if (data.features) {
            this._updateFeatures(data.features);
        }
    },

    /* ----------------------------------------------------------------
       特性仪表板更新
       ---------------------------------------------------------------- */

    _updateFeatures(features) {
        // 番茄钟
        const pomo = features.pomodoro;
        const pomoBadge = document.getElementById('pomodoroBadge');
        const pomoTime = document.getElementById('pomodoroTime');
        const pomoDetail = document.getElementById('pomodoroDetail');
        const pomoRing = document.getElementById('pomodoroRing');

        if (pomo) {
            const mins = Math.floor(pomo.remaining_seconds / 60);
            const secs = pomo.remaining_seconds % 60;
            pomoTime.textContent = String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
            pomoDetail.textContent = `状态: ${pomo.state} | 已完成: ${pomo.completed_pomodoros}`;

            // 更新进度环 (周长 339.3)
            const ratio = pomo.state === 'idle' ? 0 : (pomo.remaining_seconds > 0 ? 1 - (pomo.remaining_seconds / (pomo.state === 'focus' ? 1500 : 300)) : 0);
            pomoRing.style.strokeDashoffset = 339.3 * (1 - ratio);

            pomoBadge.textContent = pomo.state;
            pomoBadge.className = 'feature-badge ' + (pomo.state === 'focus' ? 'active' : pomo.state === 'break' ? 'warning' : 'disabled');
        } else {
            pomoTime.textContent = '--:--';
            pomoDetail.textContent = '未启用';
            pomoRing.style.strokeDashoffset = 339.3;
            pomoBadge.textContent = '未启用';
            pomoBadge.className = 'feature-badge disabled';
        }

        // 疲劳检测
        const drow = features.drowsiness;
        const drowBadge = document.getElementById('drowsinessBadge');
        const drowGauge = document.getElementById('drowsinessGauge');
        const drowLabel = document.getElementById('drowsinessLabel');
        const drowDetail = document.getElementById('drowsinessDetail');

        if (drow) {
            const ear = drow.ear_value >= 0 ? drow.ear_value : 0;
            const earPercent = Math.min(100, Math.round(ear * 200));
            drowGauge.style.width = earPercent + '%';

            const level = drow.alert_level;
            if (level === 'normal') {
                drowGauge.style.background = 'var(--accent-green)';
                drowLabel.textContent = '正常';
                drowLabel.style.color = 'var(--accent-green)';
                drowBadge.textContent = '正常';
                drowBadge.className = 'feature-badge active';
            } else if (level === 'drowsy') {
                drowGauge.style.background = 'var(--accent-orange)';
                drowLabel.textContent = '疲劳';
                drowLabel.style.color = 'var(--accent-orange)';
                drowBadge.textContent = '疲劳';
                drowBadge.className = 'feature-badge warning';
            } else {
                drowGauge.style.background = 'var(--accent-red)';
                drowLabel.textContent = '严重';
                drowLabel.style.color = 'var(--accent-red)';
                drowBadge.textContent = '严重';
                drowBadge.className = 'feature-badge danger';
            }
            drowDetail.textContent = `EAR: ${ear >= 0 ? ear.toFixed(2) : 'N/A'} | 眨眼: ${drow.blink_rate.toFixed(0)}/min`;
        } else {
            drowGauge.style.width = '0%';
            drowLabel.textContent = '--';
            drowLabel.style.color = '';
            drowDetail.textContent = '未启用';
            drowBadge.textContent = '未启用';
            drowBadge.className = 'feature-badge disabled';
        }

        // 隐私保护 / 防偷窥
        const ss = features.shoulder_surfing;
        const ssBadge = document.getElementById('shoulderBadge');
        const ssDetail = document.getElementById('shoulderDetail');
        const ssIndicator = document.getElementById('privacyIndicator');
        const ssIcon = ssIndicator.querySelector('.privacy-icon');

        if (ss) {
            if (ss.is_vulnerable) {
                ssIndicator.className = 'privacy-indicator danger';
                ssIcon.textContent = '!';
                ssDetail.textContent = `检测到 ${ss.unauthorized_count} 个未授权人脸 / 共 ${ss.total_faces} 人`;
                ssBadge.textContent = '警告';
                ssBadge.className = 'feature-badge danger';
            } else {
                ssIndicator.className = 'privacy-indicator';
                ssIcon.textContent = '✓';
                ssDetail.textContent = `隐私安全 (${ss.total_faces} 张人脸)`;
                ssBadge.textContent = '安全';
                ssBadge.className = 'feature-badge active';
            }
        } else {
            ssIndicator.className = 'privacy-indicator';
            ssIcon.textContent = '✓';
            ssDetail.textContent = '未启用';
            ssBadge.textContent = '未启用';
            ssBadge.className = 'feature-badge disabled';
        }
    },

    /* ----------------------------------------------------------------
       告警处理
       ---------------------------------------------------------------- */

    _handleAlert(alert) {
        if (alert.type !== 'detection') return;

        // 冷却：5秒内不重复触发
        const now = Date.now();
        if (now - this._lastAlertTime < 5000) return;
        this._lastAlertTime = now;

        const person = alert.person || '未知';

        // 屏幕闪烁
        const overlay = document.getElementById('alertOverlay');
        overlay.classList.remove('flash');
        void overlay.offsetWidth; // 强制 reflow
        overlay.classList.add('flash');

        // Toast 通知
        this._showToast('⚠️ 检测到目标!', `发现: ${person}`, 'alert');

        // 浏览器通知
        this._sendNotification('Boss Sentinel 检测到目标', `发现: ${person}`);

        // 声音告警
        this._playAlertSound();
    },

    /* ----------------------------------------------------------------
       通知 & 音频
       ---------------------------------------------------------------- */

    _requestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    },

    _sendNotification(title, body) {
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(title, { body, icon: '🛡️', tag: 'boss-sentinel' });
        }
    },

    _prepareAudio() {
        // 创建告警音频上下文（延迟初始化，需要用户交互）
        this._audioCtx = null;
    },

    _playAlertSound() {
        try {
            if (!this._audioCtx) {
                this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            const ctx = this._audioCtx;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.frequency.setValueAtTime(880, ctx.currentTime);
            osc.frequency.setValueAtTime(660, ctx.currentTime + 0.15);
            osc.frequency.setValueAtTime(880, ctx.currentTime + 0.3);

            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);

            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.5);
        } catch (_) {}
    },

    /* ----------------------------------------------------------------
       Toast
       ---------------------------------------------------------------- */

    _showToast(title, message, type) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = 'toast ' + (type || 'info');
        toast.innerHTML =
            '<div class="toast-title">' + this._escHtml(title) + '</div>' +
            (message ? '<div class="toast-message">' + this._escHtml(message) + '</div>' : '');

        container.appendChild(toast);

        // 4秒后移除
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(30px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    },

    /* ----------------------------------------------------------------
       配置表单读写
       ---------------------------------------------------------------- */

    _readConfigForm() {
        const val = (id) => document.getElementById(id)?.value ?? '';
        const checked = (id) => document.getElementById(id)?.checked ?? false;
        const num = (id) => parseFloat(val(id));
        const intVal = (id) => parseInt(val(id), 10);

        const config = {
            model_path: val('cfgModelPath'),
            known_faces_dir: val('cfgKnownFacesDir'),
            threshold: num('cfgThreshold'),
            confidence_threshold: num('cfgConfidence'),
            frame_skip: intVal('cfgFrameSkip'),
            cameras: val('cfgCameras').split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n)),
            log_file: val('cfgLogFile'),
            use_gpu: checked('cfgUseGpu'),
            lock_cooldown: intVal('cfgLockCooldown'),
            notify_cooldown: intVal('cfgNotifyCooldown'),
            alert_sound: checked('cfgAlertSound'),
            alert_tray: checked('cfgAlertTray'),

            enable_shoulder_surfing: checked('cfgShoulderSurfing'),
            enable_intruder_capture: checked('cfgIntruderCapture'),
            intruder_save_dir: val('cfgIntruderSaveDir'),
            enable_pomodoro: checked('cfgPomodoro'),
            pomodoro_focus_minutes: intVal('cfgFocusMinutes'),
            pomodoro_break_minutes: intVal('cfgBreakMinutes'),
            enable_mqtt: checked('cfgMqtt'),
            mqtt_broker: val('cfgMqttBroker'),
            mqtt_port: intVal('cfgMqttPort'),
            mqtt_topic_prefix: val('cfgMqttTopic'),
            enable_drowsiness: checked('cfgDrowsiness'),
            drowsiness_ear_threshold: num('cfgEarThreshold'),
        };

        // 邮件配置
        if (checked('cfgEmailEnabled') && val('cfgEmailSender')) {
            config.notification_email = {
                sender: val('cfgEmailSender'),
                receiver: val('cfgEmailReceiver'),
                smtp_server: val('cfgSmtpServer'),
                smtp_port: intVal('cfgSmtpPort'),
                username: val('cfgEmailSender'),
                password: val('cfgEmailPassword'),
                use_ssl: checked('cfgEmailSsl'),
            };
        }

        return config;
    },

    _fillConfigForm(cfg) {
        const val = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        const check = (id, v) => { const el = document.getElementById(id); if (el) el.checked = v; };

        val('cfgModelPath', cfg.model_path || 'yolov8n-face.pt');
        val('cfgKnownFacesDir', cfg.known_faces_dir || 'known_faces');
        val('cfgThreshold', cfg.threshold ?? 0.7);
        val('cfgConfidence', cfg.confidence_threshold ?? 0.7);
        val('cfgFrameSkip', cfg.frame_skip ?? 3);
        val('cfgCameras', (cfg.cameras || [0]).join(','));
        val('cfgLogFile', cfg.log_file || 'sentinel_log.txt');
        check('cfgUseGpu', cfg.use_gpu !== false);
        val('cfgLockCooldown', cfg.lock_cooldown ?? 30);
        val('cfgNotifyCooldown', cfg.notify_cooldown ?? 60);
        check('cfgAlertSound', cfg.alert_sound !== false);
        check('cfgAlertTray', cfg.alert_tray !== false);

        // 邮件
        const email = cfg.notification_email;
        if (email) {
            check('cfgEmailEnabled', true);
            val('cfgSmtpServer', email.smtp_server || '');
            val('cfgSmtpPort', email.smtp_port || 587);
            val('cfgEmailSender', email.sender || '');
            val('cfgEmailPassword', email.password || '');
            val('cfgEmailReceiver', email.receiver || '');
            check('cfgEmailSsl', !!email.use_ssl);
        }

        // 扩展特性
        check('cfgShoulderSurfing', !!cfg.enable_shoulder_surfing);
        check('cfgIntruderCapture', !!cfg.enable_intruder_capture);
        val('cfgIntruderSaveDir', cfg.intruder_save_dir || 'intruder_photos');
        check('cfgPomodoro', !!cfg.enable_pomodoro);
        val('cfgFocusMinutes', cfg.pomodoro_focus_minutes ?? 25);
        val('cfgBreakMinutes', cfg.pomodoro_break_minutes ?? 5);
        check('cfgMqtt', !!cfg.enable_mqtt);
        val('cfgMqttBroker', cfg.mqtt_broker || '');
        val('cfgMqttPort', cfg.mqtt_port ?? 1883);
        val('cfgMqttTopic', cfg.mqtt_topic_prefix || 'boss_sentinel');
        check('cfgDrowsiness', !!cfg.enable_drowsiness);
        val('cfgEarThreshold', cfg.drowsiness_ear_threshold ?? 0.2);
    },

    /* ----------------------------------------------------------------
       工具
       ---------------------------------------------------------------- */

    async _api(method, path, body) {
        const opts = { method, headers: {} };
        if (body) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(body);
        }
        return fetch(path, opts);
    },

    _escHtml(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    },
};

/* ================================================================
   启动
   ================================================================ */

document.addEventListener('DOMContentLoaded', () => {
    app.init();
    // 启动后自动加载配置
    app.loadConfig();
});
