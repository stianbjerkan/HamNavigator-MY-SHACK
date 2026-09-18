# HamNavigator MY SHACK

The current Windows MY SHACK client is in `windows/`. Its `VERSION` is the
release version. The C#/XAML files in the repository root are the older WPF
prototype; they are not the installed MY SHACK product or its updater.

Every completed client change includes updated Norwegian, English and Swedish
help, relevant tests, a Windows installer and a GitHub Release with corresponding
client source archives and SHA256SUMS.txt. A commit alone is not a release.
Verify uploaded asset SHA-256/size and that the previous PC updater discovers
the new stable release. Android prereleases must not replace the PC Latest.

Do not publish private Cloud server/gateway code, credentials, signing keys,
account data or backups. Preserve user logs and settings. Do not transmit on a
real radio or upload real contacts while testing.

The local maintained source and packaging instructions are under
Desktop/Hamnavigator/Server/Kildekode. Read Server/AGENTS.md before working there.
