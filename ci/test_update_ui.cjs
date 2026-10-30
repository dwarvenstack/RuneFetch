const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('webui/js/app.js', 'utf8');
const check = source.slice(source.indexOf('async function checkForUpdate('), source.indexOf('function showUpdateModal('));
function harness(update, reject = false) {
  const status = {textContent: '', innerHTML: ''};
  const calls = [];
  const context = vm.createContext({$: id => id === 'update-status' ? status : null,
    ws: {send: async () => {if (reject) throw Error('Disconnected'); return {update};}},
    markUpdateBadge: value => calls.push(['badge', value]),
    showUpdateModal: info => calls.push(['modal', info.version]), toast: (...args) => calls.push(['toast', ...args]),
    _pendingUpdate: null});
  vm.runInContext(check, context);
  return {context, status, calls};
}
test('manual and repeated checks show update without the removed version span', async () => {
  const h = harness({available: true, current: '2.0.1', version: '2.0.2'});
  await h.context.checkForUpdate(true);
  await h.context.checkForUpdate(true);
  assert.match(h.status.innerHTML, /v2.0.2 available/);
  assert.equal(h.calls.filter(c => c[0] === 'modal').length, 2);
});
test('transport failure clears checking status', async () => {
  const h = harness({}, true); await h.context.checkForUpdate(true);
  assert.equal(h.status.textContent, 'Check failed');
});
test('network failure reports failure instead of hanging', async () => {
  const h = harness({error: 'network', current: '2.0.1'}); await h.context.checkForUpdate(true);
  assert.match(h.status.textContent, /could not reach GitHub/);
});
test('up to date result renders without a version span', async () => {
  const h = harness({available: false, current: '2.0.2'}); await h.context.checkForUpdate(true);
  assert.match(h.status.textContent, /up to date/);
});
test('skipped startup check preserves existing update indicator', async () => {
  const h = harness({error: 'skipped_recent_check'}); h.status.innerHTML = 'v2.0.2 available';
  await h.context.checkForUpdate(false);
  assert.equal(h.status.innerHTML, 'v2.0.2 available'); assert.equal(h.calls.length, 0);
});

test('running version renders after the native bridge is ready', async () => {
  const body = source.slice(source.indexOf('async function showRunningVersion('),source.indexOf('function setupUpdates('));
  const status = {textContent:'RuneFetch —'};
  const context = vm.createContext({$:()=>status,window:{pywebview:{api:{get_version:async()=> '2.0.3'}}}});
  vm.runInContext(body,context);
  await context.showRunningVersion();
  assert.equal(status.textContent,'RuneFetch 2.0.3');
  const init=source.slice(source.indexOf('(async () => {'),source.indexOf('// ── Navigation'));
  assert.ok(init.indexOf('await ws.init();') < init.indexOf('await showRunningVersion();'));
});
test('missing native version does not crash initialization', async () => {
  const body = source.slice(source.indexOf('async function showRunningVersion('),source.indexOf('function setupUpdates('));
  const context = vm.createContext({$:()=>({}),window:{}});
  vm.runInContext(body,context);await context.showRunningVersion();
});
