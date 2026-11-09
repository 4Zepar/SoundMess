const SVG_NS = 'http://www.w3.org/2000/svg';
const PIXEL = 3;
const FRAME_MS = 100;
const TREE_WIDTH_SCALE = 1.2;
const TREE_HEIGHT_SCALE = 1.26;
const TREE_Y_OFFSET = 18;
const ROOT_X = 715;
const ROOT_Y = 245 * TREE_HEIGHT_SCALE + TREE_Y_OFFSET;
const PALETTE = ['#3b1d15', '#79200d', '#b53609', '#eb4c06', '#ff680e', '#fff0bb'];
const MOTION_KEY = 'soundmess.ambient-paused';

function sampleBranch(path) {
    const length = path.getTotalLength();
    const width = Number(path.dataset.width);
    const steps = Math.ceil(length / 1.4);
    const samples = [];

    for (let step = 0; step <= steps; step++) {
        const progress = step / steps;
        const distance = length * progress;
        const point = path.getPointAtLength(distance);
        const next = path.getPointAtLength(Math.min(length, distance + 1));
        const x = ROOT_X + (point.x - ROOT_X) * TREE_WIDTH_SCALE;
        const y = point.y * TREE_HEIGHT_SCALE + TREE_Y_OFFSET;
        const angle = Math.atan2(
            (next.y - point.y) * TREE_HEIGHT_SCALE,
            (next.x - point.x) * TREE_WIDTH_SCALE,
        );
        samples.push({
            x,
            y,
            normalX: -Math.sin(angle),
            normalY: Math.cos(angle),
            radius: width * (1 - progress) ** 1.65 / 2,
            flex: Math.min(Math.hypot(x - ROOT_X, y - ROOT_Y) / 430, 1),
            ripple: Math.sin(x * .009 + y * .012),
        });
    }

    return samples;
}

function bendPoint(sample, gust, ripple) {
    const drift = ripple * sample.ripple;
    return {
        x: sample.x + sample.flex * (4 * gust - 3 * drift),
        y: sample.y + sample.flex * (8 * gust + 3 * drift),
    };
}

function lightCell(cells, x, y, edge, leafColor) {
    const column = Math.floor(x / PIXEL);
    const row = Math.floor(y / PIXEL);
    const key = `${column},${row}`;
    const previous = cells.get(key);
    if (previous && (!previous.edge || edge || leafColor !== undefined)) return;

    if (leafColor !== undefined) {
        cells.set(key, { column, row, edge, color: leafColor });
        return;
    }

    const hash = Math.imul(column, 73856093) ^ Math.imul(row, 19349663);
    const tone = (Math.imul(hash ^ (hash >>> 16), 2246822519) >>> 0) % 100;
    if (edge && tone < 34) return;

    const color = tone < 20 ? 0 : tone < 46 ? 1 : tone < 69 ? 2 : tone < 90 ? 3 : tone < 98 ? 4 : 5;
    cells.set(key, { column, row, edge, color: edge ? Math.max(0, color - 1) : color });
}

export class AmbientTree {
    constructor() {
        this.reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
        try {
            this.paused = localStorage.getItem(MOTION_KEY) === 'true';
        } catch {
            this.paused = false;
        }

        const svg = document.querySelector('.ambient-tree');
        const pixels = svg.querySelector('.ambient-pixels');
        this.samples = [];
        this.leafOrigins = [];
        for (const branch of svg.querySelectorAll('[data-width]')) {
            const samples = sampleBranch(branch);
            this.samples.push(...samples);
            if (branch.hasAttribute('data-leaf-at')) {
                const index = Math.round(Number(branch.dataset.leafAt) * (samples.length - 1));
                this.leafOrigins.push(samples[index]);
            }
        }
        this.paths = PALETTE.map(color => {
            const path = document.createElementNS(SVG_NS, 'path');
            path.setAttribute('fill', color);
            pixels.append(path);
            return path;
        });
        this.time = 0;
        this.timer = null;
        this.leaves = [];
        this.leafSpawns = [
            { singlePixel: false, nextTime: .35, minInterval: .42 },
            { singlePixel: true, nextTime: .6, minInterval: .31 },
        ];
        this.drawFrame();
        this.reducedMotion.addEventListener('change', () => this.sync());
        document.addEventListener('visibilitychange', () => this.sync());
        document.addEventListener('click', event => {
            if (!event.target.closest('[data-ambient-toggle]')) return;
            this.paused = !this.paused;
            try {
                localStorage.setItem(MOTION_KEY, String(this.paused));
            } catch {
                // The control still works for this page when storage is unavailable.
            }
            this.sync();
        });
        this.sync();
    }

