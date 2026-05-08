document.addEventListener('alpine:init', () => {
    Alpine.store('app', {
        currentSessionId: '',
        sessions: [],
        rawProfile: {},
        profileDimensions: [],
        loading: false,
        initialized: false,

        get currentSession() {
            return this.sessions.find(s => s.session_id === this.currentSessionId) || null;
        },

        async init() {
            this.loading = true;
            await this.loadSessions();
            const hash = window.location.hash.slice(1);

            if (hash && this.sessions.find(s => s.session_id === hash)) {
                this.currentSessionId = hash;
            } else if (this.sessions.length > 0) {
                this.currentSessionId = this.sessions[0].session_id;
            }

            if (this.currentSessionId) {
                await this.loadProfile();
            }

            window.addEventListener('hashchange', async () => {
                const h = window.location.hash.slice(1);
                if (h && this.sessions.find(s => s.session_id === h)) {
                    this.currentSessionId = h;
                    await this.loadProfile();
                }
            });

            this.initialized = true;
            this.loading = false;
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

        async loadProfile() {
            if (!this.currentSessionId) return;
            try {
                const resp = await fetch(`/api/profile/${this.currentSessionId}`);
                const profile = await resp.json();
                this.rawProfile = profile || {};
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
                    .slice(0, 8);
            } catch (e) {
                console.error('Failed to load profile', e);
                this.rawProfile = {};
                this.profileDimensions = [];
            }
        },

        async createSession(name) {
            const sessionName = name || '操作系统学习';
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
                this.currentSessionId = data.session_id;
                this.rawProfile = {};
                this.profileDimensions = [];
                window.location.hash = data.session_id;
                return data.session_id;
            } catch (e) {
                alert('创建会话失败: ' + e.message);
                return null;
            }
        },

        async createSessionPrompt() {
            const name = prompt('请输入会话名称:', '操作系统学习');
            if (name === null) return null;
            return await this.createSession(name);
        },

        switchSession(sid) {
            this.currentSessionId = sid;
            window.location.hash = sid;
            this.loadProfile();
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
            const ok = confirm(`确定删除「${current.name}」吗？该会话的聊天记录、资源、路径和评估会一起删除。`);
            if (!ok) return;
            try {
                const resp = await fetch(`/api/session/${current.session_id}`, { method: 'DELETE' });
                if (!resp.ok) throw new Error('服务端拒绝了删除请求');
                this.sessions = this.sessions.filter(s => s.session_id !== current.session_id);
                this.currentSessionId = this.sessions[0]?.session_id || '';
                this.rawProfile = {};
                this.profileDimensions = [];
                window.location.hash = this.currentSessionId || '';
                if (this.currentSessionId) await this.loadProfile();
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
