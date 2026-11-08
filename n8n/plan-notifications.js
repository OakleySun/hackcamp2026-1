// This code runs in the n8n "Prepare notifications" node.
const settings = $('Quad settings').first().json;
const feed = $('Fetch Quad events').first().json.body;
if (!Array.isArray(feed)) throw new Error('Quad did not return an event list');

const now = new Date(settings.now);
const zone = 'America/Vancouver';
const vancouverDate = new Intl.DateTimeFormat('en-CA', {
  timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
});
const vancouverTime = new Intl.DateTimeFormat('en-CA', {
  timeZone: zone, hour: 'numeric', minute: '2-digit', hour12: true,
});
const dateKey = (date) => {
  const parts = Object.fromEntries(vancouverDate.formatToParts(date).map(({ type, value }) => [type, value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
};
const today = dateKey(now);
const preview = settings.mode === 'preview';
const test = settings.mode === 'test';
const sent = new Set($input.all().map(({ json }) => json.deliveryKey).filter(Boolean));
const seen = new Set();
const events = feed.filter((event) => event.state === 'published' && event.event_id && event.title);
const messages = [];

function start(event) {
  return event.start_utc ? Date.parse(event.start_utc) : NaN;
}

function eventLine(event) {
  const time = Number.isFinite(start(event)) ? vancouverTime.format(start(event)) : 'Time TBD';
  const venue = event.venue || 'Venue TBD';
  return `${time} — ${event.title} · ${venue}`;
}

function queue(recipient, kind, key, subject, text, phoneText, link) {
  if (preview) {
    messages.push({ json: { channel: 'preview', kind, subject, text, phoneText, link } });
    return;
  }
  const destinations = [
    ...(recipient.email ? [{ channel: 'email', address: recipient.email }] : []),
    ...(recipient.phoneTopic ? [{ channel: 'phone', address: recipient.phoneTopic }] : []),
  ];
  for (const { channel, address } of destinations) {
    const deliveryKey = JSON.stringify([kind, recipient.id, channel, key]);
    if (seen.has(deliveryKey) || sent.has(deliveryKey)) continue;
    seen.add(deliveryKey);
    messages.push({ json: { channel, address, kind, subject, text, phoneText, link, deliveryKey } });
  }
}

function digest(recipient, matches) {
  const todayEvents = matches.filter((event) => event.local_date === today)
    .sort((a, b) => (a.local_start || '99:99').localeCompare(b.local_start || '99:99'));
  if (todayEvents.length === 0 && !preview) return;
  const count = todayEvents.length;
  const label = `${count} ${count === 1 ? 'event' : 'events'}`;
  const link = `${settings.quadUrl}/explore`;
  const lines = todayEvents.map(eventLine);
  const emailLines = todayEvents.flatMap((event) => [eventLine(event), `${settings.quadUrl}/events/${encodeURIComponent(event.event_id)}`, '']);
  const phoneLines = lines.slice(0, 4);
  if (count > 4) phoneLines.push(`+${count - 4} more in Quad`);
  queue(recipient, 'digest', today, `Today on Quad · ${label}`,
    [`${label} today in Vancouver.`, '', ...emailLines, `Browse Quad: ${link}`].join('\n'),
    [label + ' today', ...phoneLines].join('\n').slice(0, 900), link);
}

function reminders(recipient, matches) {
  for (const event of matches) {
    const startsAt = start(event);
    const minutes = Math.ceil((startsAt - now.getTime()) / 60_000);
    if (!(minutes > 0 && minutes <= 60)) continue;
    const link = event.previewOnly ? `${settings.quadUrl}/explore` : `${settings.quadUrl}/events/${encodeURIComponent(event.event_id)}`;
    const title = `${event.previewOnly ? '[Demo] ' : ''}${event.title} starts in ${minutes} min`;
    const details = `${event.title} starts at ${vancouverTime.format(startsAt)} Vancouver time. ${event.venue || 'Venue TBD'}.`;
    const key = test ? ['demo', today] : [event.event_id, startsAt];
    queue(recipient, 'reminder', key, title, `${details}\n\nOpen in Quad: ${link}`, details, link);
  }
}

const sample = {
  event_id: 'demo-reminder', title: 'Intro to Git', venue: 'Demo Hall 204', previewOnly: true,
  start_utc: new Date(now.getTime() + 57 * 60_000).toISOString(),
};
if (preview) {
  digest({}, events);
  reminders({}, [sample]);
} else if (test) {
  reminders(settings.recipients[0], [sample]);
} else {
  for (const recipient of settings.recipients) {
    const matches = events.filter((event) => !recipient.topics?.length ||
      recipient.topics.some((topic) => event.topics?.includes(topic)));
    if (settings.mode === 'digest' && recipient.digest === true) digest(recipient, matches);
    if (settings.mode === 'reminder' && recipient.reminder === true) reminders(recipient, matches);
  }
}
return messages;
