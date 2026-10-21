import { confirmAction, toast } from './http.js';

export class Navigation {
    constructor({ mount, unmount }) {
        this.mount = mount;
        this.unmount = unmount;
        this.controller = null;
        history.scrollRestoration = 'manual';
        history.replaceState({ scroll: window.scrollY }, '');
        document.addEventListener('click', event => this.onClick(event));
        document.addEventListener('submit', event => this.onSubmit(event));
        window.addEventListener('popstate', event => {
            this.navigate(location.href, { history: false, scroll: event.state?.scroll || 0 });
        });
    }

    async navigate(url, options = {}) {
        this.controller?.abort();
        const controller = new AbortController();
        this.controller = controller;
        const active = document.activeElement;
        const focus = options.preserveFocus && active?.id ? {
            id: active.id, start: active.selectionStart, end: active.selectionEnd,
        } : null;
        const scroll = options.preserveScroll ? window.scrollY : options.scroll || 0;
        document.documentElement.classList.add('is-navigating');
        try {
            const response = await fetch(url, {
                method: options.method || 'GET', body: options.body,
                signal: controller.signal, credentials: 'same-origin',
                headers: { Accept: 'text/html', 'X-Requested-With': 'XMLHttpRequest' },
            });
            const html = await response.text();
            if (controller.signal.aborted) return;
            const next = new DOMParser().parseFromString(html, 'text/html');
            const shell = next.getElementById('app-shell');
            if (!shell) {
                location.assign(response.url || url);
                return;
            }
            this.unmount();
            document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
            shell.querySelectorAll('script:not([type="application/json"])').forEach(script => script.remove());
            if (options.history !== false) {
                history.replaceState({ ...history.state, scroll: window.scrollY }, '');
                const target = response.url || new URL(url, location.href).href;
                if (options.replace || target === location.href) history.replaceState({ scroll }, '', target);
                else history.pushState({ scroll }, '', target);
            }
            document.getElementById('app-shell').replaceWith(shell);
            document.title = next.title;
            const csrf = next.querySelector('meta[name="csrf-token"]');
            if (csrf) document.querySelector('meta[name="csrf-token"]').content = csrf.content;
            this.mount();
            window.scrollTo({ top: scroll, behavior: 'auto' });
            const field = focus && document.getElementById(focus.id);
            if (field) {
                field.focus({ preventScroll: true });
                if (field.setSelectionRange && focus.start !== null) {
                    try { field.setSelectionRange(focus.start, focus.end); } catch { /* Non-text inputs have no selection. */ }
                }
            } else {
                (document.querySelector('[aria-invalid="true"]') || document.getElementById('main-content')).focus({ preventScroll: true });
            }
        } catch (error) {
            if (error.name !== 'AbortError') toast('Не удалось загрузить страницу. Проверьте соединение и повторите.', true);
        } finally {
            if (this.controller === controller) document.documentElement.classList.remove('is-navigating');
        }
    }

    login() {
        const url = new URL(document.body.dataset.loginUrl, location.origin);
        url.searchParams.set('next', location.pathname + location.search + location.hash);
        this.navigate(url.href);
    }

    onClick(event) {
        const anchor = event.target.closest('a[href]');
        if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const url = new URL(anchor.href, location.href);
        if (url.origin !== location.origin || !['http:', 'https:'].includes(url.protocol) || anchor.target || anchor.hasAttribute('download') || url.pathname.startsWith('/admin/')) return;
        if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
        event.preventDefault();
        if (url.href !== location.href) this.navigate(url.href);
    }

    async onSubmit(event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || form.matches('[data-comment-form], [data-native]')) return;
        event.preventDefault();
        if (form.dataset.submitting === 'true') return;
        if (form.dataset.confirm && !await confirmAction(form.dataset.confirm)) return;
        const data = new FormData(form, event.submitter);
        const method = (form.getAttribute('method') || 'GET').toUpperCase();
        const target = new URL(form.getAttribute('action') || location.href, location.href);
        if (method === 'GET') {
            target.search = '';
            for (const [key, value] of data) if (typeof value === 'string' && value.trim()) target.searchParams.append(key, value);
        }
        form.dataset.submitting = 'true';
        const buttons = [...form.querySelectorAll('button[type="submit"], button:not([type])')];
        buttons.forEach(button => { button.disabled = true; });
        await this.navigate(target.href, {
            method, ...(method === 'POST' ? { body: data } : {}),
            preserveScroll: form.hasAttribute('data-filter-form'),
            preserveFocus: form.hasAttribute('data-filter-form'),
            replace: form.dataset.autoSubmit === 'true',
        });
        buttons.forEach(button => { button.disabled = false; });
        delete form.dataset.submitting;
    }
}
