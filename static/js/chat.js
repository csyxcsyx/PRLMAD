document.addEventListener('alpine:init', () => {
    Alpine.data('chatPage', () => ({
        chatInput: '',
        chatMessages: [],
        isStreaming: false,
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

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    buffer = window.PRLMAD.parseSse(buffer, async (eventName, data) => {
                        if (eventName === 'token') {
                            assistantContent += String(data || '');
                            this.streamingContent = assistantContent;
                            this.streamingContentMd = marked.parse(assistantContent);
                        } else if (eventName === 'profile') {
                            this.profileVersion++;
                            await Alpine.store('app').loadProfile();
                            this.currentStep = Math.min(Alpine.store('app').profileDimensions.length + 1, this.totalSteps);
                        } else if (eventName === 'done') {
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
                        }
                    });
                    this.$nextTick(() => this.scrollToBottom());
                }

                if (assistantContent) {
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
            this.isStreaming = false;
            this.$nextTick(() => this.scrollToBottom());
        },

        updateQuickReplies() {
            const profile = Alpine.store('app').profileDimensions || [];
            const has = (key) => profile.some(d => d.label && d.label.includes(key));

            const suggestions = [];
            if (!has('专业')) {
                suggestions.push('我是计算机科学与技术专业大二的学生');
                suggestions.push('我学软件工程，正在上操作系统课');
            }
            if (!has('知识')) {
                suggestions.push('我学过C语言和数据结构，但操作系统概念比较模糊');
                suggestions.push('我有Python编程基础，对操作系统了解不多');
            }
            if (!has('目标')) {
                suggestions.push('我想深入理解进程管理和内存管理');
            }
            if (!has('薄弱')) {
                suggestions.push('信号量和死锁这部分我一直不太明白');
                suggestions.push('页面置换算法感觉很抽象');
            }
            if (!has('习惯') && !has('偏好')) {
                suggestions.push('我比较喜欢看图解和代码示例来学习');
                suggestions.push('我喜欢通过做题来巩固知识点');
            }
            if (!has('时间')) {
                suggestions.push('我每天大概有1小时学习时间');
            }
            if (suggestions.length === 0 && profile.length >= 5) {
                suggestions.push('我觉得你已经比较了解我了，可以开始生成学习资源了');
            }
            this.quickReplies = suggestions.slice(0, 4);
        },

        scrollToBottom() {
            const el = this.$refs.msgContainer;
            if (el) el.scrollTop = el.scrollHeight;
        },
    }));
});
