// Exercise the real POSIX serial backend against a virtual radio, without RF.
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QTimer>
#include <pty.h>
#include <poll.h>
#include <unistd.h>
#include "qextserialport.h"

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    int master, slave;
    char name[128] = {};
    if (openpty(&master, &slave, name, nullptr, nullptr) < 0) return 1;
    const QString dir = "/dev/serial/by-id";
    const QString link = dir + "/usb-HamNavigator-pty-test-" + QString::number(getpid());
    if (!QDir().mkpath(dir) || !QFile::link(QString::fromLocal8Bit(name), link)) return 2;
    QextSerialPort port(link.mid(5), QextSerialPort::EventDriven);
    port.setBaudRate(BAUD19200);
    port.setFlowControl(FLOW_OFF);
    port.setParity(PAR_NONE);
    port.setDataBits(DATA_8);
    port.setStopBits(STOP_1);
    bool ok = port.open(QIODevice::ReadWrite | QIODevice::Unbuffered);
    if (ok) {
        QByteArray received;
        QObject::connect(&port, &QIODevice::readyRead, [&] {
            received += port.readAll();
            if (received == "CAT") app.exit(0);
        });
        QTimer::singleShot(2000, [&] { app.exit(3); });
        ok = write(master, "CAT", 3) == 3 && app.exec() == 0;
        char reply[4] = {};
        pollfd descriptor = {master, POLLIN, 0};
        ok = ok && port.write("ACK", 3) == 3 && poll(&descriptor, 1, 1500) > 0
             && read(master, reply, 3) == 3 && QByteArray(reply, 3) == "ACK";
        port.close();
    }
    QFile::remove(link);
    close(slave);
    close(master);
    return ok ? 0 : 4;
}
