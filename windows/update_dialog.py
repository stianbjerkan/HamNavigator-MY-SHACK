"""Non-blocking update dialog for the desktop shell."""
import ui_language
import os
from pathlib import Path
import subprocess
import threading

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
from app_update import (current_version, check_update, download_update,
                        installer_arguments, UpdateCancelled)


class UpdateWorker(QThread):
    progress = Signal(int, int)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation
        self.cancel = threading.Event()
        self.result, self.error = None, None

    def run(self):
        try:
            self.result = self.operation(self)
        except Exception as exc:
            self.error = exc


class UpdateDialog(QDialog):
    def __init__(self, root, parent):
        super().__init__(parent)
        self.root, self.worker, self.info, self.installer = Path(root), None, None, None
        self.version = current_version(root)
        self.setWindowTitle(ui_language.t('Oppdater HamNavigator MY SHACK'))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(ui_language.t('HamNavigator MY SHACK • versjon ') + self.version))
        self.status = QLabel(ui_language.t('Sjekker etter oppdateringer på GitHub …'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        note = QLabel(ui_language.t('Oppdateringer hentes fra stianbjerkan/HamNavigator-MY-SHACK.\nHele programpakken oppdateres. Oppsett og logger beholdes.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        bar = QHBoxLayout()
        self.action = QPushButton(ui_language.t('Se etter oppdateringer'))
        self.action.clicked.connect(self.act)
        self.close_button = QPushButton(ui_language.t('Lukk'))
        self.close_button.clicked.connect(self.reject)
        bar.addWidget(self.action)
        bar.addWidget(self.close_button)
        layout.addLayout(bar)
        self.check()

    def busy(self):
        return self.worker is not None

    def start(self, operation, completed):
        self.action.setEnabled(False)
        self.close_button.setText(ui_language.t('Avbryt'))
        self.worker = UpdateWorker(operation, self)
        self.worker.progress.connect(self.show_progress)
        self.worker.finished.connect(lambda: self.finished(completed))
        self.worker.start()

    def finished(self, completed):
        worker, self.worker = self.worker, None
        self.action.setEnabled(True)
        self.close_button.setEnabled(True)
        self.close_button.setText(ui_language.t('Lukk'))
        self.progress.setRange(0, 100)
        worker.deleteLater()
        if worker.cancel.is_set() or isinstance(worker.error, UpdateCancelled):
            self.status.setText(ui_language.t('Oppdateringen ble avbrutt. Du kan prøve igjen.'))
            self.progress.setValue(0)
        elif worker.error:
            self.status.setText(ui_language.t('Kunne ikke oppdatere: ') + str(worker.error))
            self.progress.setValue(0)
        else:
            completed(worker.result)

    def check(self):
        self.info, self.installer = None, None
        self.action.setText(ui_language.t('Se etter oppdateringer'))
        self.progress.setRange(0, 0)
        self.status.setText(ui_language.t('Sjekker etter oppdateringer på GitHub …'))
        self.start(lambda worker: check_update(self.version), self.checked)

    def checked(self, info):
        self.info = info
        self.progress.setValue(0)
        if info:
            self.status.setText(f"{ui_language.t('Versjon ')}{info['version']}{ui_language.t(' er tilgjengelig (')}{info['size'] / 1024 ** 2:.0f}{ui_language.t(' MB).\nTrykk «Oppdater nå» for å laste ned og starte installasjonen. Installasjonen lagrer og lukker HamNavigator, Digital og Map før oppdatering. Avslutt radiokjøringen først.')}")
            self.action.setText(ui_language.t('Oppdater nå'))
        else:
            self.status.setText(ui_language.t('Du har nyeste versjon – ') + self.version + '.')

    def act(self):
        if self.installer:
            self.install(self.installer)
        elif self.info:
            cache = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'HamNavigator' / 'updates'
            self.status.setText(ui_language.t('Laster ned oppdatering …'))
            self.progress.setRange(0, 100)
            self.start(lambda worker: download_update(self.info, cache, worker.progress.emit, worker.cancel), self.install)
        else:
            self.check()

    def show_progress(self, received, total):
        self.progress.setRange(0, 100)
        self.progress.setValue(received * 100 // total)
        self.status.setText(f"{ui_language.t('Laster ned: ')}{received / 1024 ** 2:.0f}{ui_language.t(' av ')}{total / 1024 ** 2:.0f} MB")

    def install(self, path):
        self.installer = path
        try:
            subprocess.Popen([str(path), *installer_arguments(self.root)], cwd=str(path.parent))
        except OSError as exc:
            self.status.setText(ui_language.t('Kunne ikke starte installasjonen: ') + str(exc))
            self.action.setText(ui_language.t('Start installasjon på nytt'))
            return
        self.status.setText(ui_language.t('Filen er kontrollert. Installasjonsprogrammet er startet.\nFølg trinnene der. HamNavigator lagres og lukkes før filene oppdateres.'))
        self.progress.setValue(100)
        self.action.setEnabled(False)
        # Installer preflight closes the existing shell before Restart Manager.

    def reject(self):
        if self.busy():
            self.worker.cancel.set()
            self.close_button.setEnabled(False)
            self.status.setText(ui_language.t('Avbryter …'))
        else:
            super().reject()

    def closeEvent(self, event):
        if self.busy():
            self.reject()
            event.ignore()
        else:
            event.accept()
