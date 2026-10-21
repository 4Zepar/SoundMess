import assert from 'node:assert/strict';
import test from 'node:test';

import { PlaybackSession } from '../../my_app/pc_store/static/pc_store/js/session.js';

function listen(session, start, seconds, clockStart = 0) {
    session.observe(start, { now: clockStart * 1000, playing: true });
    for (let offset = 1; offset <= seconds; offset++) {
        session.observe(start + offset, { now: (clockStart + offset) * 1000, playing: true });
    }
}

test('thirty seconds of real playback count without any DOM row', () => {
    const session = new PlaybackSession('one');
    listen(session, 0, 29);
    assert.equal(session.ready(29000), false);
    session.observe(30, { now: 30000, playing: true });
    assert.equal(session.ready(30000), true);
});

test('pauses and seeks do not count as listening', () => {
    const session = new PlaybackSession('two');
    listen(session, 0, 10);
    session.observe(10, { now: 11000, playing: false });
    session.observe(10, { now: 100000, playing: false });
    session.observe(100, { now: 101000, playing: true, seeking: true });
    session.observe(100, { now: 102000, playing: true });
    assert.equal(session.listened, 10);
    assert.equal(session.ready(102000), false);
});

test('duplicate and in-flight play requests are suppressed', () => {
    const session = new PlaybackSession('three');
    listen(session, 0, 30);
    session.pending = true;
    assert.equal(session.ready(30000), false);
    session.pending = false;
    session.counted = true;
    assert.equal(session.ready(31000), false);
});

test('network failures use a retry delay instead of flooding requests', () => {
    const session = new PlaybackSession('four');
    listen(session, 0, 30);
    session.retryAt = 35000;
    assert.equal(session.ready(34000), false);
    assert.equal(session.ready(35000), true);
});

test('media waiting does not inflate the listening time', () => {
    const session = new PlaybackSession('five');
    listen(session, 0, 5);
    session.observe(5, { now: 6000, playing: false });
    session.observe(5, { now: 100000, playing: true });
    session.observe(6, { now: 101000, playing: true });
    assert.equal(session.listened, 6);
});
