#include <QApplication>
#include <QAction>
#include <QTreeView>
#include <QDropEvent>
#include <QDragEnterEvent>
#include <QMimeData>
#include <QMessageBox>
#include <QTimer>
#include <QSplashScreen>
#include <cstdio>
#include "main_ms.h"

QSplashScreen *splash = nullptr;
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    if (argc != 2) return 6;
    _ReadSSAndSet_();
    QTimer prompts;
    QObject::connect(&prompts, &QTimer::timeout, [] {
        if (auto *dialog = qobject_cast<QMessageBox*>(QApplication::activeModalWidget())) {
            fprintf(stderr, "Dialog: %s\n", qPrintable(dialog->text()));
            dialog->reject();
        }
    });
    prompts.start(500);
    Main_Ms window("");
    window.show();
    QTimer::singleShot(1500, [&] {
        bool found = false;
        for (auto *action : window.findChildren<QAction*>()) {
            if (action->text().trimmed() == "FT8" && action->isCheckable()) {
                action->setChecked(true); found = true; break;
            }
        }
        if (!found) {app.exit(7);return;}
        QMimeData mime;
        mime.setUrls({QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1]))});
        QDragEnterEvent enter(QPoint(3, 3), Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
        QApplication::sendEvent(&window, &enter);
        QDropEvent drop(QPointF(3, 3), Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
        QApplication::sendEvent(&window, &drop);
        fprintf(stderr,"File drop accepted: %d\n", drop.isAccepted());
    });
    QTimer poll;
    QObject::connect(&poll, &QTimer::timeout, [&] {
        for (auto *view : window.findChildren<QTreeView*>()) {
            auto *m = view->model();
            if (!m) continue;
            for(int row=0;row<m->rowCount();++row)
                for(int col=0;col<m->columnCount();++col) {
                    const QString s=m->index(row,col).data().toString();
                    if(s.contains("SP4FCA G4CUS R+13") || s.contains("S9CT 9A4ZM -04") || s.contains("DC8VA LZ1CWK R-09")) {
                        fprintf(stdout,"PASS recorded FT8 WAV decoded by native Digital: %s\n",qPrintable(s));fflush(stdout);app.exit(0);return;
                    }
                }
        }
    });
    poll.start(500);
    QTimer::singleShot(120000, [&] { app.exit(8); });
    int result=app.exec();
    // Isolated QA process; main destructor can raise a "quit" confirmation.
    fflush(nullptr);
    std::_Exit(result);
}
