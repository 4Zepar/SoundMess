export class PageDialog {
    constructor(dismiss) {
        this.dialog = document.getElementById('page-dialog');
        this.panel = this.dialog.querySelector('.page-dialog-panel');
        this.content = this.dialog.querySelector('.page-dialog-scroll');
        this.dialog.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                event.preventDefault();
                dismiss();
            }
        });
        this.dialog.addEventListener('cancel', event => {
            event.preventDefault();
            dismiss();
        });
        this.dialog.addEventListener('click', event => {
            if (event.target === this.dialog || event.target.closest('[data-dismiss-page-dialog]')) {
                event.preventDefault();
                dismiss();
            }
        });
    }

    show(section, url, messages, { direct = false, trigger = document.activeElement } = {}) {
        if (!this.dialog.open) {
            this.trigger = trigger;
            this.direct = direct;
        }
        this.url = url;
        this.fallback = this.direct ? section.dataset.pageDialog : null;
        const heading = section.querySelector('h1');
        heading.id ||= 'form-heading';
        heading.tabIndex = -1;
        this.namespaceIds(section);
        this.dialog.setAttribute('aria-labelledby', heading.id);
        this.dialog.classList.toggle('page-dialog-compact', section.classList.contains('auth-page'));
        this.content.replaceChildren(...(messages ? [messages, section] : [section]));
        this.content.scrollTop = 0;
        if (!this.dialog.open) this.dialog.showModal();
        const invalid = section.querySelector('[aria-invalid="true"]');
        (invalid || heading).focus({ preventScroll: !invalid });
    }

    namespaceIds(section) {
        const ids = new Map();
        for (const element of [section, ...section.querySelectorAll('[id]')]) {
            if (!element.id) continue;
            const id = 'page-dialog-' + element.id;
            ids.set(element.id, id);
            element.id = id;
        }
        for (const attribute of ['for', 'aria-labelledby', 'aria-describedby', 'aria-errormessage', 'data-preview-for']) {
            for (const element of [section, ...section.querySelectorAll('[' + attribute + ']')]) {
                const value = element.getAttribute(attribute);
                if (value) element.setAttribute(attribute, value.split(/\s+/).map(id => ids.get(id) || id).join(' '));
            }
        }
    }

    close() {
        if (this.dialog.open) this.closing ||= this.animateClose();
        return this.closing;
    }

    async animateClose() {
        this.panel.style.setProperty('--dialog-close-from', getComputedStyle(this.panel).transform);
        this.dialog.classList.add('is-closing');
        await Promise.allSettled(this.panel.getAnimations().map(animation => animation.finished));
        this.dialog.close();
        this.dialog.classList.remove('is-closing');
        this.panel.style.removeProperty('--dialog-close-from');
        this.content.replaceChildren();
        this.dialog.removeAttribute('aria-labelledby');
        const trigger = this.trigger;
        if (trigger?.isConnected && trigger.getClientRects().length) trigger.focus({ preventScroll: true });
        else document.getElementById('main-content').focus({ preventScroll: true });
        this.closing = null;
    }
}
