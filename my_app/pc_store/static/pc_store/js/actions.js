import { api, ApiError, confirmAction, toast } from './http.js';
import { formatTime } from './player.js';

function node(tag, className, text) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined) result.textContent = text;
    return result;
}

export class Actions {
    constructor(player, navigation) {
        this.player = player;
        this.navigation = navigation;
        this.pending = new Set();
        this.objectURLs = new Set();
        this.filterTimer = null;
        document.addEventListener('click', event => this.onClick(event));
        document.addEventListener('submit', event => this.onSubmit(event));
        document.addEventListener('change', event => this.onChange(event));
        document.addEventListener('input', event => this.onInput(event));
        document.addEventListener('keydown', event => this.onKeyDown(event));
        document.addEventListener('play', event => {
            if (event.target.matches('[data-audio-preview]')) this.player.pause();
        }, true);
    }

    mount() {
        this.player.sync();
        const tab = location.hash.slice(1);
        if (document.querySelector('[data-tab="' + CSS.escape(tab) + '"]')) this.selectTab(tab, false);
        const filters = document.querySelector('details.filters');
        if (filters && matchMedia('(max-width: 700px)').matches && !location.search) filters.open = false;
    }

    unmount() {
        clearTimeout(this.filterTimer);
        for (const url of this.objectURLs) URL.revokeObjectURL(url);
        this.objectURLs.clear();
    }

    requireLogin() {
        if (document.getElementById('app-shell').dataset.authenticated === 'true') return false;
        this.navigation.login();
        return true;
    }

    handleError(error) {
        if (error instanceof ApiError && error.status === 401) this.navigation.login();
        else toast(error instanceof ApiError ? error.message : 'Не удалось выполнить действие. Попробуйте ещё раз.', true);
    }

    async onClick(event) {
        const target = event.target;
        try {
            const tab = target.closest('[data-tab]');
            if (tab) { this.selectTab(tab.dataset.tab); return; }
            const close = target.closest('[data-close-dialog]');
            if (close) { close.closest('dialog').close(); return; }
            const play = target.closest('[data-play-track]');
            if (play) { this.player.playFromRow(play.closest('.track-row')); return; }
            const like = target.closest('[data-like-id]');
            if (like && like.dataset.likeId) { await this.like(like); return; }
            const follow = target.closest('[data-follow-id]');
            if (follow) { await this.follow(follow); return; }
            const add = target.closest('[data-add-track]');
            if (add) { this.showPlaylists(add.dataset.addTrack); return; }
            const remove = target.closest('[data-remove-track]');
            if (remove) { await this.removeTrack(remove); return; }
            const reply = target.closest('[data-reply]');
            if (reply) {
                const form = reply.parentElement.querySelector('.reply-form');
                form.hidden = !form.hidden;
                if (!form.hidden) form.elements.text.focus();
                return;
            }
            const timestamp = target.closest('[data-seek-track]');
            if (timestamp) {
                const row = document.querySelector('.track-row[data-track-id="' + timestamp.dataset.seekTrack + '"]');
                if (row) this.player.seekTo(row, Number(timestamp.dataset.seconds));
                return;
            }
            const row = target.closest('.track-row');
            if (row && !target.closest('a, button, input, form, select')) this.player.playFromRow(row);
            if (!target.closest('.account-menu')) {
                document.querySelectorAll('.account-menu[open]').forEach(menu => { menu.open = false; });
            }
        } catch (error) {
            this.handleError(error);
        }
    }

    async like(button) {
        if (this.requireLogin()) return;
        const id = button.dataset.likeId;
        const key = 'like:' + id;
        if (this.pending.has(key)) return;
        this.pending.add(key);
        const controls = [...document.querySelectorAll('[data-like-id="' + id + '"]')];
        controls.forEach(control => { control.disabled = true; });
        try {
            const result = await api(button.dataset.likeUrl || '/like/toggle/' + id + '/', { liked: button.dataset.liked !== 'true' });
            for (const control of controls) {
                control.dataset.liked = String(result.liked);
                control.classList.toggle('is-liked', result.liked);
                control.setAttribute('aria-pressed', String(result.liked));
                control.setAttribute('aria-label', result.liked ? 'Убрать из любимого' : 'Добавить в любимое');
            }
            document.querySelectorAll('[data-like-count="' + id + '"]').forEach(count => { count.textContent = result.like_count; });
            document.querySelectorAll('.track-row[data-track-id="' + id + '"]').forEach(row => { row.dataset.liked = String(result.liked); });
            this.player.setLiked(id, result.liked);
            if (document.getElementById('app-shell').dataset.page === 'profile') {
                await this.navigation.navigate(location.href, { replace: true, preserveScroll: true });
            }
        } finally {
            this.pending.delete(key);
            controls.forEach(control => { control.disabled = false; });
        }
    }

