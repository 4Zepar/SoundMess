import { confirmAction, toast } from './http.js';
import { PageDialog } from './page-dialog.js';

export class Navigation {
    constructor({ mount, unmount }) {
        this.mount = mount;
        this.unmount = unmount;
        this.controller = null;
        this.pageDialog = new PageDialog(() => this.dismissPageDialog());
        history.scrollRestoration = 'manual';
        history.replaceState({ scroll: document.getElementById('workspace').scrollTop }, '');
        document.addEventListener('click', event => this.onClick(event));
        document.addEventListener('submit', event => this.onSubmit(event));
        window.addEventListener('popstate', event => {
            this.navigate(location.href, { history: false, scroll: event.state?.scroll || 0 });
        });
        const formPage = document.querySelector('[data-page-dialog]');
        if (formPage) {
            this.pageDialog.show(formPage, location.href, document.querySelector('#main-content > .messages'), { direct: true });
        }
    }

    async navigate(url, options = {}) {
        this.controller?.abort();
        const controller = new AbortController();
        this.controller = controller;
        const active = document.activeElement;
        const focus = options.preserveFocus && active?.id ? {
            id: active.id, start: active.selectionStart, end: active.selectionEnd,
        } : null;
        const workspace = document.getElementById('workspace');
        const scroll = options.preserveScroll ? workspace.scrollTop : options.scroll || 0;
        const trigger = options.trigger || active;
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
            const formPage = shell.querySelector('[data-page-dialog]');
            if (formPage) {
                await this.pageDialog.closing;
                if (controller.signal.aborted) return;
                this.unmount();
                document.querySelectorAll('dialog[open]:not(#page-dialog)').forEach(dialog => dialog.close());
                const menu = document.querySelector('.mobile-more[open]');
                if (menu) menu.open = false;
                this.pageDialog.show(formPage, response.url || url, shell.querySelector('#main-content > .messages'), {
                    direct: options.history === false, trigger,
                });
                return;
            }
            const returnToBackground = this.pageDialog.dialog.open && response.url === location.href;
            await this.pageDialog.close();
            if (controller.signal.aborted) return;
            this.unmount();
            document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
            shell.querySelectorAll('script:not([type="application/json"])').forEach(script => script.remove());
            if (options.history !== false) {
                history.replaceState({ ...history.state, scroll: workspace.scrollTop }, '');
                const target = response.url || new URL(url, location.href).href;
                if (options.replace || target === location.href) history.replaceState({ scroll }, '', target);
                else history.pushState({ scroll }, '', target);
            }
            document.getElementById('app-shell').replaceWith(shell);
            document.title = next.title;
            const csrf = next.querySelector('meta[name="csrf-token"]');
            if (csrf) document.querySelector('meta[name="csrf-token"]').content = csrf.content;
            this.mount();
            document.getElementById('workspace').scrollTop = returnToBackground ? workspace.scrollTop : scroll;
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

    async dismissPageDialog() {
        if (this.pageDialog.closing || this.pageDialog.content.querySelector('[data-submitting="true"]')) return;
        this.controller?.abort();
        const fallback = this.pageDialog.fallback;
        await this.pageDialog.close();
        this.unmount();
        if (fallback) this.navigate(fallback, { replace: true });
    }

    onClick(event) {
        const anchor = event.target.closest('a[href]');
        if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const url = new URL(anchor.href, location.href);
        if (url.origin !== location.origin || !['http:', 'https:'].includes(url.protocol) || anchor.target || anchor.hasAttribute('download') || url.pathname.startsWith('/admin/')) return;
        if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
        event.preventDefault();
        if (url.href !== location.href || this.pageDialog.dialog.open) this.navigate(url.href, { trigger: anchor });
    }

    async onSubmit(event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || form.matches('[data-comment-form], [data-native]')) return;
        event.preventDefault();
        if (form.dataset.submitting === 'true') return;
        if (form.dataset.confirm && !await confirmAction(form.dataset.confirm)) return;
        const data = new FormData(form, event.submitter);
        const method = (form.getAttribute('method') || 'GET').toUpperCase();
        const formUrl = this.pageDialog.content.contains(form) ? this.pageDialog.url : location.href;
        const target = new URL(form.getAttribute('action') || formUrl, formUrl);
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
