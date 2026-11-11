// HamNavigator's local presentation preference. No radio or log settings are changed.
#ifndef HAMNAVIGATOR_LANGUAGE_H
#define HAMNAVIGATOR_LANGUAGE_H
#include <QApplication>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
inline QString hnLanguageFolder() {
    QString folder=qEnvironmentVariable("RADIOASSISTENT_DATA");
    return folder.isEmpty()?qEnvironmentVariable("APPDATA")+"/Radioassistent":folder;
}
inline QString hnLanguageChoice() {
    QString choice=qEnvironmentVariable("HAMNAVIGATOR_LANGUAGE");
    if(choice=="en"||choice=="nb"||choice=="sv")return choice;
    QFile file(hnLanguageFolder()+"/ui-language.json");
    if(file.open(QIODevice::ReadOnly))choice=QJsonDocument::fromJson(file.readAll()).object().value("language").toString();
    return choice=="sv"?"sv":choice=="en"?"en":"nb";
}
inline bool hnEnglish() {
    if(qApp && qApp->property("hnLanguage").isValid())return qApp->property("hnLanguage").toString()=="en";
    return hnLanguageChoice()=="en";
}
inline QString hnLanguage() {return qApp && qApp->property("hnLanguage").isValid()?qApp->property("hnLanguage").toString():hnLanguageChoice();}
inline QString hnSwedish(const QString &source) {
    static const QJsonObject catalog=[](){QFile file(":/branding/language-sv.json");if(!file.open(QIODevice::ReadOnly))return QJsonObject();return QJsonDocument::fromJson(file.readAll()).object();}();
    if(catalog.contains(source))return catalog.value(source).toString();
    const QString trimmed=source.trimmed();
    if(catalog.contains(trimmed)){const int start=source.indexOf(trimmed);return source.left(start)+catalog.value(trimmed).toString()+source.mid(start+trimmed.size());}
    const int tab=source.indexOf('\t');
    if(tab>0)return hnSwedish(source.left(tab))+source.mid(tab);
    return source;
}
inline QString hnText(const char *nb,const char *en) {return hnLanguage()=="sv"?hnSwedish(QString::fromUtf8(en)):QString::fromUtf8(hnEnglish()?en:nb);}
inline bool hnSaveLanguage(const QString &choice) {
    if(choice!="nb"&&choice!="en"&&choice!="sv")return false;
    if(!QDir().mkpath(hnLanguageFolder()))return false;
    QSaveFile file(hnLanguageFolder()+"/ui-language.json");
    if(!file.open(QIODevice::WriteOnly))return false;
    QJsonObject value;value.insert("language",choice);
    if(file.write(QJsonDocument(value).toJson())<0)return false;
    return file.commit();
}
#endif
