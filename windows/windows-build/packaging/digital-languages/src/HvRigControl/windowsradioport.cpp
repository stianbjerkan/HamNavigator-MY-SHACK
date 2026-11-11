#include "windowsradioport.h"
#include <QElapsedTimer>
#include <QTimer>

RadioPortWorker::RadioPortWorker(QSerialPort *serial, std::shared_ptr<std::atomic<quint64>> desired)
    : io(serial), wanted(desired)
{
    io->setParent(this);
    io->setStopBits(QSerialPort::TwoStop);
    io->setReadBufferSize(65536);
    connect(io, &QSerialPort::readyRead, this, [this] {
        const QByteArray data = io->readAll();
        if (online && !data.isEmpty()) emit received(session, data);
    });
    connect(io, &QSerialPort::errorOccurred, this, [this](QSerialPort::SerialPortError error) {
        if (!online || (error != QSerialPort::ResourceError && error != QSerialPort::ReadError &&
                        error != QSerialPort::WriteError && error != QSerialPort::DeviceNotFoundError)) return;
        fail(io->errorString());
    });
}

void RadioPortWorker::fail(const QString &reason)
{
    if (!online) return;
    online = false;
    const quint64 ticket = session;
    emit status(ticket, false, reason);
    // Qt can emit the error from inside an I/O completion. Close after it returns.
    QTimer::singleShot(0, this, [this, ticket] {
        if (session == ticket && !online && io->isOpen()) io->close();
    });
}

void RadioPortWorker::finish()
{
    const bool drain = online;
    online = false;
    if (!io->isOpen()) return;
    // Give already queued commands (including PTT off) time to leave a working port.
    QElapsedTimer timer;
    timer.start();
    while (drain && io->bytesToWrite() && timer.elapsed() < 350) {
        const int remaining = 350 - int(timer.elapsed());
        if (remaining <= 0 || !io->waitForBytesWritten(remaining)) break;
    }
    io->close();
}

void RadioPortWorker::select(quint64 ticket, const QString &name, int baud)
{
    if (wanted->load() != ticket) return;
    finish();
    session = ticket;
    if (name.isEmpty() || name == "None" || wanted->load() != ticket) return;
    io->setPortName(name);
    if (!io->setBaudRate(baud) || !io->open(QIODevice::ReadWrite)) {
        emit status(ticket, false, io->errorString());
        return;
    }
    if (wanted->load() != ticket) {
        io->close();
        return;
    }
    online = true;
    emit status(ticket, true, QString());
}

void RadioPortWorker::setBaud(int baud)
{
    if (!io->setBaudRate(baud)) fail(io->errorString());
}

void RadioPortWorker::setLine(bool dtr, bool value)
{
    if (dtr) io->setDataTerminalReady(value);
    else io->setRequestToSend(value);
}

void RadioPortWorker::writeCommand(const QByteArray &command)
{
    if (io->bytesToWrite() + command.size() > 65536) {
        fail(tr("CAT output queue full"));
        return;
    }
    if (io->write(command) != command.size()) fail(io->errorString());
}

WindowsRadioPort::WindowsRadioPort(QObject *parent, QSerialPort *serial)
    : QObject(parent), thread(new QThread), wanted(std::make_shared<std::atomic<quint64>>(0))
{
    worker = new RadioPortWorker(serial ? serial : new QSerialPort, wanted);
    worker->moveToThread(thread);
    connect(thread, &QThread::finished, worker, &QObject::deleteLater);
    connect(thread, &QThread::finished, thread, &QObject::deleteLater);
    connect(worker, &RadioPortWorker::status, this, [this](quint64 ticket, bool ok, const QString &reason) {
        if (ticket != generation) return;
        opening = false;
        const bool lost = opened && !ok;
        opened = ok;
        if (lost) emit connectionLost();
        emit stateChanged(ok, reason);
    });
    connect(worker, &RadioPortWorker::received, this, [this](quint64 ticket, const QByteArray &data) {
        if (opened && ticket == generation) emit dataReceived(data);
    });
    thread->start();
}

WindowsRadioPort::~WindowsRadioPort()
{
    // Invalidate outstanding opens; already accepted PTT-off operations are FIFO.
    wanted->store(++generation);
    RadioPortWorker *io = worker;
    QMetaObject::invokeMethod(io, [io] { io->finish(); QThread::currentThread()->quit(); },
                              Qt::QueuedConnection);
    // A Bluetooth driver can still be in CreateFile. It owns its thread and port
    // until it returns and cleans up; the window never joins it indefinitely.
    thread->wait(600);
}

void WindowsRadioPort::select(const QString &name)
{
    opened = false;
    const quint64 ticket = ++generation;
    wanted->store(ticket);
    opening = !name.isEmpty() && name != "None";
    if (opening) {
        QTimer::singleShot(6000, Qt::PreciseTimer, this, [this, ticket] {
            if (!opening || ticket != generation) return;
            select(QString());
            emit stateChanged(false, tr("Connection timed out"));
        });
    }
    const int baud = baudRate;
    RadioPortWorker *io = worker;
    QMetaObject::invokeMethod(io, [io, ticket, name, baud] { io->select(ticket, name, baud); },
                              Qt::QueuedConnection);
}

void WindowsRadioPort::setBaudRate(int baud)
{
    baudRate = baud;
    const quint64 ticket = generation;
    RadioPortWorker *io = worker;
    QMetaObject::invokeMethod(io, [io, ticket, baud] { if (io->active(ticket)) io->setBaud(baud); },
                              Qt::QueuedConnection);
}

void WindowsRadioPort::setLine(bool dtr, bool value)
{
    if (!opened) return;
    const quint64 ticket = generation;
    RadioPortWorker *io = worker;
    QMetaObject::invokeMethod(io, [io, ticket, dtr, value] { if (io->active(ticket)) io->setLine(dtr, value); },
                              Qt::QueuedConnection);
}

void WindowsRadioPort::setDtr(bool value) { setLine(true, value); }
void WindowsRadioPort::setRts(bool value) { setLine(false, value); }

void WindowsRadioPort::write(const char *data, int size)
{
    if (!opened || size <= 0) return;
    const quint64 ticket = generation;
    const QByteArray command(data, size);
    RadioPortWorker *io = worker;
    QMetaObject::invokeMethod(io, [io, ticket, command] { if (io->active(ticket)) io->writeCommand(command); },
                              Qt::QueuedConnection);
}
