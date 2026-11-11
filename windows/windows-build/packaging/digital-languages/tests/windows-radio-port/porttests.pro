QT += core serialport testlib
QT -= gui
CONFIG += console testcase c++11
TEMPLATE = app
TARGET = porttests
INCLUDEPATH += ../../src/HvRigControl
HEADERS += ../../src/HvRigControl/windowsradioport.h
SOURCES += porttests.cpp ../../src/HvRigControl/windowsradioport.cpp
