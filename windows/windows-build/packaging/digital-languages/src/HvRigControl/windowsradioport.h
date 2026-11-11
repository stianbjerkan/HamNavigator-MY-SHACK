#ifndef HAMNAVIGATOR_WINDOWS_RADIO_PORT_H
#define HAMNAVIGATOR_WINDOWS_RADIO_PORT_H

#include <QObject>
#include <QSerialPort>
#include <QThread>
#include <atomic>
#include <memory>

// This object and the Windows port live together on a dedicated I/O thread.
class RadioPortWorker : public QObject
{
    Q_OBJECT
public:
    RadioPortWorker(QSerialPort *serial, std::shared_ptr<std::atomic<quint64>> wanted);
    void select(quint64 ticket, const QString &name, int baud);
    void finish();
    void setBaud(int baud);
    void setLine(bool dtr, bool value);
    void writeCommand(const QByteArray &command);
    bool active(quint64 ticket) const { return online && session == ticket; }

signals:
    void status(quint64 ticket, bool opened, QString reason);
    void received(quint64 ticket, QByteArray data);

private:
    void fail(const QString &reason);
    QSerialPort *io;
    std::shared_ptr<std::atomic<quint64>> wanted;
    quint64 session = 0;
    bool online = false;
};

class WindowsRadioPort : public QObject
{
    Q_OBJECT
public:
    explicit WindowsRadioPort(QObject *parent = nullptr, QSerialPort *serial = nullptr);
    ~WindowsRadioPort() override;
    void select(const QString &name);
    bool isOpen() const { return opened; }
    void setBaudRate(int baud);
    void setDtr(bool value);
    void setRts(bool value);
    void write(const char *data, int size);

signals:
    void connectionLost();
    void stateChanged(bool opened, QString reason);
    void dataReceived(QByteArray data);

private:
    void setLine(bool dtr, bool value);
    QThread *thread;
    RadioPortWorker *worker;
    std::shared_ptr<std::atomic<quint64>> wanted;
    quint64 generation = 0;
    int baudRate = 9600;
    bool opened = false;
    bool opening = false;
};

#endif
