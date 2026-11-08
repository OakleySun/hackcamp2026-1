import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

const planner = readFileSync(new URL('./plan-notifications.js', import.meta.url), 'utf8');
const nodes = [];
const connections = {};

function id(name) {
  const hex = createHash('sha256').update(`Quad n8n: ${name}`).digest('hex');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
}

function node(name, type, typeVersion, position, parameters = {}, extra = {}) {
  nodes.push({ parameters, id: id(name), name, type: `n8n-nodes-base.${type}`, typeVersion, position, ...extra });
  return name;
}

function connect(from, to, output = 0) {
  const outputs = (connections[from] ??= { main: [] }).main;
  while (outputs.length <= output) outputs.push([]);
  outputs[output].push({ node: to, type: 'main', index: 0 });
}

function code(name, position, jsCode) {
  return node(name, 'code', 2, position, { jsCode });
}

function branch(name, position, leftValue, rightValue) {
  return node(name, 'if', 2.2, position, {
    conditions: {
      options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
      conditions: [{ id: id(`${name} condition`), leftValue, rightValue, operator: { type: 'string', operation: 'equals' } }],
      combinator: 'and',
    },
    options: {},
  });
}

function schedule(name, position, expression) {
  return node(name, 'scheduleTrigger', 1.2, position, { rule: { interval: [{ field: 'cronExpression', expression }] } });
}

const morning = schedule('8 AM digest', [0, -200], '0,10,20 8 * * *');
const hourly = schedule('Check starts every 10 minutes', [0, 0], '*/10 * * * *');
const manual = node('Preview both alerts', 'manualTrigger', 1, [0, 200]);
const digest = code('Select morning digest', [235, -200], "return [{ json: { mode: 'digest' } }];");
const reminder = code('Select one-hour reminders', [235, 0], "return [{ json: { mode: 'reminder' } }];");
const preview = code('Select preview or test', [235, 200], `// Set mode to 'test' for a single sample alert to the configured test recipient.
const mode = 'preview';
return [{ json: { mode } }];`);
const settings = code('Quad settings', [480, 0], `// Add only recipients who opted in. Keep recipient details in the workspace.
const recipients = [
  // { id: 'presenter', email: '', phoneTopic: '', digest: true, reminder: true, topics: [] },
];
const enabled = false;
const emailEnabled = false;
const phoneEnabled = false;
const testRecipientId = 'presenter';
const { mode } = $input.first().json;
const optedIn = recipients.map((recipient) => ({
  ...recipient,
  email: emailEnabled ? recipient.email : '',
  phoneTopic: phoneEnabled ? recipient.phoneTopic : '',
})).filter((recipient) => recipient.id && (recipient.email || recipient.phoneTopic));
const selected = mode === 'test' ? optedIn.filter((recipient) => recipient.id === testRecipientId).slice(0, 1) : optedIn;
if (mode === 'test' && selected.length === 0) throw new Error('Set the test recipient and enable at least one channel in Quad settings.');
if (mode !== 'preview' && mode !== 'test' && (!enabled || selected.length === 0)) return [];
return [{ json: {
  mode,
  now: new Date().toISOString(),
  quadUrl: 'https://4774d003-8629-4264-90d6-274ad60172ce.mtm.sh',
  phoneUrl: 'https://ntfy.sh',
  recipients: selected,
} }];`);

const tableName = 'Quad notification receipts';
const dataTableId = { __rl: true, mode: 'name', value: tableName };
const ensureTable = node('Open delivery ledger', 'dataTable', 1.1, [730, 0], {
  resource: 'table', operation: 'create', tableName,
  columns: { column: [{ name: 'deliveryKey', type: 'string' }] },
  options: { createIfNotExists: true },
});
const fetch = node('Fetch Quad events', 'httpRequest', 4.2, [960, 0], {
  url: "={{ $('Quad settings').first().json.quadUrl + '/api/events' }}",
  options: { timeout: 15000, response: { response: { fullResponse: true, responseFormat: 'json' } } },
});
const readTable = node('Read sent receipts', 'dataTable', 1.1, [1190, 0], {
  resource: 'row', operation: 'get', dataTableId, returnAll: true,
}, { alwaysOutputData: true, executeOnce: true });
const prepare = code('Prepare notifications', [1420, 0], planner);
const isPreview = branch('Preview only?', [1650, 0], '={{ $json.channel }}', 'preview');
const show = node('Inspect the digest and reminder', 'noOp', 1, [1910, -220]);
const isEmail = branch('Email or phone?', [1910, 80], '={{ $json.channel }}', 'email');

