document.addEventListener('alpine:init', () => {
    const CURRENT_SESSION_KEY = 'prlmad.currentSessionId';

    Alpine.store('app', {
        currentSessionId: '',
        sessions: [],
        rawProfile: {},
        profileDimensions: [],
        loading: false,
        initialized: false,
        busyTasks: {},

        get currentSession() {
            return this.sessions.find(s => s.session_id === this.currentSessionId) || null;
        },

        get hasBusyTasks() {
            return Object.values(this.busyTasks).some(Boolean);
        },

        get busyTaskNames() {
            const names = {
                generate: '资源生成',
                tutor: '智能辅导',
                path: '学习路径生成',
                evaluate: '效果评估',
            };
            return Object.keys(this.busyTasks)
                .filter(key => this.busyTasks[key])
                .map(key => names[key] || key);
        },

        async init() {
            this.loading = true;
            await this.loadSessions();
            const hash = window.location.hash.slice(1);
            const savedSessionId = localStorage.getItem(CURRENT_SESSION_KEY) || '';

            if (hash && this.sessions.find(s => s.session_id === hash)) {
                await this.setCurrentSession(hash, { updateHash: false, notify: false });
            } else if (savedSessionId && this.sessions.find(s => s.session_id === savedSessionId)) {
                await this.setCurrentSession(savedSessionId, { updateHash: false, notify: false });
            } else if (this.sessions.length > 0) {
                await this.setCurrentSession(this.sessions[0].session_id, { updateHash: false, notify: false });
            }

            window.addEventListener('hashchange', async () => {
                const h = window.location.hash.slice(1);
                if (h && h !== this.currentSessionId && this.sessions.find(s => s.session_id === h)) {
                    await this.setCurrentSession(h, { updateHash: false });
                }
            });
            window.addEventListener('beforeunload', (event) => {
                if (!this.hasBusyTasks) return;
                event.preventDefault();
                event.returnValue = '';
            });

            this.initialized = true;
            this.loading = false;
        },

        setBusy(task, value) {
            this.busyTasks = { ...this.busyTasks, [task]: Boolean(value) };
        },

        confirmBusyAction(actionText = '切换页面') {
            if (!this.hasBusyTasks) return true;
            const tasks = this.busyTaskNames.join('、') || 'AI 生成任务';
            return confirm(`${tasks}正在进行中。${actionText}会中断当前页面的生成过程，确定继续吗？`);
        },

        confirmNavigation(event) {
            if (!this.confirmBusyAction('切换板块')) {
                event.preventDefault();
                event.stopPropagation();
                return false;
            }
            return true;
        },

        async loadSessions() {
            try {
                const resp = await fetch('/api/sessions');
                this.sessions = await resp.json();
            } catch (e) {
                console.error('Failed to load sessions', e);
                this.sessions = [];
            }
        },

        makeUniqueSessionName(baseName) {
            const base = (baseName || '操作系统学习').trim() || '操作系统学习';
            const names = new Set(this.sessions.map(s => s.name));
            if (!names.has(base)) return base;
            let index = 2;
            let candidate = `${base} ${index}`;
            while (names.has(candidate)) {
                index += 1;
                candidate = `${base} ${index}`;
            }
            return candidate;
        },

        async setCurrentSession(sid, options = {}) {
            const { updateHash = true, notify = true } = options;
            const nextSessionId = sid || '';
            if (nextSessionId && !this.sessions.find(s => s.session_id === nextSessionId)) {
                return;
            }
            const changed = this.currentSessionId !== nextSessionId;
            if (changed) {
                this.rawProfile = {};
                this.profileDimensions = [];
            }
            this.currentSessionId = nextSessionId;
            if (nextSessionId) {
                localStorage.setItem(CURRENT_SESSION_KEY, nextSessionId);
            } else {
                localStorage.removeItem(CURRENT_SESSION_KEY);
            }
            if (updateHash) {
                if (nextSessionId) {
                    history.replaceState(null, '', `${window.location.pathname}#${nextSessionId}`);
                } else {
                    history.replaceState(null, '', window.location.pathname);
                }
            }
            await this.loadProfile();
            if (notify && changed) {
                window.dispatchEvent(new CustomEvent('prlmad:session-changed', {
                    detail: { sessionId: nextSessionId },
                }));
            }
        },

        async loadProfile() {
            const sid = this.currentSessionId;
            if (!sid) {
                this.rawProfile = {};
                this.profileDimensions = [];
                return;
            }
            try {
                const resp = await fetch(`/api/profile/${sid}`);
                const profile = (await resp.json()) || {};
                if (this.currentSessionId !== sid) return;
                this.rawProfile = profile;
                const dimNames = {
                    major: '专业方向', grade: '年级', goal: '学习目标',
                    knowledge_level: '知识基础', cognitive_style: '认知风格',
                    preferences: '资源偏好', weak_points: '薄弱知识点',
                    available_time: '可用时间', learning_motivation: '学习动机',
                    problem_solving: '问题解决能力', practical_ability: '实践能力',
                    learning_habits: '学习习惯',
                };
                this.profileDimensions = Object.entries(profile)
                    .filter(([k, v]) => v && typeof v === 'string' && v.trim() && dimNames[k])
                    .map(([k, v]) => ({ label: dimNames[k], value: v.length > 60 ? v.slice(0, 57) + '...' : v }))
                    .slice(0, 10);
            } catch (e) {
                console.error('Failed to load profile', e);
                this.rawProfile = {};
                this.profileDimensions = [];
            }
        },

        async createSession(name) {
            const sessionName = this.makeUniqueSessionName(name || '操作系统学习');
            try {
                const resp = await fetch('/api/session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: sessionName }),
                });
                const data = await resp.json();
                this.sessions.unshift({
                    session_id: data.session_id,
                    name: data.name,
                    course: data.course,
                    profile: {},
                    message_count: 0,
                    resource_count: 0,
                    created_at: data.created_at,
                    updated_at: data.created_at,
                });
                this.rawProfile = {};
                this.profileDimensions = [];
                await this.setCurrentSession(data.session_id);
                return data.session_id;
            } catch (e) {
                alert('创建会话失败: ' + e.message);
                return null;
            }
        },

        async createSessionPrompt() {
            if (!this.confirmBusyAction('新建会话')) return null;
            const defaultName = this.makeUniqueSessionName('操作系统学习');
            const name = prompt('请输入会话名称:', defaultName);
            if (name === null) return null;
            return await this.createSession(name);
        },

        async switchSession(sid) {
            if (sid !== this.currentSessionId && !this.confirmBusyAction('切换会话')) return;
            await this.setCurrentSession(sid);
        },

        async renameCurrentSession() {
            const current = this.currentSession;
            if (!current) return;
            const name = prompt('重命名当前学习会话:', current.name);
            if (name === null) return;
            const nextName = name.trim();
            if (!nextName || nextName === current.name) return;
            try {
                const resp = await fetch(`/api/session/${current.session_id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: nextName }),
                });
                if (!resp.ok) throw new Error('服务端拒绝了重命名请求');
                current.name = nextName;
            } catch (e) {
                alert('重命名失败: ' + e.message);
            }
        },

        async deleteCurrentSession() {
            const current = this.currentSession;
            if (!current) return;
            if (!this.confirmBusyAction('删除会话')) return;
            const ok = confirm(`确定删除「${current.name}」吗？该会话的聊天记录、资源、路径和评估会一起删除。`);
            if (!ok) return;
            try {
                const resp = await fetch(`/api/session/${current.session_id}`, { method: 'DELETE' });
                if (!resp.ok) throw new Error('服务端拒绝了删除请求');
                const deletedIndex = this.sessions.findIndex(s => s.session_id === current.session_id);
                this.sessions = this.sessions.filter(s => s.session_id !== current.session_id);
                const fallback = this.sessions[Math.max(0, deletedIndex - 1)] || this.sessions[0] || null;
                await this.setCurrentSession(fallback?.session_id || '');
            } catch (e) {
                alert('删除失败: ' + e.message);
            }
        },
    });
});

window.PRLMAD = {
    parseSse(buffer, onEvent) {
        const frames = buffer.split(/\r?\n\r?\n/);
        const rest = frames.pop() || '';

        for (const frame of frames) {
            if (!frame.trim()) continue;
            let eventName = 'message';
            const dataLines = [];

            for (const line of frame.split(/\r?\n/)) {
                if (line.startsWith('event:')) {
                    eventName = line.slice(6).trim();
                } else if (line.startsWith('data:')) {
                    dataLines.push(line.slice(5).trimStart());
                }
            }

            const rawData = dataLines.join('\n');
            let data = {};
            if (rawData) {
                try {
                    data = JSON.parse(rawData);
                } catch (e) {
                    data = rawData;
                }
            }
            onEvent(eventName, data);
        }

        return rest;
    },
};

if (window.marked) {
    marked.setOptions({ breaks: true, gfm: true });
}