    drawFrame() {
        const cells = new Map();
        const gust = Math.sin(this.time * 1.05);
        const ripple = Math.sin(this.time * 1.7);

        // Bend the source geometry, then light cells on the same grid for every frame.
        for (const sample of this.samples) {
            const { x, y } = bendPoint(sample, gust, ripple);
            lightCell(cells, x, y, false);

            for (let offset = 1.8; offset < sample.radius; offset += PIXEL) {
                const dx = sample.normalX * offset;
                const dy = sample.normalY * offset;
                const edge = offset > sample.radius * .6;
                lightCell(cells, x + dx, y + dy, edge);
                lightCell(cells, x - dx, y - dy, edge);
            }
        }

        this.drawLeaves(cells, gust, ripple);
        const shades = PALETTE.map(() => []);
        for (const { column, row, color } of cells.values()) {
            shades[color].push(`M${column * PIXEL} ${row * PIXEL}h${PIXEL}v${PIXEL}h-${PIXEL}z`);
        }
        this.paths.forEach((path, index) => path.setAttribute('d', shades[index].join('')));
    }

    drawLeaves(cells, gust, ripple) {
        for (const spawn of this.leafSpawns) {
            if (!this.leafOrigins.length || this.time < spawn.nextTime) continue;

            const origin = this.leafOrigins[Math.floor(Math.random() * this.leafOrigins.length)];
            this.leaves.push({
                ...bendPoint(origin, gust, ripple),
                born: this.time,
                singlePixel: spawn.singlePixel,
                duration: 3.2 + Math.random() * 1.4,
                speed: 18 + Math.random() * 8,
                drift: (Math.random() - .5) * 12,
                flutter: 4 + Math.random() * 5,
                color: Math.random() < .25 ? 5 : 4,
            });
            spawn.nextTime = this.time + spawn.minInterval + Math.random() * .34;
        }

        this.leaves = this.leaves.filter(leaf => this.time - leaf.born < leaf.duration);
        for (const leaf of this.leaves) {
            const age = this.time - leaf.born;
            const x = leaf.x + leaf.drift * age + leaf.flutter * Math.sin(age * 3);
            const y = leaf.y + leaf.speed * age + 1.5 * age ** 2;
            const color = age > leaf.duration - .7 ? leaf.color - 1 : leaf.color;
            lightCell(cells, x, y, false, color);
            if (!leaf.singlePixel) {
                const side = leaf.drift < 0 ? -PIXEL : PIXEL;
                lightCell(cells, x + side, y, false, Math.min(color, 4));
                lightCell(cells, x, y + PIXEL, false, color - 1);
            }
        }
    }

    sync() {
        const active = !this.paused && !this.reducedMotion.matches;
        if (active && !document.hidden) {
            if (this.timer === null) {
                this.timer = setInterval(() => {
                    this.time += FRAME_MS / 1000;
                    this.drawFrame();
                }, FRAME_MS);
            }
        } else {
            clearInterval(this.timer);
            this.timer = null;
        }

        for (const button of document.querySelectorAll('[data-ambient-toggle]')) {
            button.hidden = this.reducedMotion.matches;
            button.setAttribute('aria-pressed', String(active));
        }
    }
}
