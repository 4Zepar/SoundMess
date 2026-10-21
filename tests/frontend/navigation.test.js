import assert from 'node:assert/strict';
import test from 'node:test';

import { Navigation } from '../../my_app/pc_store/static/pc_store/js/navigation.js';

function formHarness(context, attributes, fields) {
    const previous = {
        HTMLFormElement: globalThis.HTMLFormElement,
        FormData: globalThis.FormData,
        location: globalThis.location,
    };
    class Form {
        dataset = {};
        // Named fields can mask the corresponding native form properties in the browser.
        action = { value: 'role' };
        method = 'post';
        matches() { return false; }
        getAttribute(name) { return attributes[name] ?? null; }
        hasAttribute() { return false; }
        querySelectorAll() { return []; }
    }
    globalThis.HTMLFormElement = Form;
    globalThis.FormData = class extends previous.FormData {
        constructor() {
            super();
            for (const [key, value] of Object.entries(fields)) this.append(key, value);
        }
    };
    globalThis.location = { href: 'http://localhost/moderation/users/7/' };
    context.after(() => {
        for (const [name, value] of Object.entries(previous)) {
            if (value === undefined) delete globalThis[name];
            else globalThis[name] = value;
        }
    });
    const navigation = Object.create(Navigation.prototype);
    navigation.navigate = context.mock.fn();
    const event = { target: new Form(), preventDefault: context.mock.fn() };
    return { navigation, event };
}

test('a hidden action field does not override the POST endpoint for saving account rights', async context => {
    const { navigation, event } = formHarness(context, {
        action: '/moderation/users/7/update/', method: 'post',
    }, { action: 'role', role: 'moderator', csrfmiddlewaretoken: 'csrf-token' });

    await navigation.onSubmit(event);

    const [url, options] = navigation.navigate.mock.calls[0].arguments;
    assert.equal(url, 'http://localhost/moderation/users/7/update/');
    assert.equal(options.method, 'POST');
    assert.equal(options.body.get('action'), 'role');
    assert.equal(options.body.get('role'), 'moderator');
    assert.equal(options.body.get('csrfmiddlewaretoken'), 'csrf-token');
});

test('GET filters keep their artist, release kind and search parameters', async context => {
    const { navigation, event } = formHarness(context, {
        action: '/moderation/comments/', method: 'get',
    }, { q: 'Song name', artist: '4', release_kind: 'album' });

    await navigation.onSubmit(event);

    const [url, options] = navigation.navigate.mock.calls[0].arguments;
    const target = new URL(url);
    assert.equal(target.pathname, '/moderation/comments/');
    assert.equal(target.searchParams.get('q'), 'Song name');
    assert.equal(target.searchParams.get('artist'), '4');
    assert.equal(target.searchParams.get('release_kind'), 'album');
    assert.equal(options.method, 'GET');
});
