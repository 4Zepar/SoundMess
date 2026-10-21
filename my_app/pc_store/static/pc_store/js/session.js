export class PlaybackSession {
    constructor(token) {
        this.token = token;
        this.listened = 0;
        this.counted = false;
        this.pending = false;
        this.retryAt = 0;
        this.anchor = null;
    }

    observe(time, { now, playing, seeking = false }) {
        if (this.anchor && playing && this.anchor.playing && !seeking) {
            const mediaDelta = time - this.anchor.time;
            const elapsed = Math.max(0, (now - this.anchor.now) / 1000);
            if (mediaDelta > 0 && mediaDelta <= elapsed + 0.75) {
                this.listened += Math.min(mediaDelta, elapsed);
            }
        }
        this.anchor = { time, now, playing: playing && !seeking };
    }

    ready(now) {
        return this.listened >= 30 && !this.counted && !this.pending && now >= this.retryAt;
    }
}
