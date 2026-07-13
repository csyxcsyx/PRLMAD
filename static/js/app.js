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

    Alpine.data('sessionSwitcher', () => ({
        open: false,

        get currentSession() {
            return Alpine.store('app').currentSession;
        },

        get sessions() {
            return Alpine.store('app').sessions;
        },

        toggle() {
            if (!this.sessions.length) return;
            this.open = !this.open;
        },

        close() {
            this.open = false;
        },

        async choose(sessionId) {
            this.close();
            if (!sessionId || sessionId === Alpine.store('app').currentSessionId) return;
            await Alpine.store('app').switchSession(sessionId);
        },
    }));
});

window.PRLMAD = {
    assetPromises: new Map(),

    loadScript(src, globalName = '') {
        if (globalName && window[globalName]) return Promise.resolve(window[globalName]);
        if (!this.assetPromises.has(src)) {
            this.assetPromises.set(src, new Promise((resolve, reject) => {
                const existing = document.querySelector(`script[src="${src}"]`);
                if (existing?.dataset.loaded === 'true') {
                    resolve(globalName ? window[globalName] : true);
                    return;
                }
                const element = existing || document.createElement('script');
                const onLoad = () => {
                    element.dataset.loaded = 'true';
                    resolve(globalName ? window[globalName] : true);
                };
                element.addEventListener('load', onLoad, { once: true });
                element.addEventListener('error', () => {
                    this.assetPromises.delete(src);
                    reject(new Error(`无法加载本地资源: ${src}`));
                }, { once: true });
                if (!existing) {
                    element.src = src;
                    element.defer = true;
                    document.head.appendChild(element);
                }
            }));
        }
        return this.assetPromises.get(src);
    },

    normalizeAiText(value) {
        let text = String(value || '').replace(/\r\n?/g, '\n').trimStart();
        const wrappedMarkdown = text.match(/^```(?:markdown|md)\s*\n([\s\S]*?)\n```\s*$/i);
        if (wrappedMarkdown) text = wrappedMarkdown[1];
        return text
            .replace(/^(#{1,6})([^#\s])/gm, '$1 $2')
            .replace(/\n{3,}/g, '\n\n');
    },

    renderMarkdown(value) {
        const text = this.normalizeAiText(value);
        if (!window.marked) {
            return text.replace(/[&<>"']/g, char => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
            })[char]).replace(/\n/g, '<br>');
        }
        return window.marked.parse(text);
    },

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

window.PRLMAD.createNavigation = () => {
    const registeredPages = new Set([document.body.dataset.page || 'chat']);
    const scriptCache = new Map();
    const pageCache = new Map();
    const livePages = new Map();
    const navigationPaths = [
        '/page/chat', '/page/generate', '/page/learning-path',
        '/page/tutor', '/page/evaluate', '/page/knowledge',
    ];
    let renderedPath = window.location.pathname;
    let navigationVersion = 0;

    livePages.set(renderedPath, {
        page: document.body.dataset.page || 'chat',
        title: document.title,
        fragment: null,
    });

    function currentUrl(pathname) {
        const sid = Alpine.store('app')?.currentSessionId || window.location.hash.slice(1) || '';
        return sid ? `${pathname}#${sid}` : pathname;
    }

    function setLoading(value, finished = false) {
        const main = document.querySelector('.app-main');
        const bar = document.getElementById('pageLoadingBar');
        main?.classList.toggle('is-navigating', value);
        main?.setAttribute('aria-busy', value ? 'true' : 'false');
        if (!bar) return;
        bar.classList.toggle('active', value);
        bar.classList.toggle('done', finished);
        if (finished) {
            window.setTimeout(() => bar.classList.remove('done'), 240);
        }
    }

    function updateNavigation(page) {
        document.body.dataset.page = page;
        document.querySelectorAll('[data-app-nav]').forEach(link => {
            const active = link.dataset.pageTarget === page;
            link.classList.toggle('active', active);
            if (active) link.setAttribute('aria-current', 'page');
            else link.removeAttribute('aria-current');
        });
    }

    function runRegistration(source) {
        const opening = /document\.addEventListener\(['"]alpine:init['"],\s*\(\)\s*=>\s*\{/;
        if (!opening.test(source)) return;
        const body = source.replace(opening, '').replace(/\}\);\s*$/, '');
        Function(body)();
    }

    async function registerPageComponent(doc, page) {
        if (registeredPages.has(page)) return;
        const scripts = Array.from(doc.querySelectorAll('script'));
        for (const script of scripts) {
            const src = script.getAttribute('src') || '';
            const isPageScript = src === '/static/js/chat.js' || script.textContent.includes('Alpine.data(');
            if (!isPageScript) continue;
            let source = script.textContent;
            if (src) {
                if (!scriptCache.has(src)) {
                    scriptCache.set(src, fetch(src).then(response => {
                        if (!response.ok) throw new Error(`无法加载页面脚本: ${src}`);
                        return response.text();
                    }));
                }
                source = await scriptCache.get(src);
            }
            runRegistration(source);
        }
        registeredPages.add(page);
    }

    function loadPage(pathname) {
        if (pageCache.has(pathname)) return pageCache.get(pathname);
        const request = fetch(pathname, {
            headers: { 'X-PRLMAD-Navigation': 'prefetch' },
        }).then(async response => {
            if (!response.ok) throw new Error(`页面加载失败 (${response.status})`);
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const nextMain = doc.querySelector('.app-main');
            const page = doc.body.dataset.page;
            if (!nextMain || !page) throw new Error('页面内容不完整');
            await registerPageComponent(doc, page);
            return { html: nextMain.innerHTML, page, title: doc.title || document.title };
        }).catch(error => {
            pageCache.delete(pathname);
            throw error;
        });
        pageCache.set(pathname, request);
        return request;
    }

    function detachCurrentPage(main) {
        const current = livePages.get(renderedPath);
        if (!current) return;
        const fragment = document.createDocumentFragment();
        Alpine.mutateDom(() => {
            while (main.firstChild) fragment.appendChild(main.firstChild);
        });
        current.fragment = fragment;
    }

    function mountPage(main, pathname, payload) {
        detachCurrentPage(main);
        const cached = livePages.get(pathname);
        let needsInitialization = false;
        Alpine.mutateDom(() => {
            if (cached?.fragment) {
                main.appendChild(cached.fragment);
                cached.fragment = null;
            } else {
                main.innerHTML = payload.html;
                needsInitialization = true;
            }
        });
        if (needsInitialization) {
            Alpine.initTree(main);
            livePages.set(pathname, {
                page: payload.page,
                title: payload.title,
                fragment: null,
            });
        }
    }

    function refreshMountedVisuals() {
        window.requestAnimationFrame(() => {
            window.dispatchEvent(new Event('resize'));
            const chart = document.getElementById('radarChart');
            if (chart && window.echarts) window.echarts.getInstanceByDom(chart)?.resize();
        });
    }

    function swapWorkspace(pathname, payload) {
        const main = document.querySelector('.app-main');
        const swap = () => {
            main.dataset.navigationSource = livePages.get(pathname)?.fragment ? 'memory' : 'prepared';
            mountPage(main, pathname, payload);
            renderedPath = pathname;
            updateNavigation(payload.page);
            document.title = payload.title;
            main.classList.remove('workspace-enter');
            if (!document.startViewTransition) {
                void main.offsetWidth;
                main.classList.add('workspace-enter');
            }
            refreshMountedVisuals();
        };
        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (document.startViewTransition && !reducedMotion) {
            document.startViewTransition(swap);
        } else {
            swap();
        }
    }

    async function navigate(pathname, options = {}) {
        const { push = true } = options;
        const startedAt = window.performance.now();
        const target = new URL(pathname, window.location.origin);
        if (target.origin !== window.location.origin) {
            window.location.assign(target.href);
            return false;
        }
        if (target.pathname === window.location.pathname && push) {
            return true;
        }
        const version = ++navigationVersion;
        let loadingShown = false;
        const loadingTimer = window.setTimeout(() => {
            loadingShown = true;
            setLoading(true);
        }, 120);
        try {
            const live = livePages.get(target.pathname);
            const payload = live || await loadPage(target.pathname);
            if (version !== navigationVersion) return false;
            swapWorkspace(target.pathname, payload);

            const nextUrl = currentUrl(target.pathname);
            if (push) history.pushState({ page: payload.page }, '', nextUrl);
            else history.replaceState({ page: payload.page }, '', nextUrl);
            document.documentElement.dataset.lastNavigationMs = String(
                Math.round(window.performance.now() - startedAt)
            );
            window.dispatchEvent(new CustomEvent('prlmad:page-changed', { detail: { page: payload.page } }));
            return true;
        } catch (error) {
            console.error('局部页面切换失败，回退到完整导航', error);
            window.location.assign(currentUrl(target.pathname));
            return false;
        } finally {
            window.clearTimeout(loadingTimer);
            if (loadingShown) setLoading(false, true);
        }
    }

    function prefetch(pathname) {
        const target = new URL(pathname, window.location.origin);
        if (target.origin !== window.location.origin || target.pathname === renderedPath) return;
        loadPage(target.pathname).catch(() => {});
    }

    document.addEventListener('click', event => {
        const link = event.target.closest('a[data-app-nav]');
        if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        navigate(link.href);
    });

    document.addEventListener('pointerover', event => {
        const link = event.target.closest('a[data-app-nav]');
        if (link) prefetch(link.href);
    }, { passive: true });

    document.addEventListener('focusin', event => {
        const link = event.target.closest('a[data-app-nav]');
        if (link) prefetch(link.href);
    });

    window.addEventListener('popstate', async () => {
        const requestedPath = window.location.pathname;
        await navigate(requestedPath, { push: false });
    });

    updateNavigation(document.body.dataset.page);
    history.replaceState({ page: document.body.dataset.page }, '', currentUrl(window.location.pathname));
    const warmCache = () => navigationPaths.forEach(prefetch);
    if ('requestIdleCallback' in window) window.requestIdleCallback(warmCache, { timeout: 1500 });
    else window.setTimeout(warmCache, 250);
    return { navigate, prefetch };
};

function initializeWorkspaceNavigation() {
    if (window.PRLMAD.navigation || !window.Alpine) return;
    window.PRLMAD.navigation = window.PRLMAD.createNavigation();
    document.documentElement.classList.add('navigation-ready');
}

document.addEventListener('DOMContentLoaded', initializeWorkspaceNavigation);

if (window.marked) {
    marked.setOptions({ breaks: true, gfm: true });
}
