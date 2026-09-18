'use strict';
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');
const bridge = require('./map_shared_log');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hn-shared-log-test-'));
const env = {RADIOASSISTENT_DATA: path.join(root, 'custom-data')};
const file = bridge.sharedPath(env);
const settings = {appLogs: [{enabled: true, file: 'C:\\Desktop\\radioassistent.adi'},
  {enabled: false, file: 'C:\\old\\HAMNAVIGATOR.ADI'}, {enabled: false, file: 'C:\\WSJT-X\\wsjtx_log.adi'}],
  credentials: {key: 'synthetic-only'}};
assert.equal(bridge.configure(settings, env), true);
assert.deepEqual(settings.appLogs, [{enabled: true, file}, {enabled: false, file: 'C:\\WSJT-X\\wsjtx_log.adi'}]);
assert.equal(bridge.configure(settings, env), false);
assert.equal(settings.credentials.key, 'synthetic-only');
let reads = [];
const poll = bridge.observe(settings, text => reads.push(text), env);
assert.equal(poll(), false);
fs.mkdirSync(path.dirname(file), {recursive: true});
fs.writeFileSync(file, '<PROGRAMID:12>HamNavigator<EOH>\n');
assert.equal(poll(), true); assert.equal(poll(), false);
fs.writeFileSync(file+'.tmp', '<EOH>\n<CALL:6>LA1ABC<EOR>\n');
fs.renameSync(file+'.tmp', file);
assert.equal(poll(), true); assert.match(reads.at(-1), /LA1ABC/);
fs.writeFileSync(file, '<CALL:20>partial');
assert.equal(poll(), false); assert.equal(reads.length, 2);
fs.writeFileSync(file, '<EOH>\n<CALL:6>LA2ABC<EOR>\n');
assert.equal(poll(), true);
settings.appLogs = [{enabled: true, file: 'C:\\Desktop\\radioassistent.adi'}];
poll(); assert.deepEqual(settings.appLogs, [{enabled: true, file}]);
// Use the actual packaged Map read function, not a replacement implementation.
if (process.argv[2]) {
  const source = fs.readFileSync(process.argv[2], 'utf8');
  const start = source.indexOf('function loadAppLogs()');
  const end = source.indexOf('function getParentFolderAndFilename', start);
  assert.ok(start >= 0 && end > start);
  let mapReads = [];
  const context = {GT: {settings}, fs, ensureHamNavigatorLog: () => bridge.configure(settings, env),
    onAdiLoadComplete: text => mapReads.push(text)};
  vm.runInNewContext(source.slice(start, end) + '\nloadAppLogs();', context);
  assert.deepEqual(mapReads, [fs.readFileSync(file, 'utf8')]);
  assert.match(mapReads[0], /LA2ABC/);
}
// Only the uniquely created, validated synthetic temporary directory is removed.
assert.equal(path.dirname(root), os.tmpdir());
assert.ok(path.basename(root).startsWith('hn-shared-log-test-'));
fs.rmSync(root, {recursive: true});
console.log('PASS: shared source, old-copy replacement, independent sources, atomic replacement, polling and actual Map file read');
