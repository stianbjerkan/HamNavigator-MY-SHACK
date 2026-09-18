"""Radioassistent desktop shell. Programs remain independent processes."""
from __future__ import annotations
import ui_language
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox, QComboBox,
    QMdiArea, QMdiSubWindow, QSpinBox, QInputDialog)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from native_windows import EmbeddedWindow, find_window, pointer_activates_window
from package_support import launch_arguments
from update_dialog import UpdateDialog
from program_shutdown import ProgramShutdown

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get('RADIOASSISTENT_PORT', '18763'))
URL = f'http://127.0.0.1:{PORT}'
SOCKET_NAME = 'Radioassistent-' + hashlib.sha256((str(ROOT)+str(PORT)+os.environ.get('USERNAME','')).encode()).hexdigest()[:20]
LABELS = {'gridtracker': ui_language.t('Eksternt kartprogram'), 'digital': 'HamNavigator', 'hammap': 'HamNavigator Map'}

def request(path, value=None):
    if value is None:
        req = urllib.request.Request(URL+'/api/'+path)
    else:
        with urllib.request.urlopen(URL, timeout=3) as response:
            token = re.search(r'name="radio-token" content="([^"]+)"', response.read().decode()).group(1)
        req = urllib.request.Request(URL+'/api/'+path, json.dumps(value).encode(),
            {'Content-Type':'application/json', 'X-Radio-Token':token})
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.load(response)

class AppPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, main_frame):
        local = url.scheme() == 'http' and url.host() == '127.0.0.1' and url.port() == PORT
        if main_frame and not local and url.toString() != 'about:blank':
            if url.scheme() in ('https', 'http'):
                QDesktopServices.openUrl(url)
            return False
        return True

    def createWindow(self, kind):
        page = AppPage(self.profile(), self)
        page.urlChanged.connect(lambda url: self.open_external(page, url))
        return page

    def open_external(self, page, url):
        if url.scheme() in ('https','http'):
            QDesktopServices.openUrl(url)
        page.deleteLater()

