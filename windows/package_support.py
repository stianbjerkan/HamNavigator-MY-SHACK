"""First-run setup for the redistributable bundle; inactive in the developer app."""
import ui_language
from pathlib import Path
import json
import os
import shutil
import tempfile

def shared_app_logs(logs, data_dir):
    """Use one authoritative HamNavigator log; keep other applications' sources.

    Old export copies are removed only from the watch list, never from disk.
    Windows paths may also arrive from another machine through old settings.
    """
    from pathlib import PureWindowsPath
    managed = {'hamnavigator.adi', 'hamnavigatorlog.adi', 'radioassistent.adi'}
    other = [entry for entry in logs if isinstance(entry, dict)
             and PureWindowsPath(str(entry.get('file', ''))).name.lower() not in managed]
    return [{'enabled': True, 'file': str(Path(data_dir) / 'log/hamnavigator.adi')}] + other


def configure_shared_map_log(data_dir):
    """Seed new profiles too; change no unrelated preferences or credentials."""
    data_dir = Path(data_dir)
    settings_file = data_dir.parent / 'HamNavigator-Map/Ginternal/app-settings.json'
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    original = settings_file.read_bytes() if settings_file.exists() else None
    settings = json.loads(original.decode('utf-8-sig')) if original else {'defaultsApplied': True}
    updated = shared_app_logs(settings.get('appLogs', []), data_dir)
    if settings.get('appLogs') == updated:
        return False
    if original is not None:
        import datetime
        backup = settings_file.with_name('before-shared-log-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        with backup.open('xb') as stream:
            stream.write(original)
    settings['appLogs'] = updated
    if (settings_file.read_bytes() if settings_file.exists() else None) != original:
        raise RuntimeError(ui_language.t('Map-innstillingene er endret. Prøv igjen.'))
    from shared_log import atomic
    atomic(settings_file, json.dumps(settings, ensure_ascii=False, indent=2))
    return True

def bundled(root):
    return (Path(root)/'BUNDLE.json').is_file()

def program_defaults(root, data_dir):
    root, data_dir = Path(root), Path(data_dir)
    if not bundled(root):
        return {}
    if (root/'release/HamNavigator/HamNavigator.exe').is_file():
        return {}
    return {'mshv_path':str(data_dir/'programs/MSHV/MSHV_WIN64.exe'),
            'gridtracker_path':str(root/'programs/GridTracker/GridTracker2.exe')}

def prepare_bundle(root, data_dir):
    root, data_dir = Path(root), Path(data_dir)
    import settings_transfer
    try:
        settings_transfer.apply_pending(root,data_dir)
        (data_dir/'cloud/settings-error.txt').unlink(missing_ok=True)
    except Exception as error:
        (data_dir/'cloud').mkdir(parents=True,exist_ok=True)
        (data_dir/'cloud/settings-error.txt').write_text(str(error),encoding='utf-8')
    if not bundled(root):
        return
    if (root/'release/HamNavigator/HamNavigator.exe').is_file():
        # Clean archives can omit the empty directory required by the native logger.
        (root/'release/HamNavigator/log').mkdir(parents=True, exist_ok=True)
        configure_shared_map_log(data_dir)
        return  # HamNavigator keeps its own settings; Map seeds its own profile.
    target=data_dir/'programs/MSHV'
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='mshv-new-',dir=target.parent))
        try:
            shutil.copytree(root/'programs/MSHV',staging,dirs_exist_ok=True)
            try: os.rename(staging,target)
            except FileExistsError: pass
        finally:
            if staging.exists():
                if not staging.resolve().is_relative_to(target.parent.resolve()):
                    raise RuntimeError(ui_language.t('Uventet midlertidig mappe.'))
                shutil.rmtree(staging)
    profile=data_dir/'GridTracker/Ginternal'
    profile.mkdir(parents=True,exist_ok=True)
    path=profile/'app-settings.json'
    if not path.exists():
        # GridTracker deep-merges this clean seed with its factory defaults.
        settings={'defaultsApplied':True,'app':{'multicast':False,'wsjtUdpPort':2237,
            'wsjtForwardUdpEnable':True,'wsjtForwardUdpIp':'127.0.0.1','wsjtForwardUdpPort':2238}}
        try:
            with path.open('x',encoding='utf-8') as f: json.dump(settings,f,indent=2)
        except FileExistsError: pass

def launch_arguments(key, root, data_dir):
    if key=='gridtracker' and bundled(root):
        return ['--user-data-dir='+str(Path(data_dir)/'GridTracker'), '--disable-auto-updates']
    return []