    async follow(button) {
        if (this.requireLogin()) return;
        button.disabled = true;
        try {
            const result = await api(button.dataset.followUrl, { following: button.dataset.following !== 'true' });
            button.dataset.following = String(result.following);
            button.textContent = result.following ? 'Вы подписаны' : 'Подписаться';
            button.classList.toggle('btn-secondary', result.following);
            button.setAttribute('aria-pressed', String(result.following));
            document.querySelectorAll('[data-followers-count="' + button.dataset.followId + '"]').forEach(count => { count.textContent = result.followers_count; });
        } finally {
            button.disabled = false;
        }
    }

    showPlaylists(trackId) {
        if (this.requireLogin()) return;
        const dialog = document.getElementById('playlist-dialog');
        const list = document.getElementById('playlist-options-list');
        list.replaceChildren();
        const playlists = JSON.parse(document.getElementById('playlist-options').textContent);
        for (const playlist of playlists) {
            const button = node('button', 'playlist-option', playlist.title);
            button.type = 'button';
            button.addEventListener('click', async () => {
                button.disabled = true;
                try {
                    const result = await api('/album/add-track/', { track_id: trackId, album_id: playlist.id });
                    dialog.close();
                    toast(result.status === 'exists' ? 'Трек уже в этом плейлисте.' : 'Трек добавлен в плейлист.');
                } catch (error) {
                    this.handleError(error);
                } finally {
                    button.disabled = false;
                }
            });
            list.append(button);
        }
        if (!playlists.length) list.append(node('p', 'muted', 'Создай плейлист, чтобы добавить в него трек.'));
        dialog.showModal();
    }

    async removeTrack(button) {
        if (!await confirmAction('Убрать трек из этого плейлиста или релиза?')) return;
        button.disabled = true;
        try {
            await api('/album/remove-track/', { track_id: button.dataset.removeTrack, album_id: button.dataset.albumId });
            await this.navigation.navigate(location.href, { replace: true, preserveScroll: true });
        } finally {
            button.disabled = false;
        }
    }

    selectTab(name, updateURL = true) {
        const tabs = [...document.querySelectorAll('[data-tab]')];
        for (const tab of tabs) {
            const selected = tab.dataset.tab === name;
            tab.setAttribute('aria-selected', String(selected));
            tab.tabIndex = selected ? 0 : -1;
        }
        document.querySelectorAll('[data-tab-panel]').forEach(panel => { panel.hidden = panel.dataset.tabPanel !== name; });
        if (updateURL) history.replaceState({ ...history.state }, '', location.pathname + location.search + '#' + name);
    }

