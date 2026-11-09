const SVG_NS = 'http://www.w3.org/2000/svg';
const PIXEL = 3;
const PALETTE = ['#6b2815', '#a23813', '#d14b13', '#ff7830', '#ffe2a5'];
const MOTION_KEY = 'soundmess.ambient-paused';

function pixelShape(x, y, solid) {
    const size = solid ? PIXEL : PIXEL - .6;
    return `M${x} ${y}h${size}v${size}h-${size}z`;
}

function addPath(target, data, fill) {
    if (!data.length) return;
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', data.join(''));
    path.setAttribute('fill', fill);
    target.append(path);
}

function samplePixels(branch, length, width, seed) {
    const shades = PALETTE.map(() => []);
    const cells = new Map();

    function addCell(column, row, solid) {
        const key = `${column},${row}`;
        const existing = cells.get(key);
        if (existing?.solid || (existing && !solid)) return;
        const value = (Math.imul(column + seed, 73856093) ^ Math.imul(row + 17, 19349663)) >>> 0;
        if (!solid && value % 10 < 4) return;

        const tone = value % 100;
        const color = tone < 12 ? 0 : tone < 40 ? 1 : tone < 72 ? 2 : tone < 94 ? 3 : 4;
        cells.set(key, { column, row, solid, color: solid ? color : Math.max(0, color - 1) });
    }

    let previous;
    for (let distance = 0; distance <= length; distance = Math.min(distance + 1.25, length)) {
        const { x, y } = branch.getPointAtLength(distance);
        const column = Math.round(x / PIXEL);
        const row = Math.round(y / PIXEL);
        if (previous && previous.column !== column && previous.row !== row) {
            addCell(column, previous.row, true);
        }
        addCell(column, row, true);
        previous = { column, row };
        if (distance === length) break;

        const next = branch.getPointAtLength(Math.min(length, distance + 1));
        const angle = Math.atan2(next.y - y, next.x - x);
        const radius = width * (1 - distance / length) / 2;
        for (const side of [-1, 1]) {
            for (let offset = 2; offset <= radius; offset += PIXEL) {
                const outerColumn = Math.round((x - Math.sin(angle) * offset * side) / PIXEL);
                const outerRow = Math.round((y + Math.cos(angle) * offset * side) / PIXEL);
                addCell(outerColumn, outerRow, offset < radius * .6);
            }
        }
    }

    for (const { column, row, solid, color } of cells.values()) {
        shades[color].push(pixelShape(column * PIXEL, row * PIXEL, solid));
    }
    return shades;
}

function addFallingPixels(group, branch, length, index, count) {
    for (let petal = 0; petal < count; petal++) {
        const point = branch.getPointAtLength(length * (.57 + .14 * petal));
        const seed = index * 7 + petal * 13;
        const pixel = document.createElementNS(SVG_NS, 'rect');
        pixel.classList.add('ambient-petal');
        pixel.setAttribute('x', Math.round(point.x / PIXEL) * PIXEL);
        pixel.setAttribute('y', Math.round(point.y / PIXEL) * PIXEL);
        pixel.setAttribute('width', seed % 4 === 0 ? 4 : 3);
        pixel.setAttribute('height', seed % 4 === 0 ? 4 : 3);
        pixel.setAttribute('fill', PALETTE[2 + seed % 3]);
        pixel.style.setProperty('--fall-time', `${7 + seed % 6}s`);
        pixel.style.setProperty('--fall-delay', `-${seed % 14 + 1}s`);
        pixel.style.setProperty('--fall-distance', `${108 + seed % 102}px`);
        pixel.style.setProperty('--fall-drift', `${seed % 2 === 0 ? 16 + seed % 18 : -12 - seed % 18}px`);
        group.append(pixel);
    }
}

export class AmbientTree {
    constructor() {
        this.reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
        try {
            this.paused = localStorage.getItem(MOTION_KEY) === 'true';
        } catch {
            this.paused = false;
        }
        this.draw();
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

    draw() {
        const svg = document.querySelector('.ambient-tree');
        const target = svg.querySelector('.ambient-pixels');
        const branches = new Map();

        svg.querySelectorAll('[data-branch]').forEach((branch, index) => {
            const length = branch.getTotalLength();
            const width = Number(branch.dataset.width);
            const origin = branch.getPointAtLength(0);
            const group = document.createElementNS(SVG_NS, 'g');
            group.classList.add('ambient-branch');
            if (branch.dataset.parent) {
                const angle = length > 260 ? .5 : 1.2 + index % 4 * .32;
                group.classList.add('ambient-branch-sway');
                group.style.transformOrigin = `${origin.x}px ${origin.y}px`;
                group.style.setProperty('--sway-angle', `${angle}deg`);
                group.style.setProperty('--sway-time', `${4.5 + index % 5 * .7}s`);
                group.style.setProperty('--sway-delay', `-${index % 6 * .55}s`);
            }
            (branches.get(branch.dataset.parent) ?? target).append(group);
            branches.set(branch.dataset.branch, group);

            samplePixels(branch, length, width, index + 11).forEach((pixels, color) => {
                addPath(group, pixels, PALETTE[color]);
            });
            if (branch.dataset.parent && length >= 85) {
                addFallingPixels(group, branch, length, index, width > 6 ? 2 : 1);
            }
        });
    }

    sync() {
        const active = !this.paused && !this.reducedMotion.matches;
        document.documentElement.classList.toggle('ambient-paused', !active || document.hidden);
        for (const button of document.querySelectorAll('[data-ambient-toggle]')) {
            button.hidden = this.reducedMotion.matches;
            button.setAttribute('aria-pressed', String(active));
        }
    }
}
