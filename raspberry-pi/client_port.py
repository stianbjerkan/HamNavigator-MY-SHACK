"""Prepare the client files for Debian, without modifying Windows distribution files."""
from pathlib import Path


def adapt(folder):
    def edit(name, before, after):
        file = folder / name
        value = file.read_text(encoding="utf-8")
        if value.count(before) != 1:
            raise ValueError(f"Unexpected {name}: {before}")
        file.write_text(value.replace(before, after), encoding="utf-8")

    edit("cloud_sync.py", "if os.name!='nt':raise ValueError(ui_language.t('Denne klienten krever Windows DPAPI.'))",
         "from pi_station import protect as pi_protect\n    return pi_protect(text,decrypt)")
    # Remove the unreachable Windows DPAPI implementation in this build.
    file = folder / "cloud_sync.py"
    code = file.read_text()
    start = code.index("    class Blob(ctypes.Structure):")
    end = code.index("\nclass Sync:", start)
    file.write_text(code[:start] + code[end:])
    edit("cloud_sync.py", "'platform':'Windows'", "'platform':'Raspberry Pi'")
    edit("operations.py", "'platform':'Windows'", "'platform':'Raspberry Pi'")
    # Never send or apply a desktop-specific panel arrangement, serial port,
    # audio device or Map profile on a Pi. Filter both sides including tombstones.
    excluded = "('digital/preferences','map/preferences','panels/preferences','panels/layout','setting/preferences','setting/modules')"
    edit("cloud_sync.py", "local=canonical_objects(captured)",
         "local={k:v for k,v in canonical_objects(captured).items() if k not in " + excluded + "}")
    edit("cloud_sync.py", "if item['key']=='setting/vault-key':return None",
         "if item['key']=='setting/vault-key' or item['key'] in " + excluded + ":return None")
    edit("cloud_sync.py", "for key in sorted(set(local)|set(previous)|set(remote)):",
         "for key in sorted(set(local)|set(previous)|set(remote)):\n                if key in " + excluded + ":continue")
    edit("radio_assistant.py", "def open_desktop(panel='home', *, resume=True):",
         "def open_desktop(panel='home', *, resume=True):\n    from pi_station import open_panel\n    return open_panel(panel)\n\ndef _windows_desktop(panel, resume):")
    file = folder / "radio_assistant.py"
    code = file.read_text()
    start = code.index("def _windows_desktop(")
    end = code.index("def open_app():", start)
    file.write_text(code[:start] + code[end:])
    edit("radio_assistant.py", "'18763'", "'18765'")
    # Present the field features with functioning native or web implementations.
    for locale, manual, radio_label in (
        ("", "Bruksanvisning for Raspberry Pi", "Åpne HamNavigator Digital"),
        ("languages/en/", "Raspberry Pi user guide", "Open HamNavigator Digital"),
        ("languages/sv/", "Raspberry Pi-handbok", "Öppna HamNavigator Digital"),
    ):
        import re
        page = folder / locale / "app.html"
        html = page.read_text(encoding="utf-8")
        lang = "sv" if "sv" in locale else "en" if "en" in locale else "nb"
        help_text = (Path(__file__).parent / ("guide-" + lang + ".html")).read_text(encoding="utf-8")
        style = """<style>
[data-page="gridtracker"], nav button[data-page="listener"], #module-picker,
#page-gridtracker, #page-listener {display:none!important}
</style>"""
        html = html.replace("</head>", style + "</head>")
        html, changes = re.subn(r'(<section\b[^>]*id="page-ft8"[^>]*>)',
                                lambda m: m[1] + '<details class="card"><summary>' + manual + '</summary>' + help_text + '</details>',
                                html)
        if changes != 1:
            raise ValueError(f"Missing radio page in {page}")
        html = re.sub(r'(<button[^>]*id="mshv-open"[^>]*>)[^<]*(</button>)',
                      lambda m: m[1] + radio_label + m[2], html)
        page.write_text(html, encoding="utf-8")
