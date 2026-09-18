"""Install the client-only Map outbox adapter into the packaged Map sources."""
from pathlib import Path
import shutil
def install(bundle):
    renderer=Path(bundle)/'release/HamNavigator-Map/resources/app/src/renderer'
    shutil.copy2(Path(__file__).with_suffix('.js'),renderer/'lib/hamnavigator-delivery.js')
    path=renderer/'GridTracker2.html';text=path.read_text(encoding='utf-8')
    if 'hamnavigator-delivery.js' not in text:
        assert '</head>' in text
        path.write_text(text.replace('</head>','<script src="./lib/hamnavigator-delivery.js" defer></script></head>'),encoding='utf-8')
