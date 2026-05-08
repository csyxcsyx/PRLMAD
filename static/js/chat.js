document.addEventListener('alpine:init', () => {
    Alpine.data('chatPage', () => ({
        activeIndex: 0,
        saving: false,
        savedAt: '',
        profileVersion: 1,
        showProfileDetail: false,
        profileDraft: {
            major: '',
            grade: '',
            available_time: '',
            learning_motivation: '',
        },
        selections: {
            goal: [],
            knowledge_level: '',
            weak_points: [],
            preferences: [],
            practical_ability: [],
            available_time: '',
            learning_motivation: '',
        },
        customInputs: {
            goal: '',
            knowledge_level: '',
            weak_points: '',
            preferences: '',
            practical_ability: '',
            available_time: '',
            learning_motivation: '',
        },
        profileSteps: [
            {
                key: 'identity',
                nav: '学习背景',
                mark: '背',
                type: 'grouped',
                title: '你现在的学习背景是什么？',
                description: '先确认专业和年级，系统会据此调整解释深度。选项只是示例，也可以直接填写。',
                fields: [
                    {
                        key: 'major',
                        label: '专业方向',
                        options: ['软件工程', '计算机科学与技术', '人工智能', '网络工程', '物联网工程', '非计算机专业'],
                    },
                    {
                        key: 'grade',
                        label: '年级阶段',
                        options: ['大一', '大二', '大三', '大四', '研究生', '自学补基础'],
                    },
                ],
            },
            {
                key: 'goal',
                nav: '学习目标',
                mark: '目',
                type: 'choice',
                target: 'goal',
                multi: true,
                title: '你学习这门课主要想达成什么？',
                description: '可以多选。这里会直接影响资源生成时的讲解角度和练习难度。',
                options: [
                    '系统理解操作系统原理',
                    '应对课程考试和作业',
                    '能做典型题并说清思路',
                    '为项目开发打基础',
                    '为面试准备系统知识',
                    '补齐计算机基础',
                ],
                customPlaceholder: '还有其他目标可以补充，例如：希望能看懂教材某一章、准备课程设计等。',
            },
            {
                key: 'knowledge',
                nav: '当前基础',
                mark: '基',
                type: 'choice',
                target: 'knowledge_level',
                multi: false,
                title: '你现在大概处在什么基础水平？',
                description: '不需要精确判断，选最接近的一项即可。',
                options: [
                    '刚入门，还需要从基本概念开始',
                    '学过 C 语言和数据结构，但操作系统刚开始',
                    '了解进程、线程等名词，但机制不稳',
                    '已经学过部分章节，想查漏补缺',
                    '能做一些题，但解释不够清楚',
                    '基础较好，想做综合应用',
                ],
                customPlaceholder: '也可以写：你学到第几章、听课/自学情况、已经掌握哪些内容。',
            },
            {
                key: 'weak',
                nav: '薄弱知识',
                mark: '弱',
                type: 'choice',
                target: 'weak_points',
                multi: true,
                title: '哪些内容目前最需要帮助？',
                description: '这些选项会作为资源生成、学习路径和智能辅导的优先关注点。',
                options: [
                    '进程与线程',
                    '进程调度',
                    '同步与互斥',
                    '信号量',
                    '死锁',
                    '内存管理',
                    '虚拟内存',
                    '文件系统',
                    'I/O 与设备管理',
                    '还不确定，需要系统梳理',
                ],
                customPlaceholder: '如果你知道具体问题，可以写在这里，例如：PV 操作、页面置换、银行家算法。',
            },
            {
                key: 'preferences',
                nav: '学习方式',
                mark: '法',
                type: 'choice',
                target: 'preferences',
                multi: true,
                title: '你更喜欢怎样学习？',
                description: '系统会根据这些偏好决定生成讲义、导图、题库和任务清单的比例。',
                options: [
                    '图解配合例子',
                    '先讲概念再做题',
                    '通过错题解析巩固',
                    '代码或实验演示',
                    '思维导图梳理结构',
                    '短任务清单推进',
                    '先给结论再解释原因',
                    '慢一点、少术语、多类比',
                ],
                customPlaceholder: '也可以补充你不喜欢的学习方式，例如：不想一上来就看复杂公式。',
            },
            {
                key: 'practice',
                nav: '实践状态',
                mark: '练',
                type: 'choice',
                target: 'practical_ability',
                multi: true,
                title: '你希望实践内容做到什么程度？',
                description: '这会影响实操案例、代码示例和智能辅导中的举例方式。',
                options: [
                    '暂时更想先理解概念',
                    '能跟着代码运行就好',
                    '希望有小实验帮助观察机制',
                    '希望结合 Linux 命令或系统调用',
                    '希望练习画流程图和状态变化',
                    '希望偏向题目推理而不是代码',
                ],
                customPlaceholder: '可以写你熟悉的语言或环境，例如：C、Python、Linux、Windows。',
            },
            {
                key: 'time',
                nav: '时间动机',
                mark: '时',
                type: 'grouped',
                title: '你通常能投入多少时间？为什么想学好？',
                description: '学习路径会根据时间做轻重安排，动机信息会影响反馈方式。',
                fields: [
                    {
                        key: 'available_time',
                        label: '可用学习时间',
                        options: ['每天 30 分钟以内', '每天 45-60 分钟', '每周 4-6 小时', '周末集中学习', '时间不固定，需要碎片化任务'],
                    },
                    {
                        key: 'learning_motivation',
                        label: '学习动机',
                        options: ['课程考试', '完成作业/实验', '课程设计或项目', '面试准备', '补齐基础', '个人兴趣'],
                    },
                ],
            },
        ],

        get showWelcome() {
            return !Alpine.store('app').currentSessionId;
        },

        get totalSteps() {
            return this.profileSteps.length;
        },

        get currentStep() {
            return this.activeIndex + 1;
        },

        get activeStep() {
            return this.profileSteps[this.activeIndex] || this.profileSteps[0];
        },

        get profileProgress() {
            const done = this.profileSteps.filter((step) => this.isStepComplete(step)).length;
            return Math.round((done / this.totalSteps) * 100);
        },

        init() {
            this.$watch('$store.app.initialized', (ready) => {
                if (ready) this.refreshForSession();
            });
            this.$watch('$store.app.currentSessionId', () => this.refreshForSession());
            this.$watch('$store.app.rawProfile', () => this.hydrateFromProfile());
            if (Alpine.store('app').initialized) {
                this.refreshForSession();
            }
        },

        async doQuickStart() {
            await Alpine.store('app').createSessionPrompt();
        },

        refreshForSession() {
            this.activeIndex = 0;
            this.savedAt = '';
            this.hydrateFromProfile();
        },

        hydrateFromProfile() {
            const raw = Alpine.store('app').rawProfile || {};
            this.profileDraft.major = raw.major || '';
            this.profileDraft.grade = raw.grade || '';

            for (const step of this.profileSteps) {
                if (step.type === 'grouped') {
                    for (const field of step.fields || []) {
                        if (raw[field.key]) {
                            this.profileDraft[field.key] = raw[field.key];
                        }
                    }
                    continue;
                }
                const target = step.target;
                const rawValue = String(raw[target] || '');
                const matched = (step.options || []).filter((option) => rawValue.includes(option));
                if (step.multi) {
                    this.selections[target] = matched;
                } else {
                    this.selections[target] = matched[0] || '';
                }
                this.customInputs[target] = matched.length ? '' : rawValue;
            }
        },

        selectFieldOption(key, value) {
            this.profileDraft[key] = value;
            this.savedAt = '';
        },

        isSelected(target, value) {
            const current = this.selections[target];
            if (Array.isArray(current)) return current.includes(value);
            return current === value;
        },

        toggleOption(target, value, multi) {
            this.savedAt = '';
            if (multi) {
                const set = new Set(this.selections[target] || []);
                if (set.has(value)) set.delete(value);
                else set.add(value);
                this.selections[target] = Array.from(set);
                return;
            }
            this.selections[target] = this.selections[target] === value ? '' : value;
        },

        buildChoiceValue(step) {
            const target = step.target;
            const custom = (this.customInputs[target] || '').trim();
            const selected = this.selections[target];
            const parts = Array.isArray(selected) ? selected.slice() : (selected ? [selected] : []);
            if (custom) parts.push(custom);
            return Array.from(new Set(parts)).join('；');
        },

        isStepComplete(step) {
            if (step.type === 'grouped') {
                return (step.fields || []).every((field) => String(this.profileDraft[field.key] || '').trim());
            }
            return Boolean(this.buildChoiceValue(step));
        },

        buildProfile() {
            const profile = { ...(Alpine.store('app').rawProfile || {}) };
            const fields = ['major', 'grade', 'available_time', 'learning_motivation'];
            for (const key of fields) {
                const value = String(this.profileDraft[key] || '').trim();
                if (value) profile[key] = value;
            }
            for (const step of this.profileSteps) {
                if (step.type === 'grouped') {
                    for (const field of step.fields || []) {
                        const value = String(this.profileDraft[field.key] || '').trim();
                        if (value) profile[field.key] = value;
                    }
                    continue;
                }
                const value = this.buildChoiceValue(step);
                if (value) profile[step.target] = value;
            }
            if (profile.preferences && !profile.cognitive_style) {
                profile.cognitive_style = profile.preferences;
            }
            return profile;
        },

        async saveProfile(options = {}) {
            const sid = Alpine.store('app').currentSessionId;
            if (!sid || this.saving) return false;
            this.saving = true;
            try {
                const resp = await fetch(`/api/profile/${sid}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ profile: this.buildProfile() }),
                });
                if (!resp.ok) throw new Error('服务端拒绝了画像保存请求');
                await Alpine.store('app').loadProfile();
                this.profileVersion += 1;
                if (!options.silent) {
                    this.savedAt = '已保存 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
                }
                window.dispatchEvent(new CustomEvent('prlmad:profile-updated', {
                    detail: { sessionId: sid },
                }));
                return true;
            } catch (e) {
                alert('保存画像失败: ' + e.message);
                return false;
            } finally {
                this.saving = false;
            }
        },

        async nextStep() {
            await this.saveProfile({ silent: true });
            if (this.activeIndex < this.totalSteps - 1) {
                this.activeIndex += 1;
                this.savedAt = '';
            } else {
                this.savedAt = '画像已完成，可生成资源';
            }
        },

        prevStep() {
            if (this.activeIndex > 0) {
                this.activeIndex -= 1;
                this.savedAt = '';
            }
        },
    }));
});
