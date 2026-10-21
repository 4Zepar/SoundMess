import assert from 'node:assert/strict';
import test from 'node:test';

import { Player } from '../../my_app/pc_store/static/pc_store/js/player.js';

function playerHarness(context) {
    const attributes = new Map();
    const classes = new Set();
    const storage = new Map();
    const repeatButton = {
        setAttribute: (name, value) => attributes.set(name, value),
        classList: { toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name) },
    };
    const previousDocument = globalThis.document;
    const previousStorage = globalThis.localStorage;
    globalThis.document = {
        getElementById: () => repeatButton,
        querySelectorAll: () => [],
    };
    globalThis.localStorage = {
        getItem: key => storage.get(key) ?? null,
        setItem: (key, value) => storage.set(key, value),
    };
    context.after(() => {
        if (previousDocument === undefined) delete globalThis.document;
        else globalThis.document = previousDocument;
        if (previousStorage === undefined) delete globalThis.localStorage;
        else globalThis.localStorage = previousStorage;
    });
    const player = Object.create(Player.prototype);
    player.current = { id: '1' };
    player.queue = [player.current, { id: '2' }];
    player.repeat = false;
    player.ended = false;
    player.audio = { currentTime: 40, volume: 0.8, play: context.mock.fn(() => Promise.resolve()) };
    player.sync = context.mock.fn();
    player.updateProgress = context.mock.fn();
    player.select = context.mock.fn();
    player.newSession();
    return { player, attributes, classes, storage };
}

test('repeat restarts the current track with a fresh listening session', context => {
    const { player } = playerHarness(context);
    player.repeat = true;
    const previousSession = player.session;
    previousSession.counted = true;
    previousSession.listened = 40;

    player.onEnded();

    assert.equal(player.current.id, '1');
    assert.equal(player.select.mock.callCount(), 0);
    assert.equal(player.audio.play.mock.callCount(), 1);
    assert.equal(player.audio.currentTime, 0);
    assert.equal(player.ended, false);
    assert.notEqual(player.session.token, previousSession.token);
    assert.equal(player.session.counted, false);
    assert.equal(player.session.listened, 0);
});

test('without repeat the next track starts, or playback ends at the queue boundary', context => {
    const { player } = playerHarness(context);
    player.onEnded();
    assert.deepEqual(player.select.mock.calls[0].arguments, [{ id: '2' }]);

    player.current = { id: '2' };
    player.onEnded();
    assert.equal(player.select.mock.callCount(), 1);
    assert.equal(player.audio.play.mock.callCount(), 0);
    assert.equal(player.ended, true);
});

test('manual next remains available while repeat is enabled', context => {
    const { player } = playerHarness(context);
    player.repeat = true;
    assert.equal(player.next(), true);
    assert.deepEqual(player.select.mock.calls[0].arguments, [{ id: '2' }]);
});

test('repeat preference survives restoration and updates accessible button state', context => {
    const { player, attributes, classes, storage } = playerHarness(context);
    player.toggleRepeat();
    assert.equal(attributes.get('aria-pressed'), 'true');
    assert.equal(classes.has('is-active'), true);
    assert.equal(JSON.parse(storage.get('soundmess.player.v2')).repeat, true);

    const restored = Object.create(Player.prototype);
    restored.audio = {};
    restored.restore();
    assert.equal(restored.repeat, true);

    player.toggleRepeat();
    assert.equal(attributes.get('aria-pressed'), 'false');
    assert.equal(classes.has('is-active'), false);
});
