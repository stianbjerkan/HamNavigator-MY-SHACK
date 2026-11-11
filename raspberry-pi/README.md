# HamNavigator Portable for Raspberry Pi 4

Install on **64-bit Raspberry Pi OS with Desktop**. The package targets Debian Bookworm ARM64. Open a terminal in the directory where you downloaded the package and run:

```sh
sudo apt install ./hamnavigator-portable_1.9.23-1_arm64.deb
```

Open **HamNavigator Portable** from the application menu. Sign in to your HamNavigator account, select the Digital page and open Digital. Connect your DE-19 or Digirig before opening Digital. The expandable Raspberry Pi guide on that page explains USB sound, CAT, PTT and field logging in Norwegian, English and Swedish. Unlock the desktop login keyring if prompted. The local web interface only listens on loopback. Keep the Pi clock on UTC-correct time for FT8.

Logs and settings live in the user's XDG data directory (normally `~/.local/share/hamnavigator-portable`). The desktop Map executable and Windows panel layout are not included. The field map in POTA/SOTA is available in the web interface. A network connection is required to validate a Cloud login on startup. A running Digital session continues to log locally during a network outage. Check sign-in, RX audio, CAT readback and your radio's PTT method before field use.

## Source and build

The `windows/` directory supplies the shared client and web UI. `prepare.py` applies Pi-specific changes to the original [1.9.23 Digital release source](https://github.com/stianbjerkan/HamNavigator-MY-SHACK/releases/download/v1.9.23/HamNavigator-Digital-kildekode.zip). The co-located GitHub workflow contains the pinned digest, Debian dependencies, build commands and tests. Stock station data comes from the MSHV 2.76.6 distribution; see the bundled license and attribution. No personal station or radio settings are shipped.
