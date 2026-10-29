// Run from the repository root: node --test robustness/annotation_app/deployment/cloudflare/worker.test.mjs
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import worker from './worker.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const appDir = path.resolve(here, '../..');
const paperDir = path.resolve(appDir, '../data/Annotator-Test/Zunick_JournExpSocPsych_2017_zlw');
const PAPER = 'Zunick_JournExpSocPsych_2017_zlw';
const packet = JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['extract.py', paperDir], {cwd: appDir, maxBuffer: 64 << 20}));

const PART2 = {claim_alignment: 'Yes', claim_alignment_explanation: 'x', method_validity: 'Yes', method_validity_explanation: 'x'};
const RESTRICTION = {restriction_compliance: 'Yes', restriction_compliance_explanation: 'x'};
const PART3 = {implementation_fidelity: '4', implementation_fidelity_explanation: 'x'};
const PART4 = {conclusion_validity: '5', conclusion_validity_explanation: 'x'};

function makeEnv(extra = {}) {
  const responses = new Map(), assignments = new Set(), visits = new Map();
  const key = (...parts) => parts.join('|');
  const DB = {prepare(sql) {return {bind(...args) {return {
    async first() {
      if (sql.startsWith('SELECT payload')) {const row = responses.get(args.join('|')); return row ? {payload: row} : null}
      if (sql.startsWith('SELECT 1 FROM assignments')) return assignments.has(key(...args)) ? {1: 1} : null;
      throw new Error(sql);
    },
    async all() {return {results: [...responses].filter(([k]) => k.startsWith(`${args[0]}|${args[1]}|`)).map(([k, payload]) => ({analysis_id: k.split('|')[2], payload, updated_at: 'now'}))}},
    async run() {
      if (sql.startsWith('INSERT INTO visits')) {if (extra.FAIL_VISITS) throw new Error('no table'); visits.set(key(...args), (visits.get(key(...args)) || 0) + 1); return}
      responses.set(args.slice(0, 3).join('|'), args[3]);
    },
  }}}}};
  const FILES = {async get(name) {
    if (name === `${PAPER}/packet.json`) return {json: async () => structuredClone(packet)};
    if (name.startsWith(`${PAPER}/files/`)) return {body: 'file', httpMetadata: {}};
    return null;
  }};
  return {env: {DB, FILES, ALLOWED_ORIGIN: 'https://example.github.io', SESSION_SECRET: 's', ANNOTATION_PASSWORD: 'pw',
    ALLOWED_ANNOTATORS: 'cr-aaaaaa,an-bbbbbb', ...extra}, assign: (name, paper) => assignments.add(key(name, paper)), visits, responses};
}

async function call(env, pathname, {body, token, paper = PAPER} = {}) {
  const url = `https://api.example${pathname}${pathname.includes('?') ? '&' : '?'}paper=${paper}`;
  const headers = {'content-type': 'application/json'};
  if (token) headers.authorization = `Bearer ${token}`;
  const response = await worker.fetch(new Request(url, {method: body ? 'POST' : 'GET', headers, body: body && JSON.stringify(body)}), env);
  const text = await response.text();
  let data; try {data = JSON.parse(text)} catch {data = text}
  return {status: response.status, data};
}

async function login(env, annotator, paper) {
  const {status, data} = await call(env, '/api/login', {body: {annotator, password: 'pw'}, paper});
  return {status, token: data.token, error: data.error};
}

const save = (env, token, analysis_id, payload) => call(env, '/api/responses', {body: {analysis_id, payload}, token}).then(r => r.status);
const analysis = async (env, token, id) => {const {data} = await call(env, '/api/packet', {token}); return [data, data.analyses.find(a => a.id === id)]};
const fileStatus = (env, token, relative, id) => call(env, `/files/${relative}?analysis=${encodeURIComponent(id)}`, {token}).then(r => r.status);