const email = node('Send email via Gmail', 'gmail', 2.2, [2170, -40], {
  resource: 'message', operation: 'send', sendTo: '={{ $json.address }}', subject: '={{ $json.subject }}',
  emailType: 'text', message: '={{ $json.text }}', options: { appendAttribution: false },
}, { disabled: true, onError: 'continueErrorOutput' });
const phone = node('Push to phone via ntfy', 'httpRequest', 4.2, [2170, 200], {
  method: 'POST', url: "={{ $('Quad settings').first().json.phoneUrl }}",
  sendBody: true, specifyBody: 'json',
  jsonBody: '={{ JSON.stringify({ topic: $json.address, title: $json.subject, message: $json.phoneText, click: $json.link, tags: [$json.kind === "reminder" ? "alarm_clock" : "calendar"] }) }}',
  options: { timeout: 12000, response: { response: { responseFormat: 'json' } } },
}, { onError: 'continueErrorOutput' });
const failed = node('Inspect delivery failures', 'noOp', 1, [2430, 380]);
const receipt = (condition) => `return $input.all().flatMap(({ json }, index) => {
  if (!(${condition})) return [];
  const { deliveryKey } = $('Prepare notifications').itemMatching(index).json;
  return [{ json: { deliveryKey }, pairedItem: { item: index } }];
});`;
const acceptedEmail = code('Check Gmail accepted the email', [2430, -40], receipt('json.id && json.threadId'));
const acceptedPush = code('Check ntfy accepted the push', [2430, 200], receipt('json.event === "message" && json.id'));
const record = node('Record successful delivery', 'dataTable', 1.1, [2690, 80], {
  resource: 'row', operation: 'insert', dataTableId,
  columns: {
    mappingMode: 'defineBelow',
    value: { deliveryKey: '={{ $json.deliveryKey }}' },
    schema: [{ id: 'deliveryKey', displayName: 'deliveryKey', required: false, defaultMatch: false, display: true, type: 'string', canBeUsedToMatch: true }],
  },
  options: {},
});

node('Quad notification guide', 'stickyNote', 1, [-20, -520], {
  content: '## Quad campus notifications\nRun **Preview both alerts** to see the morning digest and a sample reminder.\nThe schedule uses Vancouver time. The delivery ledger prevents repeat alerts on later runs.\nSet opted-in recipients in **Quad settings**. Connect your account and enable **Send email via Gmail** before turning on the email channel.',
  width: 520, height: 260, color: 4,
});

connect(morning, digest);
connect(hourly, reminder);
connect(manual, preview);
for (const source of [digest, reminder, preview]) connect(source, settings);
connect(settings, ensureTable);
connect(ensureTable, fetch);
connect(fetch, readTable);
connect(readTable, prepare);
connect(prepare, isPreview);
connect(isPreview, show);
connect(isPreview, isEmail, 1);
connect(isEmail, email);
connect(isEmail, phone, 1);
connect(email, acceptedEmail);
connect(phone, acceptedPush);
connect(email, failed, 1);
connect(phone, failed, 1);
connect(acceptedEmail, record);
connect(acceptedPush, record);

const workflow = {
  name: 'Quad · Morning digest and one-hour reminders',
  nodes, connections, active: false,
  settings: { timezone: 'America/Vancouver', executionOrder: 'v1', executionTimeout: 120 },
  pinData: {},
};
writeFileSync(new URL('./quad-campus-notifications.json', import.meta.url), JSON.stringify(workflow, null, 2) + '\n');
