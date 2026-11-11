#include "windowsradioport.h"
#include <QtTest>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <windows.h>

// Only the fault-injection tests use this device. The busy/missing test calls
// the real Windows serial driver entry points using an exclusive temporary file.
class FaultPort : public QSerialPort
{
public:
    std::atomic<int> entered{0}, closed{0}, writes{0}, drainCalls{0};
    bool blockWrite = false;
    bool failWrite = false;
    bool open(OpenMode mode) override {
        ++entered;
        if (portName() == "slow") QThread::msleep(300);
        if (portName() == "timeout") QThread::msleep(6900);
        return QIODevice::open(mode | QIODevice::Unbuffered);
    }
    void close() override { ++closed; pending = 0; buffer.clear(); QIODevice::close(); }
    qint64 bytesAvailable() const override { return buffer.size() + QIODevice::bytesAvailable(); }
    qint64 bytesToWrite() const override { return pending; }
    bool waitForBytesWritten(int ms) override {
        ++drainCalls;
        QThread::msleep(ms);
        return false;
    }
    void incoming(const QByteArray &bytes) { buffer += bytes; emit readyRead(); }
protected:
    qint64 readData(char *dst, qint64 max) override {
        const int count = qMin<qint64>(buffer.size(), max);
        memcpy(dst, buffer.constData(), count);
        buffer.remove(0, count);
        return count;
    }
    qint64 writeData(const char *, qint64 count) override {
        ++writes;
        if (failWrite) {
            emit errorOccurred(QSerialPort::WriteError);
            return -1;
        }
        if (blockWrite) pending += count;
        return count;
    }
private:
    qint64 pending = 0;
    QByteArray buffer;
};

class PortTests : public QObject
{
    Q_OBJECT
private slots:
    void windowsMissingAndBusy() {
        QTemporaryDir tmp;
        QVERIFY(tmp.isValid());
        const auto path = QDir::toNativeSeparators(tmp.filePath("exclusive-test-port"));
        WindowsRadioPort port;
        QSignalSpy changes(&port, &WindowsRadioPort::stateChanged);
        port.select(path);
        QTRY_COMPARE(changes.count(), 1);
        QVERIFY(!port.isOpen());
        const QString missingReason = changes.takeFirst().at(1).toString();
        QVERIFY(!missingReason.isEmpty());
        const HANDLE lock = CreateFileW(reinterpret_cast<const wchar_t *>(path.utf16()), GENERIC_WRITE,
            0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
        QVERIFY(lock != INVALID_HANDLE_VALUE);
        port.select(path);
        QTRY_COMPARE(changes.count(), 1);
        QVERIFY(!port.isOpen());
        QVERIFY(changes.first().at(1).toString() != missingReason);
        QVERIFY(CloseHandle(lock));
    }

    void lateOpenLeavesUiResponsive() {
        auto *device = new FaultPort;
        WindowsRadioPort port(nullptr, device);
        QSignalSpy changes(&port, &WindowsRadioPort::stateChanged);
        QTimer heartbeat;
        QSignalSpy ticks(&heartbeat, &QTimer::timeout);
        heartbeat.start(10);
        port.select("slow");
        QTRY_COMPARE(device->entered.load(), 1);
        port.select("None");
        port.select("replacement");
        QTRY_VERIFY(port.isOpen());
        QCOMPARE(changes.count(), 1);
        QVERIFY(ticks.count() >= 10);
        QCOMPARE(device->entered.load(), 2);
        QCOMPARE(device->closed.load(), 1);
    }

    void timedOutOpenCannotReconnectItself() {
        auto *device = new FaultPort;
        WindowsRadioPort port(nullptr, device);
        QSignalSpy changes(&port, &WindowsRadioPort::stateChanged);
        port.select("timeout");
        QTRY_VERIFY_WITH_TIMEOUT(changes.count() == 1, 6800);
        QVERIFY(!port.isOpen());
        QVERIFY(changes.first().at(1).toString().contains("timed out"));
        port.select("next");
        QTRY_VERIFY(port.isOpen());
        QCOMPARE(changes.count(), 2);
        QCOMPARE(device->closed.load(), 1);
    }

    void disconnectWhileReadingThenReconnect() {
        auto *device = new FaultPort;
        WindowsRadioPort port(nullptr, device);
        QSignalSpy received(&port, &WindowsRadioPort::dataReceived);
        QSignalSpy lost(&port, &WindowsRadioPort::connectionLost);
        port.select("test");
        QTRY_VERIFY(port.isOpen());
        QMetaObject::invokeMethod(device, [device] {
            device->incoming("ABC");
            emit device->errorOccurred(QSerialPort::ResourceError);
            device->incoming("stale");
        }, Qt::QueuedConnection);
        QTRY_COMPARE(lost.count(), 1);
        QCOMPARE(received.count(), 1);
        QCOMPARE(received.at(0).at(0).toByteArray(), QByteArray("ABC"));
        QVERIFY(!port.isOpen());
        port.write("OLD", 3);
        port.select("test");
        QTRY_VERIFY(port.isOpen());
        port.write("NEW", 3);
        QTRY_COMPARE(device->writes.load(), 1);
    }

    void disconnectDuringWrite() {
        auto *device = new FaultPort;
        device->failWrite = true;
        WindowsRadioPort port(nullptr, device);
        QSignalSpy lost(&port, &WindowsRadioPort::connectionLost);
        port.select("test");
        QTRY_VERIFY(port.isOpen());
        port.write("test", 4);
        QTRY_COMPARE(lost.count(), 1);
        QVERIFY(!port.isOpen());
        QTRY_COMPARE(device->closed.load(), 1);
    }

    void stalledOutputHasBoundedDrain() {
        auto *device = new FaultPort;
        device->blockWrite = true;
        WindowsRadioPort port(nullptr, device);
        port.select("first");
        QTRY_VERIFY(port.isOpen());
        port.write("RX", 2);
        QTRY_COMPARE(device->writes.load(), 1);
        QTimer heartbeat;
        QSignalSpy ticks(&heartbeat, &QTimer::timeout);
        heartbeat.start(10);
        QElapsedTimer elapsed;
        elapsed.start();
        port.select("next");
        QTRY_VERIFY(port.isOpen());
        QCOMPARE(device->drainCalls.load(), 1);
        QVERIFY(ticks.count() >= 10);
        QVERIFY(elapsed.elapsed() < 1500);
    }

    void repeatedChangeAndIndependentPttPort() {
        auto *catDevice = new FaultPort;
        auto *pttDevice = new FaultPort;
        WindowsRadioPort cat(nullptr, catDevice), ptt(nullptr, pttDevice);
        ptt.select("ptt");
        QTRY_VERIFY(ptt.isOpen());
        for (int i = 0; i < 20; ++i) {
            cat.select("cat");
            QTRY_VERIFY(cat.isOpen());
            cat.write("poll", 4);
            QTRY_COMPARE(catDevice->writes.load(), i + 1);
            cat.select("None");
            QTRY_COMPARE(catDevice->closed.load(), i + 1);
            QVERIFY(ptt.isOpen());
        }
        QCOMPARE(pttDevice->entered.load(), 1);
    }
};

QTEST_GUILESS_MAIN(PortTests)
#include "porttests.moc"
