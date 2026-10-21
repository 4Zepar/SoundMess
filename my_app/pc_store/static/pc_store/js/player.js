import { api, toast } from './http.js';
import { PlaybackSession } from './session.js';

const STORAGE_KEY = 'soundmess.player.v2';

export function formatTime(value) {
    const seconds = Number.isFinite(Number(value)) ? Math.max(0, Math.floor(Number(value))) : 0;
    return String(Math.floor(seconds / 60)) + ':' + String(seconds % 60).padStart(2, '0');
}

export function trackData(row) {
    return {
        id: row.dataset.trackId, title: row.dataset.title, artist: row.dataset.artist,
        url: row.dataset.url, cover: row.dataset.cover, detail: row.dataset.detail,
        duration: Number(row.dataset.duration) || 0,
        liked: row.dataset.liked === 'true', countable: row.dataset.countable === 'true',
    };
}

export class Player {
    constructor() {
        this.audio = document.getElementById('main-player');
        this.current = null;
        this.queue = [];
        this.session = null;
        this.lastSave = 0;
        this.ended = false;
        this.pendingSeek = null;
        this.progress = document.getElementById('progress-bar');
        this.bind();
        this.restore();
    }

    newSession() {
        this.session = new PlaybackSession(globalThis.crypto?.randomUUID?.() ?? Date.now() + '-' + Math.random().toString(16).slice(2));
    }

    bind() {
        document.getElementById('player-toggle').addEventListener('click', () => this.toggle());
        document.getElementById('player-next').addEventListener('click', () => this.next());
        document.getElementById('player-prev').addEventListener('click', () => this.previous());
        this.progress.addEventListener('input', () => {
            this.audio.currentTime = Number(this.progress.value);
            this.updateProgress();
        });
        const volume = document.getElementById('volume-slider');
        volume.addEventListener('input', () => {
            this.audio.volume = Number(volume.value);
            this.audio.muted = false;
        });
        document.getElementById('player-mute').addEventListener('click', () => {
            this.audio.muted = !this.audio.muted;
        });
        this.audio.addEventListener('timeupdate', () => this.updateProgress());
        this.audio.addEventListener('loadedmetadata', () => {
            if (this.pendingSeek !== null) {
                this.audio.currentTime = Math.min(this.pendingSeek, this.audio.duration || 0);
                this.pendingSeek = null;
            }
            this.updateProgress();
        });
        for (const event of ['play', 'pause', 'seeking', 'seeked', 'waiting', 'playing']) {
            this.audio.addEventListener(event, () => {
                this.session?.observe(this.audio.currentTime, {
                    now: performance.now(),
                    playing: !this.audio.paused && event !== 'waiting',
                    seeking: this.audio.seeking,
                });
                this.sync();
            });
        }
        this.audio.addEventListener('ended', () => {
            this.updateProgress();
            this.ended = true;
            if (!this.next()) this.sync();
        });
        this.audio.addEventListener('volumechange', () => {
            const muted = this.audio.muted || !this.audio.volume;
            const button = document.getElementById('player-mute');
            button.querySelector('use').setAttribute('href', muted ? '#icon-muted' : '#icon-volume');
            button.setAttribute('aria-label', muted ? 'Включить звук' : 'Выключить звук');
            volume.value = this.audio.volume;
            this.save();
        });
        this.audio.addEventListener('error', () => {
            if (this.current) {
                this.pause();
                toast('Аудиофайл недоступен. Попробуйте другой трек.', true);
            }
        });
        document.getElementById('player-cover').addEventListener('error', event => {
            event.target.hidden = true;
            document.getElementById('player-cover-placeholder').hidden = false;
        });
        window.addEventListener('pagehide', () => this.save());
    }

    restore() {
        let saved;
        try {
            saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
        } catch {
            saved = null;
        }
        this.audio.volume = Number.isFinite(saved?.volume) ? Math.max(0, Math.min(1, saved.volume)) : 0.8;
        if (!saved?.track?.id || !saved.track.url) return;
        const url = new URL(saved.track.url, location.origin);
        if (url.origin !== location.origin || !/^\/track\/\d+\/audio\/$/.test(url.pathname)) return;
        this.current = saved.track;
        this.pendingSeek = Number(saved.position) || 0;
        this.audio.src = this.current.url;
        this.audio.dataset.trackId = this.current.id;
        this.newSession();
        this.renderMetadata();
        this.sync();
    }

