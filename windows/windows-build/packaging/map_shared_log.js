/* HamNavigator's live ADIF source. Reading never invokes logging-service uploads. */
'use strict';
const path = require('path');
const fs = require('fs');

function sharedPath(env = process.env) {
  const data = env.RADIOASSISTENT_DATA || path.join(env.APPDATA, 'Radioassistent');
  return path.join(data, 'log', 'hamnavigator.adi');
}

function configure(settings, env = process.env) {
  const managed = new Set(['hamnavigator.adi', 'hamnavigatorlog.adi', 'radioassistent.adi']);
  const old = settings.appLogs || [];
  const other = old.filter(entry => entry && !managed.has(path.win32.basename(String(entry.file || '')).toLowerCase()));
  const logs = [{enabled: true, file: sharedPath(env)}, ...other];
  const changed = JSON.stringify(old) !== JSON.stringify(logs);
  if (changed) settings.appLogs = logs;
  return changed;
}

function observe(settings, consume, env = process.env) {
  let previous = null;
  return function poll() {
    configure(settings, env);
    const file = sharedPath(env);
    try {
      // Atomic replacements are normal: observe the path, not an obsolete inode.
      const stat = fs.statSync(file);
      const revision = `${stat.size}:${stat.mtimeMs}:${stat.ctimeMs}`;
      if (revision === previous) return false;
      const content = fs.readFileSync(file, 'utf8');
      if (content.trim() && !/<(?:EOR|EOH)>\s*$/i.test(content.trim())) return false;
      consume(content);
      previous = revision;
      return true;
    } catch (error) {
      if (error.code === 'ENOENT' || error.code === 'EBUSY' || error.code === 'EPERM') return false;
      throw error;
    }
  };
}

module.exports = {sharedPath, configure, observe};
