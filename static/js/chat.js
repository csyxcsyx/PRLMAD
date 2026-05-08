document.addEventListener('alpine:init', () => {
    Alpine.data('chatPage', () => ({
        chatInput: '',
        chatMessages: [],
        isStreaming: false,
        profileUpdating: false,
        requestSeq: 0,
        activeRequestId: 0,
        streamingContent: '',
        streamingContentMd: '',
        quickReplies: [],
        currentStep: 1,
        totalSteps: 7,
        profileVersion: 1,
        showProfileDetail: false,

        get showWelcome() {
            return !Alpine.store('app').currentSessionId;
        },

        get profileProgress() {
            const dims = Alpine.store('app').profileDimensions.length;
            return Math.min(Math.round((dims / 8) * 100), 100);
        },

        init() {
            this.$watch('$store.app.initialized', (val) => {
                if (val && Alpine.store('app').currentSessionId) {
                    this.loadHistory();
                    this.updateQuickReplies();
                    this.currentStep = Math.min(Alpine.store('app').profileDimensions.length + 1, this.totalSteps);
                }
            });
            if (Alpine.store('app').initialized && Alpine.store('app').currentSessionId) {
                this.loadHistory();
                this.updateQuickReplies();
            }
        },

        async doQuickStart() {
            const sid = await Alpine.store('app').createSessionPrompt();
            if (sid) {
                this.$nextTick(() => {
                    this.loadHistory();
                    this.scrollToBottom();
                });
            }
        },

        async loadHistory() {
            const sid = Alpine.store('app').currentSessionId;
            if (!sid) return;
            try {
                const resp = await fetch(`/api/chat/history/${sid}`);
                const messages = await resp.json();
                this.chatMessages = messages.map(m => ({
                    ...m,
                    content_md: m.role === 'assistant' ? marked.parse(m.content) : null,
                }));
                this.$nextTick(() => this.scrollToBottom());
            } catch (e) {
                console.error('Failed to load chat history', e);
            }
        },

        sendQuickReply(text) {
            this.chatInput = text;
            this.sendMessage();
        },

        async sendMessage() {
            const msg = this.chatInput.trim();
            const sid = Alpine.store('app').currentSessionId;
            if (!msg || !sid || this.isStreaming) return;

            this.chatMessages.push({ role: 'user', content: msg, content_md: null });
            this.chatInput = '';
            this.quickReplies = [];
            this.isStreaming = true;
            const requestId = ++this.requestSeq;
            this.activeRequestId = requestId;
            this.streamingContent = '';
            this.streamingContentMd = '';
            this.$nextTick(() => {
                this.scrollToBottom();
                const ta = this.$refs.chatInput;
                if (ta) ta.style.height = 'auto';
            });

            try {
                const resp = await fetch('/api/chat/stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sid, message: msg }),
                });

                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let assistantContent = '';
                let answerFinalized = false;

                const finalizeAssistant = () => {
                    if (answerFinalized) return;
                    if (assistantContent) {
                        this.chatMessages.push({
                            role: 'assistant',
                            content: assistantContent,
                            content_md: marked.parse(assistantContent),
                        });
                    }
                    this.streamingContent = '';
                    this.streamingContentMd = '';
                    assistantContent = '';
                    answerFinalized = true;
                    if (this.activeRequestId === requestId) {
                        this.isStreaming = false;
                    }
                    this.updateQuickReplies();
                    this.$nextTick(() => this.scrollToBottom());
                };

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    buffer = window.PRLMAD.parseSse(buffer, async (eventName, data) => {
                        if (eventName === 'token') {
                            assistantContent += String(data || '');
                            this.streamingContent = assistantContent;
                            this.streamingContentMd = marked.parse(assistantContent);
                        } else if (eventName === 'answer_done') {
                            if (!assistantContent && data.content) {
                                assistantContent = data.content;
                            }
                            finalizeAssistant();
                            this.profileUpdating = true;
                        } else if (eventName === 'profile') {
                            this.profileVersion++;
                            await Alpine.store('app').loadProfile();
                            this.currentStep = Math.min(Alpine.store('app').profileDimensions.length + 1, this.totalSteps);
                            this.updateQuickReplies();
                        } else if (eventName === 'done') {
                            finalizeAssistant();
                            this.profileUpdating = false;
                        } else if (eventName === 'error') {
                            const errMsg = data.message || '未知错误';
                            this.chatMessages.push({
                                role: 'assistant',
                                content: '抱歉: ' + errMsg,
                                content_md: '<p class="text-red-500">' + errMsg + '</p>',
                            });
                            this.streamingContent = '';
                            this.streamingContentMd = '';
                            assistantContent = '';
                            answerFinalized = true;
                            if (this.activeRequestId === requestId) {
                                this.isStreaming = false;
                            }
                            this.profileUpdating = false;
                        }
                    });
                    this.$nextTick(() => this.scrollToBottom());
                }

                if (assistantContent && !answerFinalized) {
                    this.chatMessages.push({
                        role: 'assistant',
                        content: assistantContent,
                        content_md: marked.parse(assistantContent),
                    });
                }

                await Alpine.store('app').loadProfile();
                this.updateQuickReplies();
                this.profileVersion++;
                this.currentStep = Math.min(Alpine.store('app').profileDimensions.length + 1, this.totalSteps);
            } catch (e) {
                this.chatMessages.push({
                    role: 'assistant',
                    content: '网络错误: ' + e.message,
                    content_md: '<p class="text-red-500">网络错误: ' + e.message + '</p>',
                });
            }
            this.streamingContent = '';
            this.streamingContentMd = '';
            if (this.activeRequestId === requestId) {
                this.isStreaming = false;
            }
            this.profileUpdating = false;
            this.$nextTick(() => this.scrollToBottom());
        },

        updateQuickReplies() {
            const raw = Alpine.store('app').rawProfile || {};
            const hasValue = (key) => raw[key] && String(raw[key]).trim().length > 0;
            const lastAssistant = [...this.chatMessages].reverse()
                .find(m => m.role === 'assistant')?.content || '';
            const includesAny = (text, words) => words.some(w => text.includes(w));

            let focus = '';
            if (includesAny(lastAssistant, ['专业', '年级', '课程'])) focus = 'identity';
            else if (includesAny(lastAssistant, ['目标', '提升', '考试', '项目', '面试', '能力'])) focus = 'goal';
            else if (includesAny(lastAssistant, ['基础', '学过', '学到哪里', '掌握', '当前水平'])) focus = 'knowledge';
            else if (includesAny(lastAssistant, ['困难', '薄弱', '不明白', '抽象', '章节', '知识点', '题目'])) focus = 'weak';
            else if (includesAny(lastAssistant, ['图解', '代码', '做题', '实验', '偏好', '喜欢', '资源'])) focus = 'preference';
            else if (includesAny(lastAssistant, ['时间', '每天', '每周', '投入'])) focus = 'time';

            if (!focus) {
                if (!hasValue('major') || !hasValue('grade')) focus = 'identity';
                else if (!hasValue('goal')) focus = 'goal';
                else if (!hasValue('knowledge_level')) focus = 'knowledge';
                else if (!hasValue('weak_points')) focus = 'weak';
                else if (!hasValue('preferences') && !hasValue('cognitive_style')) focus = 'preference';
                else if (!hasValue('available_time')) focus = 'time';
                else focus = 'ready';
            }

            const replies = {
                identity: [
                    '我是软件工程专业大二学生，正在学习操作系统',
                    '我是计算机相关专业，想补齐操作系统基础',
                    '我正在上操作系统课，教材主要讲进程、内存和文件系统',
                ],
                goal: [
                    '我想系统掌握操作系统原理，为课程考试和项目开发打基础',
                    '我希望能把进程、内存和文件系统讲清楚，也能做题',
                    '我更想提升面试和项目中解释系统机制的能力',
                ],
                knowledge: [
                    '我学过C语言、数据结构和一点计算机组成，操作系统刚入门',
                    '我知道进程和线程的概念，但同步、死锁和内存管理不太稳',
                    '我已经学到进程调度和同步，后面的虚拟内存还没掌握',
                ],
                weak: [
                    '信号量和死锁这部分我一直不太明白',
                    '页面置换算法和虚拟内存感觉比较抽象',
                    '我做题时经常分不清进程同步、互斥和调度的条件',
                ],
                preference: [
                    '我比较喜欢图解配合代码示例来学习',
                    '我喜欢通过做题和错题解析来巩固知识点',
                    '我希望有讲义、思维导图和小实验一起辅助学习',
                ],
                time: [
                    '我每天大概有1小时学习时间，周末可以多学一点',
                    '我每周能投入4到6小时，希望按7天计划推进',
                    '我平时碎片时间多，希望每次任务控制在30分钟左右',
                ],
                ready: [
                    '我觉得你已经比较了解我了，可以开始生成学习资源了',
                    '请围绕我的薄弱点生成讲义、思维导图、练习和学习路径',
                ],
            };
            this.quickReplies = (replies[focus] || replies.ready).slice(0, 4);
        },

        scrollToBottom() {
            const el = this.$refs.msgContainer;
            if (el) el.scrollTop = el.scrollHeight;
        },
    }));
});
