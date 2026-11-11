"""Prepare the client files for Debian, without modifying Windows distribution files."""
from pathlib import Path
import re


def adapt(folder):
    def edit(name, before, after):
        file = folder / name
        value = file.read_text(encoding="utf-8")
        if value.count(before) != 1:
            raise ValueError(f"Unexpected {name}: {before}")
        file.write_text(value.replace(before, after), encoding="utf-8")

    def replace_region(name, start, end, implementation):
        file = folder / name
        code = file.read_text(encoding="utf-8")
        a, b = code.index(start), code.index(end, code.index(start) + len(start))
        file.write_text(code[:a] + implementation + "\n\n" + code[b:], encoding="utf-8")

    replace_region("cloud_sync.py", "def protect(text, decrypt=False):", "class Sync:",
                   "from pi_station import protect")
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
    replace_region("radio_assistant.py", "def open_desktop(", "def open_app():",
                   "def open_desktop(panel='home', *, resume=True):\n"
                   "    from pi_station import open_panel\n    return open_panel(panel)")
    edit("radio_assistant.py", "'18763'", "'18765'")
    # Present the field features with functioning native or web implementations.
    for locale, manual, radio_label in (
        ("", "Bruksanvisning for Raspberry Pi", "Åpne HamNavigator Digital"),
        ("languages/en/", "Raspberry Pi user guide", "Open HamNavigator Digital"),
        ("languages/sv/", "Raspberry Pi-handbok", "Öppna HamNavigator Digital"),
    ):
        js_name = locale + "app.js"
        edit(js_name, "function pageEnabled(page) {", "function pageEnabled(page) {\n  if (['gridtracker','listener'].includes(page)) return false;")
        page = folder / locale / "app.html"
        html = page.read_text(encoding="utf-8")
        lang = "sv" if "sv" in locale else "en" if "en" in locale else "nb"
        clouds = {
            "nb": "Digital og MY SHACK bruker hamnavigator.adi. Kontakter synkroniseres begge veier. Pi-en beholder sine egne USB-, lyd- og programinnstillinger.",
            "en": "Digital and MY SHACK share hamnavigator.adi. Contacts sync in both directions. USB, audio and program settings stay on the Pi.",
            "sv": "Digital och MY SHACK delar hamnavigator.adi. Kontakter synkroniseras åt båda hållen. USB-, ljud- och programinställningar sparas på Pi:n.",
        }
        cloud = folder / locale / "cloud.js"
        code, n = re.subn(r'<p class="small muted">[^<]*hamnavigator\.adi[^<]*</p>',
                          lambda _: '<p class="small muted">' + clouds[lang] + '</p>',
                          cloud.read_text(encoding="utf-8"))
        if n != 1:
            raise ValueError(f"Missing Cloud log description in {cloud}")
        cloud.write_text(code, encoding="utf-8")
        help_text = (Path(__file__).parent / ("guide-" + lang + ".html")).read_text(encoding="utf-8")
        style = """<style>
[data-page="gridtracker"], [data-page="listener"], #module-picker, #modules-choose,
label:has(input[name="mshv_path"]),label:has(input[name="gridtracker_path"]),
#page-gridtracker, #page-listener, #page-manual > :not(.pi-guide) {display:none!important}
</style>"""
        html = html.replace("</head>", style + "</head>")
        html, n = re.subn(r'(<section\b[^>]*id="page-manual"[^>]*>)',
                         lambda m: m[1] + '<article class="card pi-guide">' + help_text + '</article>', html)
        if n != 1:
            raise ValueError(f"Missing manual in {page}")
        html, changes = re.subn(r'(<section\b[^>]*id="page-ft8"[^>]*>)',
                                lambda m: m[1] + '<details class="card"><summary>' + manual + '</summary>' + help_text + '</details>',
                                html)
        if changes != 1:
            raise ValueError(f"Missing radio page in {page}")
        html = re.sub(r'(<button[^>]*id="mshv-open"[^>]*>)[^<]*(</button>)',
                      lambda m: m[1] + radio_label + m[2], html)
        page.write_text(html, encoding="utf-8")