class Surface(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.window = None
        self.focus_timer = QTimer(self)
        self.focus_timer.setSingleShot(True)
        self.focus_timer.setInterval(30)
        self.focus_timer.timeout.connect(self.focus_foreign)
        self.focus_from_pointer = False
        self.setMinimumSize(640, 400)

    def focus_foreign(self):
        if self.window:
            self.window.focus(self.focus_from_pointer)

    def queue_foreign_focus(self, from_pointer=False):
        self.focus_from_pointer = from_pointer
        self.focus_timer.start()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.queue_foreign_focus()

    def nativeEvent(self, event_type, message):
        if pointer_activates_window(message):
            # Delay until Qt's mouse activation has finished choosing focus.
            self.queue_foreign_focus(True)
        return super().nativeEvent(event_type, message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.window:
            self.window.resize()

class ProgramPanel(QWidget):
    def __init__(self, key, shell):
        super().__init__()
        self.key, self.shell = key, shell
        self.process = None
        self.executable = None
        self.deadline = 0
        self.layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.start = QPushButton(ui_language.t('Åpne ')+shell.label(key)+ui_language.t(' her'))
        self.detach_button = QPushButton(ui_language.t('Løsne vindu'))
        self.detach_button.setEnabled(False)
        self.status = QLabel(ui_language.t('Programmet åpnes når du trykker på knappen.'))
        self.status.setWordWrap(True)
        bar.addWidget(self.start)
        bar.addWidget(self.detach_button)
        bar.addWidget(self.status, 1)
        self.layout.addLayout(bar)
        self.surface = Surface()
        self.layout.addWidget(self.surface, 1)
        self.start.clicked.connect(self.open)
        self.detach_button.clicked.connect(self.detach)
        self.timer = QTimer(self)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.tick)

    def open(self):
        if not self.shell.account_access():return
        if self.shell.shutdown_pending:
            return
        if self.deadline:
            return
        if self.surface.window and self.surface.window.alive():
            return
        try:
            self.executable = self.shell.program_path(self.key)
            if self.key in ('mshv', 'digital'):
                if not request('live')['udp']['running']:
                    request('udp', {'start':True})
            hwnd = find_window(self.executable)
            if hwnd:
                self.attach(hwnd)
                return
            # Start only after a user's button/explicit panel request; never send radio commands.
            env=os.environ.copy()
            env.update(HAMNAVIGATOR_LANGUAGE=ui_language.get(),RADIOASSISTENT_DATA=str(self.shell.data_dir))
            if self.key=='hammap':
                env.update(HAMNAVIGATOR_DELIVERY_PYTHON=str(ROOT/'runtime/python.exe'),HAMNAVIGATOR_DELIVERY_BRIDGE=str(ROOT/'log_delivery.py'),RADIOASSISTENT_DATA=str(self.shell.data_dir))
            self.process = subprocess.Popen([str(self.executable), *launch_arguments(self.key, ROOT, self.shell.data_dir)], cwd=str(self.executable.parent),env=env)
            self.deadline = time.monotonic()+45
            self.start.setEnabled(False)
            self.status.setText(ui_language.t('Starter ')+self.shell.label(self.key)+' …')
            self.timer.start()
        except Exception as exc:
            self.status.setText(str(exc))

    def attach(self, hwnd):
        self.surface.window = EmbeddedWindow(hwnd, int(self.surface.winId()))
        if self.key in ('digital', 'hammap'):
            self.shell.managed_windows[hwnd] = self.surface.window
        self.deadline = 0
        self.start.setEnabled(False)
        self.detach_button.setEnabled(not self.shell.panels_locked)
        self.status.setText(self.shell.label(self.key)+ui_language.t(' er innebygd.'))
        self.timer.start()

    def tick(self):
        if self.surface.window:
            if not self.surface.window.alive():
                self.surface.window = None
                self.start.setEnabled(True)
                self.detach_button.setEnabled(False)
                self.status.setText(ui_language.t('Programmet er avsluttet.'))
                self.timer.stop()
            return
        if not self.deadline:
            return
        try:
            hwnd = find_window(self.executable)
            if hwnd:
                self.attach(hwnd)
            elif time.monotonic() > self.deadline:
                raise TimeoutError(ui_language.t('Fant ikke hovedvinduet. Fullfør eventuell oppstart i programmet og prøv igjen.'))
        except Exception as exc:
            self.deadline = 0
            self.timer.stop()
            self.start.setEnabled(True)
            self.status.setText(str(exc))

    def detach(self):
        try:
            if self.surface.window:
                self.surface.window.detach()
                self.surface.window = None
            self.deadline = 0
            self.timer.stop()
            self.start.setEnabled(True)
            self.detach_button.setEnabled(False)
            self.status.setText(ui_language.t('Eget programvindu. «Åpne her» henter det tilbake.'))
            return True
        except Exception as exc:
            self.status.setText(str(exc))
            return False

class PanelWindow(QMdiSubWindow):
    """Movable, resizable panel that remains inside the main application."""
    def __init__(self, shell):
        super().__init__()
        self.shell, self.key, self.content = shell, '', None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        root = QWidget()
        self.body = QVBoxLayout(root)
        self.body.setContentsMargins(5, 5, 5, 5)
        self.source = QComboBox()
        self.source.setAccessibleName(ui_language.t('Innhold i panelet'))
        self.body.addWidget(self.source)
        self.placeholder = QLabel(ui_language.t('Velg innhold i nedtrekksmenyen ovenfor.\nDu kan også legge til et nytt program øverst.'))
        self.placeholder.setWordWrap(True)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.addWidget(self.placeholder, 1)
        self.setWidget(root)
        self.setMinimumSize(360, 260)
        self.refresh_choices()
        self.source.activated.connect(lambda index: shell.assign(self, self.source.itemData(index), True))

    def refresh_choices(self):
        self.source.blockSignals(True)
        self.source.clear()
        for key in ['', 'home', *LABELS, *self.shell.extra_programs]:
            self.source.addItem(self.shell.label(key), key)
        self.source.setCurrentIndex(max(0, self.source.findData(self.key)))
        self.source.blockSignals(False)
        self.setWindowTitle(self.shell.label(self.key))

    def closeEvent(self, event):
        if self.shell.panels_locked:
            event.ignore()
            return
        if self.shell.remove_panel(self):
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if self.shell.panels_locked:
            event.ignore()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.shell.panels_locked:
            event.ignore()
            return
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.shell.panels_locked:
            event.ignore()
            return
        super().mouseDoubleClickEvent(event)

    def set_locked(self, locked):
        self.source.setEnabled(not locked)
        for action in self.systemMenu().actions():
            action.setEnabled(not locked)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.shell.schedule_save()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.shell.schedule_save()


class Shell(QMainWindow):
    def __init__(self, layout_path=None, resume=True):
        super().__init__()
        data_dir = Path(os.environ.get('RADIOASSISTENT_DATA', str(Path(os.environ.get('APPDATA', str(ROOT))) / 'Radioassistent')))
        self.data_dir = data_dir
        self.layout_path = Path(layout_path) if layout_path else data_dir/'panels.json'
        self.restoring, self.closing = True, False
        self.panels_locked = False
        self.windows, self.panels, self.extra_programs = [], {}, {}
        self.managed_windows = {}
        self.authorized=False
        self.ever_authorized=False
        self.shutdown_pending, self.shutdown_complete = False, False
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.setInterval(200)
        self.shutdown_timer.timeout.connect(self.poll_shutdown)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(600)
        self.save_timer.timeout.connect(self.save_layout)
        self.setWindowTitle('HamNavigator MY SHACK')
        self.setWindowIcon(QIcon(str(ROOT/'radioassistent.ico')))
        self.resize(1600, 1000)
        self.setMinimumSize(1100, 700)
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(8,8,8,8)
        bar = QHBoxLayout()
        title = QLabel('HamNavigator / MY SHACK')
        title.setStyleSheet('font-size:16px; font-weight:bold; color:#99e3c7;')
        bar.addWidget(title, 1)
        self.update_dialog = None
        update_button = QPushButton(ui_language.t('↻ Oppdater'))
        update_button.setToolTip(ui_language.t('Se etter en nyere versjon på GitHub'))
        update_button.clicked.connect(self.show_updates)
        bar.addWidget(update_button)
        language_button=QPushButton('Språk / Language')
        language_button.clicked.connect(self.show_language)
        bar.addWidget(language_button)
        bar.addWidget(QLabel(ui_language.t('Paneler:')))
        self.count = QSpinBox()
        self.count.setRange(1,24)
        self.count.setAccessibleName(ui_language.t('Antall paneler'))
        self.count.setKeyboardTracking(False)
        self.count.valueChanged.connect(self.set_panel_count)
        bar.addWidget(self.count)
        more = QPushButton(ui_language.t('＋ Nytt panel'))
        more.clicked.connect(lambda: self.count.setValue(self.count.value()+1))
        bar.addWidget(more)
        self.arrangement = QComboBox()
        self.arrangement.addItems([ui_language.t('Rutenett'), ui_language.t('Side om side'), ui_language.t('Over hverandre'), ui_language.t('Fritt oppsett'), ui_language.t('3 × 2 – seks paneler')])
        self.arrangement.setAccessibleName(ui_language.t('Paneloppsett'))
        self.arrangement.activated.connect(self.choose_arrangement)
        bar.addWidget(self.arrangement)
        arrange = QPushButton(ui_language.t('Fordel paneler'))
        arrange.clicked.connect(self.arrange)
        bar.addWidget(arrange)
        add_program = QPushButton(ui_language.t('＋ Legg til program …'))
        add_program.clicked.connect(self.add_program)
        bar.addWidget(add_program)
        both = QPushButton(ui_language.t('Åpne HamNavigator + Map'))
        both.clicked.connect(lambda: self.activate('hamnavigator'))
        bar.addWidget(both)
        self.layout_controls = [self.count, more, self.arrangement, arrange, add_program, both]
        self.lock_button = QPushButton(ui_language.t('Lås paneler'))
        self.lock_button.setCheckable(True)
        self.lock_button.setToolTip(ui_language.t('Hindrer flytting, størrelsesendring, lukking og bytte av panelinnhold.'))
        self.lock_button.toggled.connect(self.set_panels_locked)
        bar.addWidget(self.lock_button)
        layout.addLayout(bar)
        self.area = QMdiArea()
        self.area.setViewMode(QMdiArea.ViewMode.SubWindowView)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.area, 1)
        self.setCentralWidget(outer)
        self.parking = QWidget(self)
        self.parking.hide()
        self.profile = QWebEngineProfile('HamNavigator MY SHACK', self)
        self.profile.setPersistentStoragePath(str(data_dir/'WebView'))
        self.profile.setCachePath(str(data_dir/'WebCache'))
        self.profile.downloadRequested.connect(self.download)
        self.web = QWebEngineView(self.parking)
        self.web.setPage(AppPage(self.profile, self.web))
        self.web.setUrl(QUrl(URL))
        self.login_web=QWebEngineView()
        self.login_web.setPage(AppPage(self.profile,self.login_web))
        self.login_web.setUrl(QUrl(URL+'/#cloud'))
        layout.addWidget(self.login_web,1)
        self.area.hide()
        self.account_timer=QTimer(self)
        self.account_timer.setInterval(2000)
        self.account_timer.timeout.connect(self.account_access)
        self.account_timer.start()
        self.setStyleSheet('QMainWindow,QWidget{background:#101923;color:#e5edf5;font-family:Segoe UI;font-size:13px;} QPushButton,QComboBox,QSpinBox{background:#203345;border:1px solid #355069;border-radius:5px;padding:8px;} QPushButton:disabled{color:#647789;} QMdiSubWindow{border:1px solid #52705e;}')
        saved = self.read_layout()
        self.extra_programs = saved.get('programs', {})
        self.arrangement.setCurrentIndex(saved.get('arrangement',0))
        for item in saved['panels']:
            pane = self.add_panel()
            self.assign(pane, item['source'], False)
        self.restoring = False
        QTimer.singleShot(300, lambda: self.restore_positions(saved, resume))

    def account_access(self):
        try:self.authorized=request('cloud/status').get('authorized') is True
        except Exception:self.authorized=False
        if self.authorized:
            self.login_web.hide();self.area.show()
            if not self.ever_authorized:
                self.ever_authorized=True
                self.restore_positions(self.read_layout(),False)
        elif not any(w.alive() for w in self.managed_windows.values()):
            self.area.hide();self.login_web.show()
        # Existing radio windows remain reachable for STOP TX if a session expires.
        # Login never starts a radio or re-enables transmission.
        for control in self.layout_controls:control.setEnabled(self.authorized and not self.panels_locked)
        self.lock_button.setEnabled(self.authorized)
        return self.authorized

    def show_language(self):
        # Also available with locked panels or when MY SHACK is not in the layout.
        value,accepted=QInputDialog.getItem(self,'Språk / Language','Språk / Language',
            ['Norsk','English','Svenska'],{'nb':0,'en':1,'sv':2}[ui_language.get()],False)
        if not accepted:return
        try:ui_language.select({'Norsk':'nb','English':'en','Svenska':'sv'}[value])
        except OSError:
            QMessageBox.warning(self,'Språk / Language',ui_language.t('Språkvalget kunne ikke lagres.'))
            return
        for name in ('web','login_web'):
            view=getattr(self,name,None)
            if view is not None:view.reload()
        QMessageBox.information(self,'Språk / Language',ui_language.t('MY SHACK bruker det valgte språket. Start HamNavigator på nytt for Windows-paneler, Digital og Map. Stopp sending før omstart.'))

    def show_updates(self):
        if self.update_dialog is None:
            self.update_dialog = UpdateDialog(ROOT, self)
        elif not self.update_dialog.isVisible() and not self.update_dialog.busy():
            self.update_dialog.check()
        self.update_dialog.show()
        self.update_dialog.raise_()
        self.update_dialog.activateWindow()

    def label(self, key):
        return {'':ui_language.t('Tomt panel'), 'home':'HamNavigator MY SHACK', **LABELS}.get(key, self.extra_programs.get(key,{}).get('name',ui_language.t('Program')))

    def read_layout(self):
        default = {'version':1, 'panels':[{'source':key} for key in ('home','hammap','digital')], 'programs':{}, 'arrangement':0}
        try:
            pending=self.layout_path.parent/'cloud-panels-pending.json'
            if pending.exists():
                if self.layout_path.exists():
                    import shutil
                    shutil.copy2(self.layout_path,self.layout_path.with_name('panels.before-cloud.json'))
                os.replace(pending,self.layout_path)
            value = json.loads(self.layout_path.read_text(encoding='utf-8'))
            if value.get('version') != 1 or not isinstance(value.get('panels'),list) or not 1 <= len(value['panels']) <= 24:
                return default
            programs = value.get('programs',{})
            if not isinstance(programs,dict):
                return default
            value['programs'] = {key:{'name':str(item['name'])[:80], 'path':str(item['path'])} for key,item in programs.items()
                if isinstance(key,str) and key.startswith('extra-') and isinstance(item,dict) and 'name' in item and 'path' in item}
            allowed = {'','home',*LABELS,*value['programs']}
            seen = set()
            for panel in value['panels']:
                if not isinstance(panel,dict):
                    return default
                key = panel.get('source','')
                if key == 'mshv':
                    key = 'digital'
                if not isinstance(key,str) or key not in allowed or key in seen:
                    panel['source'] = ''
                else:
                    panel['source'] = key
                    if key: seen.add(key)
                rect = panel.get('rect')
                if not isinstance(rect,list) or len(rect)!=4 or not all(type(n)==int for n in rect):
                    panel.pop('rect',None)
            if type(value.get('arrangement')) != int or value['arrangement'] not in range(5):
                value['arrangement']=0
            value['locked'] = value.get('locked') is True
            return value
        except (OSError,ValueError,TypeError,KeyError):
            return default

    def program_path(self, key):
        if key == 'hammap':
            path = ROOT/'release/HamNavigator-Map/HamNavigatorMap.exe'
            if not path.is_file():
                raise ValueError(ui_language.t('HamNavigator Map er ikke installert i denne utgaven.'))
            return path
        if key == 'digital':
            path = ROOT/'release/HamNavigator/HamNavigator.exe'
            if not path.is_file():
                raise ValueError(ui_language.t('HamNavigator er ikke installert i denne utgaven.'))
            return path
        if key in self.extra_programs:
            path = Path(self.extra_programs[key]['path'])
            pattern = r'.+\.exe'
        else:
            settings = request('state')['settings']
            value = settings.get('mshv_path' if key=='mshv' else 'gridtracker_path','')
            if not value and key=='gridtracker':
                value = str(Path(os.environ.get('ProgramFiles','C:/Program Files'))/'GridTracker2/GridTracker2/GridTracker2.exe')
            path=Path(value)
            pattern=r'MSHV(?:_WIN(?:32|64))?\.exe' if key=='mshv' else r'GridTracker2?\.exe'
        if not path.is_absolute() or not path.is_file() or not re.fullmatch(pattern,path.name,re.I):
            raise ValueError(ui_language.t('Programfilen finnes ikke. Velg riktig fil under Min stasjon eller Legg til program.'))
        return path

    def add_panel(self):
        if self.panels_locked:
            return None
        if len(self.windows)>=24:
            return None
        pane=PanelWindow(self)
        self.windows.append(pane)
        self.area.addSubWindow(pane)
        pane.show()
        self.sync_count()
        return pane

    def sync_count(self):
        self.count.blockSignals(True)
        self.count.setValue(len(self.windows))
        self.count.blockSignals(False)

    def set_panel_count(self, count):
        if self.panels_locked:
            self.sync_count()
            return
        if self.arrangement.currentIndex() == 4 and count != 6:
            self.arrangement.setCurrentIndex(0)
        while len(self.windows)<count:
            self.add_panel()
        while len(self.windows)>count:
            if not self.remove_panel(self.windows[-1], arrange=False):
                break
        self.sync_count()
        self.arrange()

    def release(self, pane):
        if isinstance(pane.content,ProgramPanel):
            if not pane.content.detach():
                return False
            self.panels.pop(pane.key,None)
        if pane.content:
            pane.body.removeWidget(pane.content)
            pane.content.hide()
            pane.content.setParent(self.parking)
            if pane.content is not self.web:
                pane.content.deleteLater()
        pane.content,pane.key=None,''
        pane.placeholder.show()
        pane.refresh_choices()
        return True

    def assign(self, pane, key, start=False):
        if self.panels_locked:
            return
        if key not in ('','home',*LABELS,*self.extra_programs):
            return
        if pane.key==key:
            if start and isinstance(pane.content,ProgramPanel): pane.content.open()
            return
        # Each real program and the web application appear in exactly one panel.
        other=next((p for p in self.windows if p is not pane and p.key==key and key),None)
        if other and not self.release(other):
            pane.refresh_choices()
            return
        if not self.release(pane):
            return
        pane.key=key
        if key:
            pane.content=self.web if key=='home' else ProgramPanel(key,self)
            pane.body.addWidget(pane.content,1)
            pane.placeholder.hide()
            pane.content.show()
            if isinstance(pane.content,ProgramPanel):
                self.panels[key]=pane.content
                if start: pane.content.open()
        pane.refresh_choices()
        self.schedule_save()

    def remove_panel(self, pane, arrange=True):
        if self.panels_locked:
            return False
        if len(self.windows)==1:
            self.release(pane)
            self.schedule_save()
            return False
        if not self.release(pane):
            return False
        self.windows.remove(pane)
        self.area.removeSubWindow(pane)
        pane.hide()
        pane.deleteLater()
        self.sync_count()
        if arrange: self.arrange()
        self.schedule_save()
        return True

    def arrange(self):
        if self.restoring or self.panels_locked or not self.windows:
            return
        mode=self.arrangement.currentIndex()
        if mode==3:
            self.schedule_save()
            return
        n=len(self.windows)
        width,height=self.area.viewport().width(),self.area.viewport().height()
        cols=3 if mode==4 else n if mode==1 else 1 if mode==2 else min(n,max(1,math.ceil(math.sqrt(n*width/max(height,1)/2))))
        rows=math.ceil(n/cols)
        minimum_w=max([370]+[p.minimumSizeHint().width() for p in self.windows])
        minimum_h=max([290]+[p.minimumSizeHint().height() for p in self.windows])
        cell_w,cell_h=max(minimum_w,width//cols),max(minimum_h,height//rows)
        for i,pane in enumerate(self.windows):
            pane.showNormal()
            pane.setGeometry((i%cols)*cell_w,(i//cols)*cell_h,cell_w,cell_h)
        self.schedule_save()

    def choose_arrangement(self, index):
        if self.panels_locked:
            return
        if index == 4:
            self.set_panel_count(6)
        else:
            self.arrange()

    def set_panels_locked(self, locked):
        self.panels_locked = bool(locked)
        self.lock_button.blockSignals(True)
        self.lock_button.setChecked(self.panels_locked)
        self.lock_button.setText(ui_language.t('Lås opp paneler') if locked else ui_language.t('Lås paneler'))
        self.lock_button.blockSignals(False)
        for control in self.layout_controls:
            control.setEnabled(not locked)
        for pane in self.windows:
            pane.set_locked(locked)
        for panel in self.panels.values():
            window = panel.surface.window
            panel.detach_button.setEnabled(not locked and bool(window and window.attached and window.alive()))
        self.schedule_save()

    def restore_positions(self, saved, resume):
        if all('rect' in item for item in saved['panels']):
            width,height=self.area.viewport().width(),self.area.viewport().height()
            for pane,item in zip(self.windows,saved['panels']):
                x,y,w,h=item['rect']
                pane.setGeometry(max(0,min(x,width-100)),max(0,min(y,height-80)),max(370,min(w,width)),max(290,min(h,height)))
        else:
            self.arrange()
        if resume and self.account_access():
            for key,panel in list(self.panels.items()):
                try:
                    panel.executable=self.program_path(key)
                    hwnd=find_window(panel.executable)
                    if hwnd: panel.attach(hwnd)
                except Exception as exc:
                    panel.status.setText(str(exc))
        self.set_panels_locked(saved.get('locked', False))
        self.schedule_save()

    def activate(self, key):
        if not self.account_access():return
        if self.shutdown_pending:
            return
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()
        if self.panels_locked:
            keys = ('hammap', 'digital') if key in ('hamnavigator', 'both') else (key,)
            for selected in keys:
                panel = self.panels.get(selected)
                if panel:
                    panel.open()
            return
        if key=='hamnavigator':
            self.activate('home')
            self.activate('hammap')
            self.activate('digital')
            self.arrange()
            return
        if key=='both':
            self.activate('hammap')
            self.activate('digital')
            self.arrange()
            return
        key=key if key in (*LABELS,*self.extra_programs) else 'home'
        pane=next((p for p in self.windows if p.key==key),None)
        if not pane:
            pane=next((p for p in self.windows if not p.key),None) or self.add_panel()
            if not pane:
                QMessageBox.information(self,ui_language.t('Paneler'),ui_language.t('Velg innhold i ett av de eksisterende panelene. Maksimum er 24.'))
                return
            self.assign(pane,key,False)
            self.arrange()
        pane.showNormal()
        self.area.setActiveSubWindow(pane)
        if isinstance(pane.content,ProgramPanel): pane.content.open()

    def add_program(self):
        filename,_=QFileDialog.getOpenFileName(self,ui_language.t('Velg program som kan vises i et panel'),'',ui_language.t('Windows-program (*.exe)'))
        if not filename:
            return
        path=Path(filename)
        if not path.is_file() or path.suffix.lower()!='.exe':
            return
        key='extra-'+hashlib.sha256(str(path.resolve()).lower().encode()).hexdigest()[:12]
        # Reuse known programs rather than offering duplicate instances.
        for known in LABELS:
            try:
                if self.program_path(known)==path:
                    self.activate(known)
                    return
            except Exception: pass
        self.extra_programs[key]={'name':path.stem,'path':str(path.resolve())}
        for pane in self.windows: pane.refresh_choices()
        self.activate(key)
        self.schedule_save()

    def schedule_save(self):
        if not self.restoring and not self.closing and not self.shutdown_pending:
            self.save_timer.start()

    def layout_value(self):
        return {'version':1,'arrangement':self.arrangement.currentIndex(),'locked':self.panels_locked,'programs':self.extra_programs,
            'panels':[{'source':p.key,'rect':list(p.geometry().getRect())} for p in self.windows]}

    def save_layout(self):
        if not self.ever_authorized:return
        try:
            self.layout_path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.layout_path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.layout_value(),ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temp,self.layout_path)
        except OSError as exc:
            self.statusBar().showMessage(ui_language.t('Paneloppsettet kunne ikke lagres: ')+str(exc),10000)

    def download(self,item):
        filename,_=QFileDialog.getSaveFileName(self,ui_language.t('Lagre fil'),str(Path.home()/'Downloads'/item.downloadFileName()))
        if filename:
            item.setDownloadDirectory(str(Path(filename).parent))
            item.setDownloadFileName(Path(filename).name)
            item.accept()
        else: item.cancel()

    def poll_shutdown(self):
        try:
            if not self.shutdown.poll():
                return
        except Exception as exc:
            self.shutdown_timer.stop()
            self.shutdown_pending = False
            self.centralWidget().setEnabled(True)
            self.statusBar().showMessage(str(exc))
            return
        self.shutdown_timer.stop()
        self.shutdown_pending = False
        self.shutdown_complete = True
        self.close()

    def closeEvent(self,event):
        if self.update_dialog and self.update_dialog.busy():
            self.update_dialog.reject()
            self.statusBar().showMessage(ui_language.t('Avbryter oppdateringen. Lukk vinduet igjen når den er ferdig.'), 10000)
            event.ignore()
            return
        self.save_timer.stop()
        self.save_layout()
        if not self.shutdown_complete:
            event.ignore()
            if self.shutdown_pending:
                return
            self.shutdown_pending = True
            self.centralWidget().setEnabled(False)
            self.statusBar().showMessage(ui_language.t('Avslutter HamNavigator og Map og venter på at innstillingene lagres …'))
            self.shutdown = ProgramShutdown(
                lambda: list(self.managed_windows.values()),
                lambda: any(p.deadline and p.process and p.process.poll() is None
                            for key, p in self.panels.items() if key in ('digital', 'hammap')))
            self.shutdown_timer.start()
            return
        if not all([panel.detach() for panel in self.panels.values()]):
            self.shutdown_complete = False
            self.centralWidget().setEnabled(True)
            QMessageBox.warning(self,'HamNavigator MY SHACK',ui_language.t('Et programvindu kunne ikke løsnes. Lukk programmet i panelet før du lukker Radioassistenten.'))
            event.ignore()
            return
        self.closing=True
        try: request('audio/stop',{})
        except Exception: pass
        try: request('backend/stop',{})
        except Exception: pass
        event.accept()

    def snapshot(self):
        return {'title':self.windowTitle(),'hwnd':int(self.winId()),'panel_count':len(self.windows),'layout':self.layout_value(),'shutdown_pending':self.shutdown_pending,
            'panels':{key:{'status':panel.status.text(),'attached':bool(panel.surface.window and panel.surface.window.alive()),
                'visible':panel.isVisible(),'hwnd':panel.surface.window.hwnd if panel.surface.window else None,
                'parent':int(panel.surface.winId())} for key,panel in self.panels.items()}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--panel', choices=['home',*LABELS,'both','hamnavigator'], default='home')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--close', action='store_true')
    parser.add_argument('--no-resume', action='store_true', help=ui_language.t('Åpne arbeidsplassen uten å starte radioprogrammene'))
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setApplicationName('HamNavigator MY SHACK')
    client = QLocalSocket()
    client.connectToServer(SOCKET_NAME)
    if client.waitForConnected(700):
        client.write(('status' if args.status else 'close' if args.close else args.panel).encode())
        client.waitForBytesWritten(1000)
        if args.status and client.waitForReadyRead(3000):
            print(bytes(client.readAll()).decode())
        client.disconnectFromServer()
        return 0
    if args.status or args.close:
        print(json.dumps({'running':False}))
        return 0
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(SOCKET_NAME):
        raise RuntimeError(ui_language.t('Radioassistent-vinduet er allerede under oppstart. Prøv igjen.'))
    shell = Shell(resume=not args.no_resume)
    connections = []
    def incoming():
        connection = server.nextPendingConnection()
        connections.append(connection)
        def read():
            key = bytes(connection.readAll()).decode(errors='ignore')
            if key in ('home',*LABELS,'both','hamnavigator'):
                shell.activate(key)
            elif key == 'status':
                connection.write(json.dumps(shell.snapshot(), ensure_ascii=True).encode())
                connection.flush()
            elif key == 'close':
                shell.close()
            connection.disconnectFromServer()
        connection.readyRead.connect(read)
        if connection.bytesAvailable():
            read()
        connection.disconnected.connect(connection.deleteLater)
    server.newConnection.connect(incoming)
    shell.showMaximized()
    if args.panel != 'home':
        QTimer.singleShot(400, lambda: shell.activate(args.panel))
    return app.exec()

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,str(exc),ui_language.t('Radioassistent – vindusfeil'),0x10)
        raise