    save() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
                track: this.current, position: this.audio.currentTime || 0, volume: this.audio.volume,
            }));
        } catch {
            // Playback remains available when browser storage is disabled.
        }
    }

    playFromRow(row) {
        const metadata = trackData(row);
        if (!metadata.url) return;
        this.queue = [...document.querySelectorAll('.track-row[data-url]')]
            .map(trackData).filter(track => track.url)
            .filter((track, index, all) => all.findIndex(item => item.id === track.id) === index);
        if (this.current?.id === metadata.id) {
            this.toggle();
            return;
        }
        this.select(metadata);
    }

    select(metadata, position = 0) {
        this.current = { ...metadata };
        this.ended = false;
        this.newSession();
        this.pendingSeek = position;
        this.audio.src = metadata.url;
        this.audio.dataset.trackId = metadata.id;
        this.renderMetadata();
        this.play();
        this.save();
        if (metadata.countable && document.getElementById('app-shell').dataset.authenticated === 'true') {
            api('/history/add/' + metadata.id + '/', {}).catch(() => {});
        }
    }

    play() {
        if (!this.current) return;
        document.querySelectorAll('[data-audio-preview]').forEach(audio => audio.pause());
        if (this.ended) {
            this.audio.currentTime = 0;
            this.ended = false;
            this.newSession();
        }
        this.audio.play().catch(error => {
            if (error.name !== 'AbortError') toast('Нажмите воспроизведение, чтобы включить музыку.', true);
            this.sync();
        });
        this.sync();
    }

    pause() {
        this.audio.pause();
        this.save();
    }

    toggle() {
        if (this.audio.paused || this.audio.ended) this.play();
        else this.pause();
    }

    next() {
        const index = this.queue.findIndex(track => track.id === this.current?.id);
        if (index < 0 || index >= this.queue.length - 1) return false;
        this.select(this.queue[index + 1]);
        return true;
    }

    previous() {
        if (this.audio.currentTime > 3) {
            this.audio.currentTime = 0;
            return;
        }
        const index = this.queue.findIndex(track => track.id === this.current?.id);
        if (index > 0) this.select(this.queue[index - 1]);
    }

    seekTo(row, seconds) {
        const metadata = trackData(row);
        if (this.current?.id !== metadata.id) this.select(metadata, seconds);
        else {
            this.audio.currentTime = Math.min(seconds, this.audio.duration || seconds);
            this.play();
        }
    }

    timeFor(id) {
        return this.current?.id === String(id) ? Math.floor(this.audio.currentTime || 0) : 0;
    }

    renderMetadata() {
        const track = this.current;
        if (!track) return;
        const title = document.getElementById('player-track-title');
        title.textContent = track.title;
        title.href = track.detail;
        document.getElementById('player-track-artist').textContent = track.artist;
        const cover = document.getElementById('player-cover');
        cover.hidden = !track.cover;
        document.getElementById('player-cover-placeholder').hidden = Boolean(track.cover);
        if (track.cover) cover.src = track.cover;
        else cover.removeAttribute('src');
        document.getElementById('player-bar').classList.remove('is-empty');
        const like = document.getElementById('player-like');
        like.dataset.likeId = track.id;
        like.dataset.likeUrl = '/like/toggle/' + track.id + '/';
        like.disabled = !track.countable;
        this.setLiked(track.id, track.liked);
    }

    setLiked(id, liked) {
        if (this.current?.id !== String(id)) return;
        this.current.liked = liked;
        const button = document.getElementById('player-like');
        button.dataset.liked = String(liked);
        button.classList.toggle('is-liked', liked);
        button.setAttribute('aria-pressed', String(liked));
        button.setAttribute('aria-label', liked ? 'Убрать из любимого' : 'Добавить в любимое');
        this.save();
    }

    sync() {
        const playing = !this.audio.paused && !this.audio.ended;
        const button = document.getElementById('player-toggle');
        button.disabled = !this.current;
        button.setAttribute('aria-label', playing ? 'Пауза' : 'Воспроизвести');
        button.querySelector('use').setAttribute('href', playing ? '#icon-pause' : '#icon-play');
        const index = this.queue.findIndex(track => track.id === this.current?.id);
        document.getElementById('player-prev').disabled = !this.current;
        document.getElementById('player-next').disabled = index < 0 || index >= this.queue.length - 1;
        for (const row of document.querySelectorAll('.track-row[data-track-id]')) {
            const active = row.dataset.trackId === this.current?.id;
            row.classList.toggle('is-playing', active && playing);
            const icon = row.querySelector('.track-play use');
            if (icon) icon.setAttribute('href', active && playing ? '#icon-pause' : '#icon-play');
        }
        const visible = this.current && document.querySelector('.track-row[data-track-id="' + this.current.id + '"]');
        if (visible) this.setLiked(this.current.id, visible.dataset.liked === 'true');
        if (this.current && document.getElementById('app-shell').dataset.authenticated === 'false') this.setLiked(this.current.id, false);
    }

    updateProgress() {
        const duration = Number.isFinite(this.audio.duration) ? this.audio.duration : this.current?.duration || 0;
        this.progress.max = duration;
        this.progress.value = this.audio.currentTime || 0;
        this.progress.disabled = !duration;
        document.getElementById('current-time').textContent = formatTime(this.audio.currentTime);
        document.getElementById('total-time').textContent = formatTime(duration);
        const now = performance.now();
        this.session?.observe(this.audio.currentTime, { now, playing: !this.audio.paused, seeking: this.audio.seeking });
        if (this.current?.countable && this.session?.ready(now)) this.recordPlay();
        if (now - this.lastSave > 1000) {
            this.lastSave = now;
            this.save();
        }
    }

    async recordPlay() {
        const session = this.session;
        session.pending = true;
        try {
            await api('/track/' + this.current.id + '/play/', { playback_token: session.token });
            session.counted = true;
        } catch {
            session.retryAt = performance.now() + 5000;
        } finally {
            session.pending = false;
        }
    }
}
