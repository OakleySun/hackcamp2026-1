import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';

const planner = readFileSync(new URL('./plan-notifications.js', import.meta.url), 'utf8');
const now = '2026-11-09T07:10:00Z'; // November 8, 11:10 p.m. in Vancouver
const recipient = { id: 'presenter', email: 'test@example.invalid', phoneTopic: 'test-topic',
  digest: true, reminder: true, topics: ['tech'] };
const event = { event_id: 'a', title: 'Intro to Git', local_date: '2026-11-09', local_start: '00:05',
  start_utc: '2026-11-09T08:05:00Z', venue: 'Demo Hall 204', state: 'published', topics: ['tech'] };

function plan(mode, events, sent = []) {
  const inputs = {
    'Quad settings': { now, mode, recipients: [recipient], quadUrl: 'https://quad.example' },
    'Fetch Quad events': { body: events },
  };
  const result = runInNewContext(`(function () { ${planner}\n})()`, {
    $: (name) => ({ first: () => ({ json: inputs[name] }) }),
    $input: { all: () => sent.map((deliveryKey) => ({ json: { deliveryKey } })) },
  });
  return Array.from(result, ({ json }) => json);
}

test('digest uses the Vancouver date, includes time TBD, and respects opted-in topics', () => {
  const today = { ...event, event_id: 'today', title: 'Coding Lab', local_date: '2026-11-08',
    local_start: null, start_utc: null };
  const results = plan('digest', [event, today, { ...today, event_id: 'sports', topics: ['sports'] }]);
  assert.deepEqual(results.map(({ channel }) => channel), ['email', 'phone']);
  assert.match(results[0].text, /Time TBD — Coding Lab/);
  assert.doesNotMatch(results[0].text, /Intro to Git|\/events\/sports/);
  assert.match(results[0].text, /https:\/\/quad\.example\/events\/today/);
});

test('reminders cross midnight, use the current venue, and retry only undelivered channels', () => {
  const results = plan('reminder', [event, event, { ...event, event_id: 'tbd', start_utc: null },
    { ...event, event_id: 'cancelled', state: 'cancelled' },
    { ...event, event_id: 'later', start_utc: '2026-11-09T08:11:00Z' }]);
  assert.equal(results.length, 2);
  assert.match(results[0].subject, /55 min/);
  assert.match(results[1].phoneText, /Demo Hall 204/);
  assert.equal(results[1].link, 'https://quad.example/events/a');
  assert.deepEqual(plan('reminder', [event], [results[0].deliveryKey]).map(({ channel }) => channel), ['phone']);
  assert.equal(plan('reminder', [event], results.map(({ deliveryKey }) => deliveryKey)).length, 0);
});

test('manual preview does not address messages and test mode only sends the sample', () => {
  const preview = plan('preview', [event]);
  assert.deepEqual(preview.map(({ kind }) => kind), ['digest', 'reminder']);
  assert.ok(preview.every(({ channel, address }) => channel === 'preview' && !address));
  const sample = plan('test', [event]);
  assert.equal(sample.length, 2);
  assert.ok(sample.every(({ subject, link }) => subject.startsWith('[Demo]') && link.endsWith('/explore')));
});
