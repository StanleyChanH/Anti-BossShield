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

    async toggleLock(enabled) {
        try {
            const res = await this._api('POST', '/api/toggle_lock', { enabled });
            const data = await res.json();
            if (data.ok) {
                this._showToast(
                    enabled ? '锁屏已开启' : '锁屏已关闭',
                    enabled ? '检测到目标时将自动锁屏' : '检测到目标时仅记录日志，不执行锁屏',
                    'info'
                );
            }
        } catch (e) {
            this._showToast('操作失败', e.message, 'alert');
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
        this._updateFeatures(data.features || {}, data.enabled_features || {});

        // 同步锁屏开关状态
        const lockToggle = document.getElementById('cfgEnableLock');
        if (lockToggle && data.lock_enabled !== undefined) {
            lockToggle.checked = data.lock_enabled;
        }
    },

    /* ----------------------------------------------------------------
       特性仪表板更新
       ---------------------------------------------------------------- */

    _updateFeatures(features, enabledFeatures) {
        const isFeatureEnabled = (name) => enabledFeatures[name] === true;

        // 番茄钟
        const pomo = features.pomodoro;
        const pomoBadge = document.getElementById('pomodoroBadge');
        const pomoTime = document.getElementById('pomodoroTime');
        const pomoDetail = document.getElementById('pomodoroDetail');
        const pomoRing = document.getElementById('pomodoroRing');

        if (pomo) {
            const total = Math.floor(pomo.remaining_seconds);
            const hrs = Math.floor(total / 3600);
            const mins = Math.floor((total % 3600) / 60);
            const secs = total % 60;
            if (hrs > 0) {
                pomoTime.textContent = hrs + ':' + String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
            } else {
                pomoTime.textContent = String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
            }
            pomoDetail.textContent = `状态: ${pomo.state} | 已完成: ${pomo.completed_pomodoros}`;

            // 更新进度环 (周长 339.3)
            const ratio = pomo.state === 'idle' ? 0 : (pomo.remaining_seconds > 0 ? 1 - (pomo.remaining_seconds / (pomo.state === 'focus' ? 1500 : 300)) : 0);
            pomoRing.style.strokeDashoffset = 339.3 * (1 - ratio);

            pomoBadge.textContent = pomo.state;
            pomoBadge.className = 'feature-badge ' + (pomo.state === 'focus' ? 'active' : pomo.state === 'break' ? 'warning' : 'disabled');
        } else if (isFeatureEnabled('pomodoro')) {
            pomoTime.textContent = '--:--';
            pomoDetail.textContent = '已启用，等待数据...';
            pomoRing.style.strokeDashoffset = 339.3;
            pomoBadge.textContent = '已启用';
            pomoBadge.className = 'feature-badge active';
        } else {
            pomoTime.textContent = '--:--';
            pomoDetail.textContent = '未启用';
            pomoRing.style.strokeDashoffset = 339.3;
            pomoBadge.textContent = '未启用';
            pomoBadge.className = 'feature-badge disabled';
        }

        // 头部姿态 / 注意力追踪
        const hp = features.head_pose;
        const hpBadge = document.getElementById('headPoseBadge');
        const hpDetail = document.getElementById('headPoseDetail');
        const hpAttention = document.getElementById('attentionStatus');
        const hpFocus = document.getElementById('focusScore');
        const hpIndicator = document.getElementById('attentionIndicator');
        const hpIcon = document.getElementById('attentionIcon');

        if (hp) {
            const statusMap = {
                focused: { icon: '🎯', text: '专注', color: 'var(--accent-green)', badgeClass: 'active' },
                distracted: { icon: '👀', text: '分心', color: 'var(--accent-orange)', badgeClass: 'warning' },
                away: { icon: '🚶', text: '离开', color: 'var(--accent-red)', badgeClass: 'danger' },
            };
            const info = statusMap[hp.attention_status] || statusMap.focused;
            hpIcon.textContent = info.icon;
            hpAttention.textContent = info.text;
            hpAttention.style.color = info.color;
            hpIndicator.className = 'attention-indicator ' + (hp.looking_at_screen ? '' : 'away');
            hpFocus.textContent = '专注度: ' + Math.round(hp.focus_score * 100) + '%';
            hpDetail.textContent = `偏转: ${hp.yaw.toFixed(0)}° / ${hp.pitch.toFixed(0)}° | ${hp.attention_status}`;
            hpBadge.textContent = info.text;
            hpBadge.className = 'feature-badge ' + info.badgeClass;
        } else if (isFeatureEnabled('head_pose')) {
            hpIcon.textContent = '👁️';
            hpAttention.textContent = '--';
            hpAttention.style.color = 'var(--accent-blue)';
            hpFocus.textContent = '专注度: --%';
            hpDetail.textContent = '已启用，等待检测...';
            hpBadge.textContent = '已启用';
            hpBadge.className = 'feature-badge active';
        } else {
            hpIcon.textContent = '👁️';
            hpAttention.textContent = '--';
            hpAttention.style.color = '';
            hpFocus.textContent = '专注度: --%';
            hpDetail.textContent = '未启用';
            hpBadge.textContent = '未启用';
            hpBadge.className = 'feature-badge disabled';
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
        } else if (isFeatureEnabled('shoulder_surfing')) {
            ssIndicator.className = 'privacy-indicator';
            ssIcon.textContent = '✓';
            ssDetail.textContent = '已启用，等待检测...';
            ssBadge.textContent = '已启用';
            ssBadge.className = 'feature-badge active';
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
            enable_head_pose: checked('cfgHeadPose'),
            head_pose_alert_threshold: num('cfgHeadPoseThreshold'),
            enable_lock: checked('cfgEnableLock'),
            roles: this._readRolesForm(),
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
        check('cfgHeadPose', !!cfg.enable_head_pose);
        val('cfgHeadPoseThreshold', cfg.head_pose_alert_threshold ?? 30);

        // 角色配置
        this._fillRolesForm(cfg.roles || {});
        this._loadFaces();
    },

    /* ----------------------------------------------------------------
       角色管理
       ---------------------------------------------------------------- */

    _loadFaces() {
        fetch('/api/faces').then(r => r.json()).then(faces => {
            this._renderRolesGrid(faces);
        }).catch(() => {
            const container = document.getElementById('rolesContainer');
            if (container) container.innerHTML = '<p class="config-hint">无法加载人脸列表</p>';
        });
    },

    _renderRolesGrid(faces) {
        const container = document.getElementById('rolesContainer');
        if (!container) return;

        if (!faces || faces.length === 0) {
            container.innerHTML = '<p class="config-hint">known_faces/ 目录中暂无已知人脸。请添加照片后重试。</p>';
            return;
        }

        const roles = this._currentRoles || {};
        let html = '';
        for (const face of faces) {
            const currentRole = face.role || ((roles.owner || []).includes(face.name) ? 'owner'
                : (roles.boss || []).includes(face.name) ? 'boss'
                : (roles.colleague || []).includes(face.name) ? 'colleague' : '');
            html += '<div class="role-assignment">'
                + '<span class="role-face-name">' + this._escHtml(face.name) + '</span>'
                + '<span class="role-face-photos">' + face.photos + ' 张照片</span>'
                + '<select class="role-select" data-name="' + this._escHtml(face.name) + '">'
                + '<option value=""' + (!currentRole ? ' selected' : '') + '>未分配</option>'
                + '<option value="owner"' + (currentRole === 'owner' ? ' selected' : '') + '>🏠 主人</option>'
                + '<option value="boss"' + (currentRole === 'boss' ? ' selected' : '') + '>👔 Boss</option>'
                + '<option value="colleague"' + (currentRole === 'colleague' ? ' selected' : '') + '>👥 同事</option>'
                + '</select>'
                + '</div>';
        }
        container.innerHTML = html;
    },

    _readRolesForm() {
        const roles = { owner: [], boss: [], colleague: [] };
        const selects = document.querySelectorAll('.role-select');
        selects.forEach(sel => {
            const name = sel.dataset.name;
            const role = sel.value;
            if (role && roles[role]) {
                roles[role].push(name);
            }
        });
        return roles;
    },

    _fillRolesForm(roles) {
        this._currentRoles = roles || {};
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
