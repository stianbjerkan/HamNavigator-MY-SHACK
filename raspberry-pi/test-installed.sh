#!/bin/sh
set -eu
qsrc=/tmp/hn-src/HamNavigator-kildekode/src/HvRigControl/qexsp_1_2rc
src=$(pwd)/raspberry-pi
mkdir -p /tmp/hn-port-test
cd /tmp/hn-port-test
cat > port.pro <<EOF
QT = core
CONFIG += console c++11
DEFINES += _LINUX_ QESP_NO_UDEV
INCLUDEPATH += "$qsrc"
SOURCES += "$src/port-test.cpp" "$qsrc/qextserialport.cpp" "$qsrc/qextserialport_unix.cpp"
HEADERS += "$qsrc/qextserialport.h" "$qsrc/qextserialport_p.h"
LIBS += -lutil
TARGET = port-test
EOF
qmake port.pro
make -j2
./port-test
echo 'PASS POSIX adapter path and bidirectional CAT bytes over a pseudo-terminal'
export XDG_RUNTIME_DIR=$(mktemp -d)
dbus-run-session -- sh -ec 'printf %s test | gnome-keyring-daemon --unlock --components=secrets >/dev/null; python3 "$1/smoke.py"' sh "$src"