test('code reviewer: Task 2 restriction, then code, then results', async () => {
  const {env} = makeEnv();
  const {token} = await login(env, 'CR-AAAAAA');
  const id = '1_test_02:Task2', code = packet.analyses.find(a => a.id === id).files.code;
  let [p, a] = await analysis(env, token, id);
  assert.equal(p.code_reviewer, true);
  assert.equal(a.files.code, null);
  assert.equal(await fileStatus(env, token, code, id), 403);

  assert.equal(await save(env, token, id, {...PART2, part2_submitted: true}), 409);
  let done = {...PART2, ...RESTRICTION, part2_submitted: true};
  assert.equal(await save(env, token, id, done), 200);
  [, a] = await analysis(env, token, id);
  assert.equal(a.files.code, code);
  assert.deepEqual(a.execution, {});
  assert.equal(await fileStatus(env, token, code, id), 200);

  assert.equal(await save(env, token, id, {...done, restriction_compliance: 'No'}), 409);
  assert.equal(await save(env, token, id, {...done, ...PART4, part4_submitted: true}), 409);
  done = {...done, ...PART3, part3_submitted: true};
  assert.equal(await save(env, token, id, done), 200);
  [, a] = await analysis(env, token, id);
  assert.notDeepEqual(a.execution, {});
  assert.equal(await save(env, token, id, {...done, ...PART4, part4_submitted: true}), 200);
});

test('non-reviewer: skips Part 3 and never sees code', async () => {
  const {env} = makeEnv();
  const {token} = await login(env, 'an-bbbbbb');
  const id = '1_test_01:Task1', code = packet.analyses.find(a => a.id === id).files.code;
  let [p] = await analysis(env, token, id);
  assert.equal(p.code_reviewer, false);
  const done = {...PART2, part2_submitted: true};
  assert.equal(await save(env, token, id, done), 200);
  const [, a] = await analysis(env, token, id);
  assert.equal(a.files.code, null);
  assert.notDeepEqual(a.execution, {});
  assert.equal(await fileStatus(env, token, code, id), 403);
  assert.equal(await save(env, token, id, {...done, ...PART3, part3_submitted: true}), 409);
  assert.equal(await save(env, token, id, {...done, ...PART4, part4_submitted: true}), 200);
});

test('assignments: off by default, enforced when enabled', async () => {
  const open = makeEnv();
  assert.equal((await login(open.env, 'an-bbbbbb')).status, 200);

  const {env, assign} = makeEnv({ENFORCE_ASSIGNMENTS: 'true'});
  const denied = await login(env, 'an-bbbbbb');
  assert.equal(denied.status, 403);
  assert.match(denied.error, /not assigned/);

  assign('an-bbbbbb', PAPER.toLowerCase());  // roster.py writes lowercase rows
  const {status, token} = await login(env, 'AN-BBBBBB');
  assert.equal(status, 200);
  assert.equal((await call(env, '/api/session', {token})).data.authenticated, true);
  assert.equal((await call(env, '/api/packet', {token})).status, 200);

  // The same token must not open a paper the annotator is not assigned to.
  assert.equal((await call(env, '/api/session', {token, paper: 'Other_paper'})).data.authenticated, false);
  assert.equal((await call(env, '/api/packet', {token, paper: 'Other_paper'})).status, 401);
});

test('visit log: records paper loads, never touches answers or blocks the page', async () => {
  const {env, visits, responses} = makeEnv();
  const {token} = await login(env, 'cr-aaaaaa');
  assert.equal(visits.size, 0);  // logging in alone records nothing
  await call(env, '/api/packet', {token});
  await call(env, '/api/packet', {token});
  assert.deepEqual([...visits], [[`cr-aaaaaa|${PAPER}`, 2]]);
  assert.equal(responses.size, 0);

  const failing = makeEnv({FAIL_VISITS: true});
  const t = (await login(failing.env, 'cr-aaaaaa')).token;
  assert.equal((await call(failing.env, '/api/packet', {token: t})).status, 200);
});
