"""Load the plasmoid's real main.qml against stub org.kde.* modules and
evaluate QML expressions on its root item:

    python3 render.py '<expr>' ['<expr>' ...]   -> one JSON list of results

Run in its own process: Qt wants one QGuiApplication per process."""
import json, os, sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
except ImportError as e:            # no PySide6, or no libEGL/libGL under it
    print(e, file=sys.stderr)
    sys.exit(77)

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, "..", "..", "kde", "plasmoid", "contents", "ui", "main.qml")

app = QGuiApplication(sys.argv[:1])
engine = QQmlEngine()
engine.addImportPath(os.path.join(HERE, "stubs"))
comp = QQmlComponent(engine, QUrl.fromLocalFile(os.path.abspath(MAIN)))
root = comp.create()
if root is None:
    sys.exit("main.qml failed to load: " + "; ".join(e.toString() for e in comp.errors()))
out = []
for expr in sys.argv[1:]:
    value, undefined = QQmlExpression(engine.rootContext(), root, expr).evaluate()
    out.append(None if undefined else value)
print(json.dumps(out))
