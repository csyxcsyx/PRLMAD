(() => {
    const PRLMAD = window.PRLMAD;
    let mermaidConfigured = false;
    let diagramSequence = 0;

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, char => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
        })[char]);
    }

    PRLMAD.renderMarkdown = function renderMarkdown(value) {
        const text = this.normalizeAiText(value);
        const rawHtml = window.marked
            ? window.marked.parse(text)
            : escapeHtml(text).replace(/\n/g, '<br>');
        if (!window.DOMPurify) return escapeHtml(text).replace(/\n/g, '<br>');
        return window.DOMPurify.sanitize(rawHtml, {
            USE_PROFILES: { html: true },
            ADD_ATTR: ['target', 'rel', 'loading', 'decoding'],
        });
    };

    PRLMAD.copyText = async function copyText(text, successMessage = '内容已复制') {
        try {
            await navigator.clipboard.writeText(String(text || ''));
            this.notify(successMessage, 'success');
            return true;
        } catch (error) {
            this.notify('复制失败，请手动选择内容', 'error');
            return false;
        }
    };

    PRLMAD.openMediaLightbox = function openMediaLightbox(image) {
        const dialog = document.getElementById('mediaLightbox');
        const target = dialog?.querySelector('img');
        const caption = dialog?.querySelector('[data-lightbox-caption]');
        if (!dialog || !target || !image?.src) return;
        target.src = image.src;
        target.alt = image.alt || '';
        if (caption) caption.textContent = image.alt || '学习资料图片';
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', '');
    };

    PRLMAD.ensureMermaid = async function ensureMermaid() {
        const api = await this.loadScript('/static/vendor/mermaid.min.js?v=11.6.0', 'mermaid');
        if (!api) throw new Error('Mermaid 未正确初始化');
        if (!mermaidConfigured) {
            api.initialize({
                startOnLoad: false,
                securityLevel: 'strict',
                theme: 'base',
                fontFamily: 'Inter Local, Microsoft YaHei UI, sans-serif',
                flowchart: { htmlLabels: false, useMaxWidth: true, curve: 'basis' },
                themeVariables: {
                    background: '#faf9f5',
                    primaryColor: '#efe9de',
                    primaryTextColor: '#141413',
                    primaryBorderColor: '#cc785c',
                    lineColor: '#8e8177',
                    secondaryColor: '#f5f0e8',
                    tertiaryColor: '#faf9f5',
                    noteBkgColor: '#f5f0e8',
                    noteBorderColor: '#cc785c',
                    fontSize: '14px',
                },
            });
            mermaidConfigured = true;
        }
        return api;
    };

    function addHeadingOutline(root) {
        const headings = Array.from(root.querySelectorAll('h2, h3'));
        if (headings.length < 4) return;
        const outline = document.createElement('nav');
        outline.className = 'ai-outline';
        outline.setAttribute('aria-label', '本页目录');
        const title = document.createElement('p');
        title.className = 'ai-outline-title';
        title.textContent = '本页目录';
        outline.appendChild(title);
        const list = document.createElement('div');
        list.className = 'ai-outline-list';
        headings.slice(0, 10).forEach((heading, index) => {
            heading.id = heading.id || `ai-heading-${root.dataset.renderVersion}-${index}`;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = heading.tagName === 'H3' ? 'is-subheading' : '';
            button.textContent = heading.textContent || `第 ${index + 1} 节`;
            button.addEventListener('click', () => heading.scrollIntoView({ behavior: 'smooth', block: 'start' }));
            list.appendChild(button);
        });
        outline.appendChild(list);
        const firstHeading = root.querySelector('h1');
        if (firstHeading) firstHeading.insertAdjacentElement('afterend', outline);
        else root.prepend(outline);
    }

    function enhanceCitations(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (!node.parentElement?.closest('code, pre, .citation-chip')) nodes.push(node);
        }
        const pattern = /\[(资料\d+(?:[-、,，]\d+)*)\]/g;
        nodes.forEach(node => {
            const text = node.nodeValue || '';
            if (!pattern.test(text)) return;
            pattern.lastIndex = 0;
            const fragment = document.createDocumentFragment();
            let cursor = 0;
            let match;
            while ((match = pattern.exec(text))) {
                fragment.append(text.slice(cursor, match.index));
                const chip = document.createElement('span');
                chip.className = 'citation-chip';
                chip.textContent = match[1];
                chip.title = '教材检索来源';
                fragment.appendChild(chip);
                cursor = match.index + match[0].length;
            }
            fragment.append(text.slice(cursor));
            node.replaceWith(fragment);
        });
    }

    function enhanceTables(root) {
        root.querySelectorAll('table').forEach(table => {
            if (table.parentElement?.classList.contains('table-scroll')) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'table-scroll';
            table.before(wrapper);
            wrapper.appendChild(table);
        });
    }

    function enhanceImages(root) {
        root.querySelectorAll('img').forEach(image => {
            image.loading = 'lazy';
            image.decoding = 'async';
            image.tabIndex = 0;
            image.setAttribute('role', 'button');
            image.setAttribute('aria-label', `放大查看：${image.alt || '学习资料图片'}`);
            const figure = document.createElement('figure');
            figure.className = 'ai-figure';
            image.before(figure);
            figure.appendChild(image);
            if (image.alt) {
                const caption = document.createElement('figcaption');
                caption.textContent = image.alt;
                figure.appendChild(caption);
            }
            const open = () => PRLMAD.openMediaLightbox(image);
            image.addEventListener('click', open);
            image.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    open();
                }
            });
            image.addEventListener('error', () => {
                figure.classList.add('has-error');
                image.removeAttribute('role');
                image.removeAttribute('tabindex');
            }, { once: true });
        });
    }

    function enhanceCodeBlocks(root) {
        root.querySelectorAll('pre').forEach(pre => {
            if (pre.closest('.code-shell, .mermaid-card')) return;
            const code = pre.querySelector('code');
            const languageClass = Array.from(code?.classList || []).find(name => name.startsWith('language-'));
            const language = languageClass ? languageClass.slice(9) : 'text';
            const shell = document.createElement('section');
            shell.className = 'code-shell';
            const toolbar = document.createElement('div');
            toolbar.className = 'code-toolbar';
            const label = document.createElement('span');
            label.textContent = language.toUpperCase();
            const copy = document.createElement('button');
            copy.type = 'button';
            copy.textContent = '复制代码';
            copy.addEventListener('click', () => PRLMAD.copyText(code?.textContent || '', '代码已复制'));
            toolbar.append(label, copy);
            pre.before(shell);
            shell.append(toolbar, pre);
        });
    }

    async function renderMermaidBlocks(root, version) {
        const blocks = Array.from(root.querySelectorAll('pre > code.language-mermaid'));
        if (!blocks.length) return;
        let api;
        try {
            api = await PRLMAD.ensureMermaid();
        } catch (error) {
            blocks.forEach(code => {
                code.parentElement?.insertAdjacentHTML('beforebegin', '<p class="diagram-error">导图组件加载失败，以下保留原始 Mermaid 内容。</p>');
            });
            return;
        }
        for (const code of blocks) {
            if (String(root.dataset.renderVersion) !== String(version)) return;
            const pre = code.parentElement;
            const source = code.textContent || '';
            try {
                const id = `prlmad-diagram-${Date.now()}-${diagramSequence++}`;
                const result = await api.render(id, source);
                if (String(root.dataset.renderVersion) !== String(version) || !pre?.isConnected) return;
                const card = document.createElement('section');
                card.className = 'mermaid-card';
                const toolbar = document.createElement('div');
                toolbar.className = 'diagram-toolbar';
                const label = document.createElement('span');
                label.textContent = '知识图解';
                const actions = document.createElement('div');
                const copy = document.createElement('button');
                copy.type = 'button'; copy.textContent = '复制源码';
                copy.addEventListener('click', () => PRLMAD.copyText(source, 'Mermaid 源码已复制'));
                const expand = document.createElement('button');
                expand.type = 'button'; expand.textContent = '放大';
                expand.addEventListener('click', () => {
                    const expanded = card.classList.toggle('is-expanded');
                    expand.textContent = expanded ? '收起' : '放大';
                    if (expanded) {
                        const closeOnEscape = event => {
                            if (event.key === 'Escape') {
                                card.classList.remove('is-expanded');
                                expand.textContent = '放大';
                                document.removeEventListener('keydown', closeOnEscape);
                            }
                        };
                        document.addEventListener('keydown', closeOnEscape);
                    }
                });
                actions.append(copy, expand);
                toolbar.append(label, actions);
                const canvas = document.createElement('div');
                canvas.className = 'mermaid-canvas';
                canvas.innerHTML = window.DOMPurify.sanitize(result.svg, {
                    USE_PROFILES: { svg: true, svgFilters: true },
                });
                card.append(toolbar, canvas);
                pre.replaceWith(card);
            } catch (error) {
                pre?.insertAdjacentHTML('beforebegin', '<p class="diagram-error">这段 Mermaid 暂时无法渲染，已保留源码供检查。</p>');
            }
        }
    }

    PRLMAD.enhanceAiContent = async function enhanceAiContent(root, version) {
        addHeadingOutline(root);
        enhanceTables(root);
        enhanceImages(root);
        enhanceCitations(root);
        await renderMermaidBlocks(root, version);
        if (String(root.dataset.renderVersion) === String(version)) enhanceCodeBlocks(root);
    };

    PRLMAD.renderInto = function renderInto(root, value) {
        const payload = value && typeof value === 'object'
            ? value
            : { content: value, final: true };
        const version = Number(root.dataset.renderVersion || 0) + 1;
        root.dataset.renderVersion = String(version);
        root.innerHTML = this.renderMarkdown(payload.content || '');
        if (payload.final !== false) {
            window.queueMicrotask(() => {
                if (String(root.dataset.renderVersion) === String(version)) this.enhanceAiContent(root, version);
            });
        }
    };

    document.addEventListener('alpine:init', () => {
        Alpine.directive('ai-markdown', (element, { expression }, { evaluateLater, effect, cleanup }) => {
            const evaluate = evaluateLater(expression);
            let frame = 0;
            effect(() => {
                evaluate(value => {
                    if (frame) window.cancelAnimationFrame(frame);
                    frame = window.requestAnimationFrame(() => {
                        frame = 0;
                        PRLMAD.renderInto(element, value);
                    });
                });
            });
            cleanup(() => {
                if (frame) window.cancelAnimationFrame(frame);
            });
        });
    });
})();