    onKeyDown(event) {
        const tab = event.target.closest('[data-tab]');
        if (!tab || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const tabs = [...tab.parentElement.querySelectorAll('[data-tab]')];
        let index = tabs.indexOf(tab);
        if (event.key === 'Home') index = 0;
        else if (event.key === 'End') index = tabs.length - 1;
        else index = (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        this.selectTab(tabs[index].dataset.tab);
        tabs[index].focus();
    }

    async onSubmit(event) {
        const form = event.target.closest('[data-comment-form]');
        if (!form) return;
        event.preventDefault();
        if (this.requireLogin() || form.dataset.submitting === 'true') return;
        form.dataset.submitting = 'true';
        const button = form.querySelector('button[type="submit"], button:not([type])');
        button.disabled = true;
        try {
            const comment = await api(form.dataset.url, {
                text: form.elements.text.value,
                timestamp_seconds: this.player.timeFor(form.dataset.trackId),
                ...(form.dataset.parentId ? { parent_id: Number(form.dataset.parentId) } : {}),
            });
            if (!form.isConnected) return;
            const parent = form.dataset.parentId && document.querySelector('[data-comment-id="' + form.dataset.parentId + '"]');
            const depth = parent ? Number(parent.dataset.depth) + 1 : 0;
            const item = this.commentNode(comment, form.dataset.trackId, depth);
            const root = document.querySelector('[data-comment-root]');
            if (parent) parent.querySelector('.comment-replies').append(item);
            else if (root) root.append(item);
            root?.querySelector('.empty-comments')?.remove();
            form.reset();
            if (parent) form.hidden = true;
        } catch (error) {
            this.handleError(error);
        } finally {
            delete form.dataset.submitting;
            button.disabled = false;
        }
    }

    commentNode(comment, trackId, depth) {
        const article = node('article', 'comment-node');
        article.dataset.commentId = comment.id;
        article.dataset.depth = depth;
        const avatar = node('div', 'avatar');
        if (comment.avatar) {
            const image = document.createElement('img');
            image.src = comment.avatar;
            image.alt = '';
            avatar.append(image);
        } else avatar.textContent = comment.author.slice(0, 1).toUpperCase();
        const body = node('div', 'comment-body');
        const meta = node('div', 'comment-meta');
        const timestamp = node('button', 'timestamp', formatTime(comment.timestamp_seconds));
        timestamp.type = 'button';
        timestamp.dataset.seekTrack = trackId;
        timestamp.dataset.seconds = comment.timestamp_seconds;
        meta.append(node('strong', '', comment.author), timestamp);
        body.append(meta, node('p', '', comment.text));
        if (depth < 3) {
            const reply = node('button', 'reply-button', 'Ответить');
            reply.type = 'button';
            reply.dataset.reply = comment.id;
            const form = node('form', 'reply-form');
            form.hidden = true;
            form.dataset.commentForm = '';
            form.dataset.trackId = trackId;
            form.dataset.parentId = comment.id;
            form.dataset.url = '/track/' + trackId + '/comments/';
            const input = document.createElement('input');
            input.name = 'text';
            input.maxLength = 1000;
            input.required = true;
            input.placeholder = 'Твой ответ';
            input.setAttribute('aria-label', 'Ответ на комментарий');
            const submit = node('button', 'btn btn-secondary', 'Ответить');
            submit.type = 'submit';
            form.append(input, submit);
            body.append(reply, form);
        }
        body.append(node('div', 'comment-replies'));
        article.append(avatar, body);
        return article;
    }

    onChange(event) {
        const input = event.target;
        if (input.matches('input[type="file"]')) this.previewFile(input);
        const form = input.closest('[data-filter-form]');
        if (form && !input.matches('input[type="search"]')) this.submitFilters(form, 0);
    }

    onInput(event) {
        const form = event.target.closest('[data-filter-form]');
        if (form && event.target.matches('input[type="search"]')) this.submitFilters(form, 400);
    }

    submitFilters(form, delay) {
        clearTimeout(this.filterTimer);
        this.filterTimer = setTimeout(() => {
            if (!form.isConnected) return;
            form.dataset.autoSubmit = 'true';
            form.requestSubmit();
        }, delay);
    }

    previewFile(input) {
        const file = input.files[0];
        if (!file) return;
        if (input.dataset.previewURL) {
            URL.revokeObjectURL(input.dataset.previewURL);
            this.objectURLs.delete(input.dataset.previewURL);
        }
        const url = URL.createObjectURL(file);
        this.objectURLs.add(url);
        input.dataset.previewURL = url;
        const preview = document.querySelector('[data-preview-for="' + CSS.escape(input.id) + '"]');
        if (preview && file.type.startsWith('image/')) {
            const image = document.createElement('img');
            image.src = url;
            image.alt = 'Предпросмотр изображения';
            preview.replaceChildren(image);
        }
        if (input.name === 'audio_file') {
            const audio = document.querySelector('[data-audio-preview]');
            if (!audio) return;
            audio.hidden = false;
            audio.src = url;
            audio.addEventListener('loadedmetadata', () => {
                const label = document.querySelector('[data-audio-duration]');
                if (label) label.textContent = 'Длительность: ' + formatTime(audio.duration);
            }, { once: true });
        }
    }
}
