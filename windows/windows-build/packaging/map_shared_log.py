"""Bind Map reads to the same ADIF file as Digital and MY SHACK."""
from pathlib import Path
import shutil

def install(bundle):
    renderer = Path(bundle) / 'release/HamNavigator-Map/resources/app/src/renderer'
    shutil.copy2(Path(__file__).with_suffix('.js'), renderer / 'lib/hamnavigator-shared-log.js')
    target = renderer / 'lib/adif.js'
    text = target.read_text(encoding='utf-8')
    if '// HN_SHARED_LOG_BINDING' in text:
        return
    header = '''// HN_SHARED_LOG_BINDING
const hnSharedLog = require('./lib/hamnavigator-shared-log.js');
let hnSharedPoll = null;
let hnSharedTimer = null;
function ensureHamNavigatorLog()
{
  hnSharedLog.configure(GT.settings);
}
'''
    text = header + text
    for signature in ('function loadAppLogs()', 'function updateAppLogsUI()',
                      'function scanForAppLogs()'):
        marker = signature + '\n{'
        assert marker in text, signature
        text = text.replace(marker, marker + '\n  ensureHamNavigatorLog();', 1)
    # The first managed row cannot be disabled or removed. External app logs remain editable.
    for signature in ('function removeAppLog(i)', 'function toggleAppLog(i, checkbox)'):
        marker = signature + '\n{'
        assert marker in text, signature
        text = text.replace(marker, marker + '\n  if (i == 0) { updateAppLogsUI(); return; }', 1)
    marker = '  loadAppLogs();\n'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '''  if (!hnSharedTimer)
  {
    hnSharedPoll = hnSharedLog.observe(GT.settings, buffer => {
      if (buffer) onAdiLoadComplete(buffer);
    });
    hnSharedTimer = setInterval(() => {
      try { hnSharedPoll(); } catch (error) { console.error('HamNavigator shared log:', error.code || 'read error'); }
    }, 2000);
  }
''', 1)
    checkbox = '" onclick=\'toggleAppLog(" + i + ", this)\' />'
    assert checkbox in text
    text = text.replace(checkbox, '(i == 0 ? " disabled" : "") + " onclick=\'toggleAppLog(" + i + ", this)\' />', 1)
    trash = '      html.push("<td onclick=\'removeAppLog(" + i + ")\'><img src=\'img/trash_24x48.png\' style=\'height:17px;margin:-1px;margin-bottom:-3px;padding:0px;cursor:pointer\'></td></tr>");'
    assert trash in text
    text = text.replace(trash, '      if (i == 0) html.push("<td></td></tr>");\n      else ' + trash.strip(), 1)
    target.write_text(text, encoding='utf-8')

if __name__ == '__main__':
    install(Path(__file__).resolve().parents[2] / 'bygg/klient')
