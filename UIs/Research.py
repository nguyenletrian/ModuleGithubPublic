import os
import sys
import ast
import json
import shutil
import importlib.machinery
import importlib.util
from pathlib import Path

import maya.cmds as cmds
import maya.OpenMayaUI as omui

try:
    from PySide6 import QtWidgets, QtCore
    from shiboken6 import getCppPointer
except ImportError:
    from PySide2 import QtWidgets, QtCore
    from shiboken2 import getCppPointer

import NLTA_General

UI = {}


def ReloadWindows(*args):
    combo = UI.get("window")
    if combo is None:
        return

    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    inspector = UI.get("widget")
    inspectorWindow = inspector.window() if inspector else None

    combo.blockSignals(True)

    try:
        combo.clear()
        combo.addItem("Select Window", None)

        windows = sorted(
            app.topLevelWidgets(),
            key=lambda w: w.windowTitle().casefold()
            if w.windowTitle() else ""
        )

        for window in windows:
            try:
                if not window.isWindow() or not window.isVisible():
                    continue

                # Exclude NLTA Research and its owning window
                if window is inspector or window is inspectorWindow:
                    continue

                title = window.windowTitle().strip()

                if title:
                    combo.addItem(title, window)

            except RuntimeError:
                continue
    finally:
        combo.blockSignals(False)

    UI["tree"].clear()
    ClearDetail()
    UI["sourceResults"].clear()
    UI["sourceMatches"] = []
    UI["originalModule"] = ""
    print("Loaded {} windows".format(combo.count() - 1))


def GetUIDisplay(widget):
    """Visible label of a QWidget. Model item data is handled separately."""
    try:
        if isinstance(widget, QtWidgets.QLineEdit):
            return widget.placeholderText() or widget.text()
        if isinstance(widget, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
            return widget.placeholderText() or widget.toPlainText()
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.currentText()
        if isinstance(widget, QtWidgets.QAbstractButton):
            return (widget.text() or widget.toolTip() or
                    widget.accessibleName() or widget.whatsThis())
        if isinstance(widget, QtWidgets.QLabel):
            return widget.text()
        if isinstance(widget, QtWidgets.QGroupBox):
            return widget.title()
        if isinstance(widget, QtWidgets.QTabWidget):
            index = widget.currentIndex()
            return widget.tabText(index) if index >= 0 else ""
        if isinstance(widget, QtWidgets.QTabBar):
            index = widget.currentIndex()
            return widget.tabText(index) if index >= 0 else ""
        if isinstance(widget, QtWidgets.QAbstractSpinBox):
            return widget.text()
        if isinstance(widget, QtWidgets.QProgressBar):
            return str(widget.value())
        if isinstance(widget, QtWidgets.QWidget):
            return (widget.windowTitle() or widget.accessibleName() or
                    widget.toolTip() or widget.whatsThis())
    except (RuntimeError, ReferenceError, AttributeError, TypeError):
        pass
    return ""


def GetQtDataEntries(widget, limit=250):
    """Inspect data owned by Qt views, tabs, combo items, actions and scenes.

    Entries are snapshots; no clicks, events, imports or scene changes.
    Caps on visited rows/columns/depth avoid traversing giant Qt models.
    """
    entries = []

    def add(name, kind, value):
        if len(entries) >= limit or value is None:
            return
        try:
            value = str(value).strip()
        except (RuntimeError, ReferenceError, ValueError, TypeError):
            return
        if value:
            entries.append({"name": name, "type": kind, "text": value[:3000]})

    try:
        if isinstance(widget, QtWidgets.QAbstractItemView):
            model = widget.model()
            if model is not None:
                for col in range(min(max(0, model.columnCount()), 12)):
                    add("Header[{}]".format(col), "Model Header",
                        model.headerData(col, QtCore.Qt.Horizontal,
                                         QtCore.Qt.DisplayRole))

                # BFS visits visible/proxy model rows, including nested tree rows.
                queue = [(QtCore.QModelIndex(), (), 0)]
                inspected = 0
                while queue and inspected < limit and len(entries) < limit:
                    parent, path, depth = queue.pop(0)
                    row_count = min(max(0, model.rowCount(parent)), 150)
                    col_count = min(max(1, model.columnCount(parent)), 8)
                    for row in range(row_count):
                        if inspected >= limit or len(entries) >= limit:
                            break
                        inspected += 1
                        indices = [model.index(row, col, parent)
                                   for col in range(col_count)]
                        values = []
                        for col, index in enumerate(indices):
                            if not index.isValid():
                                continue
                            display = model.data(index, QtCore.Qt.DisplayRole)
                            if display is None or str(display) == "":
                                display = model.data(index, QtCore.Qt.ToolTipRole)
                            if display is None or str(display) == "":
                                display = model.data(index, QtCore.Qt.UserRole)
                            if display is not None and str(display).strip():
                                values.append("{}: {}".format(col, display))
                        row_path = path + (row,)
                        path_text = "/".join(str(n) for n in row_path)
                        if values:
                            add("Row[{}]".format(path_text), "Model Item",
                                " | ".join(values))
                            entries[-1]["path"] = tuple(row_path)
                        if depth < 5 and indices and indices[0].isValid():
                            if model.hasChildren(indices[0]):
                                queue.append((indices[0], row_path, depth + 1))

        if isinstance(widget, QtWidgets.QComboBox):
            for index in range(min(widget.count(), limit)):
                add("Combo[{}]".format(index), "Combo Item",
                    widget.itemText(index))

        if isinstance(widget, QtWidgets.QTabBar):
            for index in range(min(widget.count(), limit)):
                add("Tab[{}]".format(index), "Tab Text",
                    widget.tabText(index) or widget.tabToolTip(index))

        if isinstance(widget, QtWidgets.QGraphicsView):
            scene = widget.scene()
            if scene is not None:
                for index, obj in enumerate(scene.items()[:limit]):
                    if isinstance(obj, QtWidgets.QGraphicsTextItem):
                        add("Graphics[{}]".format(index), "Graphics Text",
                            obj.toPlainText())
                    elif isinstance(obj, QtWidgets.QGraphicsSimpleTextItem):
                        add("Graphics[{}]".format(index), "Graphics Text",
                            obj.text())

        for index, action in enumerate(widget.actions()[:limit]):
            add("Action[{}]".format(index), "QAction",
                action.text() or action.toolTip() or action.whatsThis())

    except (RuntimeError, ReferenceError, AttributeError, TypeError, ValueError) as error:
        cmds.warning("GetQtDataEntries: {}".format(error))

    return entries


# ============================================================
# QT MODEL / CUSTOM WIDGET READ-ONLY INSPECTOR
# ============================================================

def _ReadQtShort(value, limit=500):
    """Bound output; avoid materializing arbitrary large objects."""
    if value is None:
        return "None"
    try:
        result = repr(value)
    except Exception as error:
        result = "<unrepresentable {}: {}>".format(type(value).__name__, error)
    return result[:limit] + ("..." if len(result) > limit else "")


def _ReadQtRoleMap(model):
    names = {
        int(QtCore.Qt.DisplayRole): "DisplayRole",
        int(QtCore.Qt.EditRole): "EditRole",
        int(QtCore.Qt.ToolTipRole): "ToolTipRole",
        int(QtCore.Qt.StatusTipRole): "StatusTipRole",
        int(QtCore.Qt.WhatsThisRole): "WhatsThisRole",
        int(QtCore.Qt.DecorationRole): "DecorationRole",
        int(QtCore.Qt.CheckStateRole): "CheckStateRole",
        int(QtCore.Qt.AccessibleTextRole): "AccessibleTextRole",
        int(QtCore.Qt.AccessibleDescriptionRole): "AccessibleDescriptionRole",
    }
    for offset in range(33):
        names[int(QtCore.Qt.UserRole) + offset] = "UserRole+{}".format(offset)
    try:
        for key, name in model.roleNames().items():
            try:
                label = bytes(name).decode("utf-8", errors="replace")
            except (AttributeError, ValueError, TypeError):
                label = str(name)
            role = int(key)
            names[role] = "{} ({})".format(names.get(role, "Role"), label)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass
    return names


def _ReadQtObjectReport(obj, lines, prefix=""):
    """Inspect the object's own Qt/Python metadata without invoking behavior."""
    cls = type(obj)
    lines.append("{}Python class: {}.{}".format(prefix, cls.__module__, cls.__name__))
    if isinstance(obj, QtCore.QObject):
        lines.append("{}Qt class: {}".format(prefix, obj.metaObject().className()))
        lines.append("{}objectName: {}".format(prefix, _ReadQtShort(obj.objectName())))
        try:
            for name in list(obj.dynamicPropertyNames())[:40]:
                name = bytes(name).decode("utf-8", errors="replace")
                if any(secret in name.lower() for secret in ("password", "secret", "token", "credential")):
                    continue
                lines.append("{}dynamic[{}]: {}".format(
                    prefix, name, _ReadQtShort(obj.property(name))))
        except (AttributeError, RuntimeError, TypeError, ValueError) as error:
            lines.append("{}Dynamic property read failed: {}".format(prefix, error))
    try:
        attributes = vars(obj)
    except (AttributeError, RuntimeError, TypeError):
        attributes = {}
    if attributes:
        lines.append("{}Python instance fields (up to 50):".format(prefix))
        for name, value in list(attributes.items())[:50]:
            if any(secret in name.lower() for secret in ("password", "secret", "token", "credential")):
                continue
            if isinstance(value, (str, int, float, bool)):
                desc = _ReadQtShort(value)
            else:
                desc = "<{}>".format(type(value).__name__)
                if isinstance(value, (list, dict, set, tuple)):
                    desc += " len={}".format(len(value))
            lines.append("{}  {}: {}".format(prefix, name, desc))


def _ReadQtIndexReport(model, index, lines, label, roles):
    if not index.isValid():
        lines.append("{}: invalid QModelIndex".format(label))
        return
    lines.append("{} (row={}, column={}):".format(label, index.row(), index.column()))
    for role, role_name in sorted(roles.items()):
        try:
            value = model.data(index, role)
        except (RuntimeError, ReferenceError, TypeError, ValueError, AttributeError) as error:
            lines.append("  {}: <error {}>".format(role_name, error))
            continue
        if value is not None and value != "":
            lines.append("  {} [{}]: {}".format(
                role_name, role, _ReadQtShort(value)))


def _ReadQtModelReport(view, lines, entry=None):
    model = view.model()
    if model is None:
        lines.append("No model attached")
        return
    lines.append("\n--- Qt Model ---")
    _ReadQtObjectReport(model, lines)
    if isinstance(model, QtCore.QAbstractProxyModel):
        source_model = model.sourceModel()
        if source_model is not None:
            lines.append("\n--- Proxy source model ---")
            _ReadQtObjectReport(source_model, lines)
    roles = _ReadQtRoleMap(model)
    lines.append("Roles available for inspection: {}".format(
        ", ".join("{}={}".format(key, name) for key, name in sorted(roles.items()))))
    selected_index = None
    path = entry.get("path") if entry else None
    if path is not None:
        # Resolve a fresh QModelIndex rather than retaining potentially stale Qt handles.
        parent = QtCore.QModelIndex()
        for row in path:
            selected_index = model.index(int(row), 0, parent)
            if not selected_index.isValid():
                break
            parent = selected_index
        lines.append("Selected Research row path: {}".format(path))
    else:
        selected_index = view.currentIndex()
        if not selected_index.isValid():
            chosen = view.selectedIndexes()
            if chosen:
                selected_index = chosen[0]
    if selected_index is not None and selected_index.isValid():
        # Row may have multiple columns; report them all, with limits.
        parent = selected_index.parent()
        for col in range(min(model.columnCount(parent), 8)):
            index = model.index(selected_index.row(), col, parent)
            _ReadQtIndexReport(model, index, lines, "Selected column {}".format(col), roles)
    else:
        lines.append("No valid selected model row. Showing first few root items.")
        for row in range(min(model.rowCount(), 5)):
            _ReadQtIndexReport(model, model.index(row, 0), lines,
                               "Root row {}".format(row), roles)


def ReadUIData(*args):
    """Read selected NLTA Research widget/model item, present a copyable report."""
    item = UI.get("tree").currentItem() if UI.get("tree") else None
    if item is None:
        cmds.warning("Read: Select a widget or Model Item in UI Explorer first.")
        return
    widget = item.data(0, QtCore.Qt.UserRole)
    entry = item.data(0, QtCore.Qt.UserRole + 1)
    if widget is None:
        return
    try:
        lines = ["NLTA RESEARCH - QT DATA READ (read only)",
                 "Selected: {} / {}".format(item.text(0), item.text(1)),
                 "Display: {}".format(item.data(2, QtCore.Qt.UserRole) or item.text(2)),
                 ""]
        _ReadQtObjectReport(widget, lines)
        if isinstance(widget, QtWidgets.QAbstractItemView):
            _ReadQtModelReport(widget, lines, entry)
        if isinstance(widget, QtWidgets.QWidget):
            lines.append("\n--- Visible text descendants (up to 80) ---")
            count = 0
            for child in widget.findChildren(QtWidgets.QWidget):
                if count >= 80:
                    break
                if isinstance(child, QtWidgets.QLineEdit):
                    # Never inspect hidden/password input contents.
                    if child.echoMode() == QtWidgets.QLineEdit.Password:
                        continue
                content = GetUIDisplay(child)
                if content:
                    count += 1
                    lines.append("{} [{}]: {}".format(
                        child.objectName() or "(Unnamed)",
                        child.metaObject().className(),
                        _ReadQtShort(content)))
        report = "\n".join(lines)
    except (RuntimeError, ReferenceError, AttributeError, ValueError, TypeError) as error:
        cmds.warning("Read failed: {}".format(error))
        return

    dialog = QtWidgets.QDialog(UI.get("widget"))
    dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    dialog.setWindowTitle("NLTA Research / Read Qt Data")
    dialog.resize(900, 640)
    layout = QtWidgets.QVBoxLayout(dialog)
    field = QtWidgets.QPlainTextEdit(dialog)
    field.setReadOnly(True)
    field.setPlainText(report)
    layout.addWidget(field)
    controls = QtWidgets.QHBoxLayout()
    copy = QtWidgets.QPushButton("Copy Report", dialog)
    close = QtWidgets.QPushButton("Close", dialog)
    copy.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(report))
    close.clicked.connect(dialog.close)
    controls.addWidget(copy)
    controls.addWidget(close)
    layout.addLayout(controls)
    dialog.show()
    UI["readDialog"] = dialog
    return report


def ClearDetail():
    for key in ("name", "type", "showText", "windowName", "parentName",
                "module", "moduleFile", "rootPath"):
        field = UI.get(key)
        if field is not None:
            field.clear()


def LoadHierarchy(*args):
    tree = UI["tree"]
    tree.clear()
    ClearDetail()
    UI["sourceResults"].clear()
    UI["sourceMatches"] = []
    UI["originalModule"] = ""

    window = UI["window"].currentData()
    if window is None:
        return

    def AddWidget(widget, parentItem=None):
        try:
            name = widget.objectName() or "(Unnamed)"
            widgetType = widget.metaObject().className()
            display = str(GetUIDisplay(widget)).replace("\n", " ")
            values = [name, widgetType, display[:150]]
            item = QtWidgets.QTreeWidgetItem(
                tree if parentItem is None else parentItem, values
            )
            item.setData(0, QtCore.Qt.UserRole, widget)
            item.setData(2, QtCore.Qt.UserRole, display)

            # Model rows / tab titles / graphics text are NOT QWidget children.
            # Show them as research-only entries under their owning QWidget.
            for entry in GetQtDataEntries(widget):
                childItem = QtWidgets.QTreeWidgetItem(item, [
                    entry["name"], entry["type"],
                    entry["text"].replace("\n", " ")[:150]
                ])
                childItem.setData(0, QtCore.Qt.UserRole, widget)
                childItem.setData(0, QtCore.Qt.UserRole + 1, entry)
                childItem.setData(2, QtCore.Qt.UserRole, entry["text"])

            for child in widget.children():
                if isinstance(child, QtWidgets.QWidget):
                    AddWidget(child, item)
        except (RuntimeError, ReferenceError, TypeError):
            return

    AddWidget(window)
    tree.expandToDepth(1)
    FindUI()


def FindUI(*args):
    """Filter the existing UI tree using literal Name / Show Text."""
    tree = UI.get("tree")
    search = UI.get("search")
    typeFilter = UI.get("typeFilter")
    if tree is None or search is None or typeFilter is None:
        return

    # Quotes are literal. Never evaluate or parse the user's search string.
    keyword = search.text().strip().casefold()
    selectedType = typeFilter.currentText()
    typeMap = {
        "Button": (QtWidgets.QPushButton, QtWidgets.QToolButton),
        "Input": (QtWidgets.QLineEdit, QtWidgets.QTextEdit,
                  QtWidgets.QPlainTextEdit, QtWidgets.QSpinBox,
                  QtWidgets.QDoubleSpinBox),
        "ComboBox": (QtWidgets.QComboBox,),
        "CheckBox": (QtWidgets.QCheckBox,),
        "RadioButton": (QtWidgets.QRadioButton,),
        "Label": (QtWidgets.QLabel,),
    }

    def MatchType(widget):
        if selectedType == "All Widgets":
            return True
        if widget is None:
            return False
        try:
            if selectedType == "Layout":
                return (isinstance(widget, QtWidgets.QWidget) and
                        any(isinstance(child, QtWidgets.QWidget)
                            for child in widget.children()))
            if selectedType == "Other":
                return not any(isinstance(widget, classes)
                               for classes in typeMap.values())
            return isinstance(widget, typeMap.get(selectedType, ()))
        except (RuntimeError, ReferenceError):
            # Window was closed/rebuilt; its Qt wrapper may be invalid.
            return False

    def FilterItem(item):
        # Use the cached tree text, not widget.text(), so the filter
        # never calls a potentially deleted widget just to search text.
        try:
            name = item.text(0).casefold()
            display = str(item.data(2, QtCore.Qt.UserRole) or item.text(2)).casefold()
            widget = item.data(0, QtCore.Qt.UserRole)
            matched = (not keyword or keyword in name or keyword in display)
            matched = matched and MatchType(widget)

            childMatch = False
            for i in range(item.childCount()):
                if FilterItem(item.child(i)):
                    childMatch = True

            visible = matched or childMatch
            item.setHidden(not visible)
            if childMatch and (keyword or selectedType != "All Widgets"):
                item.setExpanded(True)
            return visible
        except (RuntimeError, ReferenceError):
            return False

    tree.setUpdatesEnabled(False)
    try:
        for i in range(tree.topLevelItemCount()):
            FilterItem(tree.topLevelItem(i))
    finally:
        tree.setUpdatesEnabled(True)


def GetRootPath(moduleFile):
    if not moduleFile:
        return ""
    try:
        modulePath = Path(moduleFile).resolve()
    except (OSError, ValueError):
        return ""
    matches = []
    for path in sys.path:
        try:
            root = Path(path or os.getcwd()).resolve()
            if root.is_dir():
                modulePath.relative_to(root)
                matches.append(root)
        except (ValueError, OSError):
            continue
    return str(max(matches, key=lambda p: len(p.parts))) if matches else ""


def InspectUI(*args):
    global UI
    for key in ("showText", "windowName", "module", "moduleFile", "rootPath"):
        UI[key].clear()

    item = UI["tree"].currentItem()
    if item is None:
        return
    widget = item.data(0, QtCore.Qt.UserRole)
    if widget is None:
        return

    try:
        extra = item.data(0, QtCore.Qt.UserRole + 1)
        window = widget.window()
        moduleName = type(widget).__module__
        moduleObj = sys.modules.get(moduleName)
        moduleFile = getattr(moduleObj, "__file__", "") or "" if moduleObj else ""

        # Generic PySide widgets are often owned by a Python custom widget.
        # Use the nearest owning Python subclass to locate the source module.
        if not moduleFile or moduleName.startswith(("PySide", "shiboken")):
            owner = widget.parentWidget()
            while owner is not None:
                candidateName = type(owner).__module__
                candidateModule = sys.modules.get(candidateName)
                candidateFile = (getattr(candidateModule, "__file__", "") or ""
                                 if candidateModule else "")
                if (candidateFile and os.path.isfile(candidateFile) and
                        not candidateName.startswith(("PySide", "shiboken"))):
                    moduleName, moduleFile = candidateName, candidateFile
                    break
                owner = owner.parentWidget()

        UI["originalModule"] = moduleName
        values = {
            "showText": extra["text"] if extra else str(GetUIDisplay(widget)),
            "windowName": window.windowTitle() if window else "",
            "module": moduleName,
            "moduleFile": moduleFile,
            "rootPath": GetRootPath(moduleFile)
        }
        for key, value in values.items():
            UI[key].setText(str(value))
    except (RuntimeError, ReferenceError, AttributeError, TypeError) as error:
        cmds.warning("InspectUI failed: {}".format(error))


def FindSource(*args):
    rootPath = UI["rootPath"].text().strip()
    showText = UI["showText"].text().strip()
    tree = UI["sourceResults"]
    tree.clear()
    UI["sourceMatches"] = []

    if not os.path.isdir(rootPath):
        cmds.warning("FindSource: Invalid Root Path.")
        return []
    if not showText:
        cmds.warning("FindSource: Show Text is empty.")
        return []

    keyword = showText.encode("utf-8")  # case-sensitive bytes search
    matches = []
    scanned = skipped = 0
    skipFolders = {".git", ".svn", ".idea", ".vs", "__pycache__", "node_modules"}

    for folder, dirs, files in os.walk(rootPath):
        dirs[:] = [d for d in dirs if d.casefold() not in skipFolders
                   and not os.path.islink(os.path.join(folder, d))]
        for filename in files:
            path = os.path.join(folder, filename)
            if os.path.islink(path):
                skipped += 1
                continue
            try:
                with open(path, "rb") as stream:
                    scanned += 1
                    for lineNumber, rawLine in enumerate(stream, 1):
                        if keyword not in rawLine:
                            continue
                        binary = b"\x00" in rawLine
                        matches.append({
                            "file": path,
                            "line": None if binary else lineNumber,
                            "text": ("FOUND IN BINARY" if binary else
                                     rawLine.decode("utf-8", errors="replace").strip())
                        })
                        if binary:
                            break
            except (OSError, ValueError):
                skipped += 1

    UI["sourceMatches"] = matches
    # Temporarily suspend UI repaints while loading large result sets.
    tree.setUpdatesEnabled(False)
    try:
        for match in matches:
            path, line, content = match["file"], match["line"], match["text"]
            item = QtWidgets.QTreeWidgetItem(tree, [
                os.path.basename(path),
                str(line) if line is not None else "Binary",
                content[:300]
            ])
            item.setData(0, QtCore.Qt.UserRole, match)
            item.setToolTip(0, path)
            item.setToolTip(2, content)
    finally:
        tree.setUpdatesEnabled(True)

    matchedFiles = len({item["file"] for item in matches})
    print("FindSource: {} matches across {} files (scanned {}, skipped {})".format(
        len(matches), matchedFiles, scanned, skipped
    ))
    return matches


def OpenModuleFolder(*args):
    import subprocess
    moduleFile = UI["moduleFile"].text().strip()
    if not os.path.isfile(moduleFile):
        cmds.warning("Module File not found: {}".format(moduleFile))
        return
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(moduleFile)])
    else:
        cmds.warning("Open Module Folder currently supports Windows Explorer only.")


def OpenSourceResult(item, column):
    match = item.data(0, QtCore.Qt.UserRole)
    if not match:
        return
    path, line = match["file"], match["line"]
    if not os.path.isfile(path):
        cmds.warning("Source file not found: {}".format(path))
        return
    try:
        NLTA_General.OpenSublime("{}:{}".format(path, line) if line else path)
    except Exception as error:
        cmds.warning("Cannot open source: {}".format(error))


def UpdateModuleFile(*args):
    import sys
    import importlib.machinery
    moduleName = UI["module"].text().strip()
    if moduleName.startswith(("from ", "import ")):
        return  # Import statements are resolved by Locate Import
    UI["moduleFile"].clear()
    if not moduleName:
        return
    # Module already loaded
    moduleObj = sys.modules.get(moduleName)
    moduleFile = getattr(moduleObj, "__file__", "") if moduleObj else ""
    # Resolve without importing customer code
    if not moduleFile:
        try:
            paths = None
            fullname = ""
            for part in moduleName.split("."):
                fullname = part if not fullname else fullname + "." + part
                loaded = sys.modules.get(fullname)
                if loaded is not None and hasattr(loaded, "__path__"):
                    paths = list(loaded.__path__)
                    continue
                spec = importlib.machinery.PathFinder.find_spec(
                    fullname, paths
                )

                if spec is None:
                    break

                if fullname == moduleName:
                    moduleFile = spec.origin or ""

                paths = list(spec.submodule_search_locations or [])

        except (ImportError, ValueError, AttributeError, TypeError):
            pass

    if moduleFile in ("built-in", "frozen"):
        moduleFile = ""

    UI["moduleFile"].setText(moduleFile or "")



def LocateImport(*args):
    """Resolve 'from ..package import SYMBOL' without executing customer code.

    Uses the last selected widget's original module as the relative-import anchor.
    Keeps Root Path unchanged; results are candidates from static source analysis.
    """
    raw = UI["module"].text().strip()
    baseModule = UI.get("originalModule", "")
    resultTree = UI["sourceResults"]
    resultTree.clear()
    UI["sourceMatches"] = []

    try:
        parsed = ast.parse(raw)
        if len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.ImportFrom):
            cmds.warning("Locate Import: enter 'from ... import NAME'.")
            return []
        statement = parsed.body[0]
    except SyntaxError as error:
        cmds.warning("Locate Import: invalid statement: {}".format(error))
        return []

    if not statement.names or any(a.name == "*" for a in statement.names):
        cmds.warning("Locate Import: specify one or more explicit names.")
        return []

    if statement.level:
        if not baseModule:
            cmds.warning("Locate Import: select a UI first to anchor relative imports.")
            return []
        baseObj = sys.modules.get(baseModule)
        package = baseModule if getattr(baseObj, "__path__", None) is not None else baseModule.rpartition(".")[0]
        try:
            moduleName = importlib.util.resolve_name(
                "." * statement.level + (statement.module or ""), package
            )
        except (ImportError, ValueError) as error:
            cmds.warning("Locate Import: {}".format(error))
            return []
    else:
        moduleName = statement.module or ""

    if not moduleName:
        cmds.warning("Locate Import: module name not found.")
        return []

    def find_module(fullname):
        """Return (file, package_paths) from sys.modules/PathFinder, no import."""
        paths = None
        current = ""
        final_file = ""
        for segment in fullname.split("."):
            current = segment if not current else current + "." + segment
            loaded = sys.modules.get(current)
            if loaded is not None:
                loaded_file = getattr(loaded, "__file__", None)
                loaded_paths = getattr(loaded, "__path__", None)
                if loaded_file or loaded_paths is not None:
                    final_file = loaded_file or ""
                    paths = list(loaded_paths) if loaded_paths is not None else None
                    continue
            spec = importlib.machinery.PathFinder.find_spec(current, paths)
            if spec is None:
                return "", None
            final_file = spec.origin or ""
            paths = list(spec.submodule_search_locations) if spec.submodule_search_locations is not None else None
        return final_file, paths

    def definitions(module, symbol, seen=None, depth=0):
        """Return candidate file/line definitions, including simple re-exports."""
        seen = set() if seen is None else seen
        key = (module, symbol)
        if key in seen or depth > 6:
            return []
        seen.add(key)
        file, pkg_paths = find_module(module)
        found = []
        if file and Path(file).suffix.lower() == ".py" and os.path.isfile(file):
            try:
                code = Path(file).read_text(encoding="utf-8-sig", errors="replace")
                tree = ast.parse(code, filename=file)
            except (OSError, SyntaxError, UnicodeError):
                tree = None
            if tree is not None:
                for node in tree.body:
                    match = False
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        match = node.name == symbol
                    elif isinstance(node, ast.Assign):
                        match = any(isinstance(t, ast.Name) and t.id == symbol for t in node.targets)
                    elif isinstance(node, ast.AnnAssign):
                        match = isinstance(node.target, ast.Name) and node.target.id == symbol
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            if (alias.asname or alias.name) != symbol:
                                continue
                            package = module if Path(file).name == "__init__.py" else module.rpartition(".")[0]
                            try:
                                origin = (importlib.util.resolve_name(
                                    "." * node.level + (node.module or ""), package
                                ) if node.level else node.module or "")
                                if origin:
                                    found.extend(definitions(origin, alias.name, seen, depth + 1))
                            except (ImportError, ValueError):
                                pass
                            match = True
                    elif isinstance(node, ast.Import):
                        match = any((a.asname or a.name.split(".")[0]) == symbol for a in node.names)
                    if match:
                        found.append({
                            "file": file, "line": node.lineno,
                            "text": (ast.get_source_segment(code, node) or symbol).splitlines()[0],
                            "status": "candidate"
                        })
        # 'from package import symbol' may refer to package/symbol.py
        if pkg_paths:
            subfile, _ = find_module(module + "." + symbol)
            if subfile and os.path.isfile(subfile):
                found.append({"file": subfile, "line": 1,
                              "text": "Submodule {}.{}".format(module, symbol),
                              "status": "candidate"})
        return found

    try:
        moduleFile, _ = find_module(moduleName)
        if moduleFile and os.path.isfile(moduleFile):
            UI["moduleFile"].setText(moduleFile)
        else:
            UI["moduleFile"].clear()
        # Root Path intentionally stays unchanged.
        matches = []
        for alias in statement.names:
            matches.extend(definitions(moduleName, alias.name))
    except (ImportError, AttributeError, TypeError, ValueError, OSError) as error:
        cmds.warning("Locate Import failed: {}".format(error))
        return []

    unique = []
    seen_matches = set()
    for match in matches:
        key = (match["file"], match["line"], match["text"])
        if key not in seen_matches:
            seen_matches.add(key)
            unique.append(match)
    UI["sourceMatches"] = unique
    for match in unique:
        item = QtWidgets.QTreeWidgetItem(resultTree, [
            os.path.basename(match["file"]), str(match["line"]), match["text"][:300]
        ])
        item.setData(0, QtCore.Qt.UserRole, match)
        item.setToolTip(0, match["file"])
    if not unique:
        cmds.warning("Locate Import: module found or checked, but no static definition identified.")
    return unique

# ============================================================
# UI CODE GENERATOR / SCRIPT WORKSPACE
# ============================================================

def ResearchDataDirectory():
    # <root>/<Research parent>/Research.py -> <root>/Data/Research
    return Path(__file__).resolve().parent.parent / "Data" / "Research"


def ScriptRegistryPath():
    return ResearchDataDirectory() / "script_files.json"


def LoadScriptRegistry():
    path = ScriptRegistryPath()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, str)]
    except (OSError, ValueError, UnicodeError) as error:
        cmds.warning("Cannot read Research script registry: {}".format(error))
    return []


def RegisterScript(path):
    path = str(Path(path).resolve())
    registry = LoadScriptRegistry()
    if path not in registry:
        registry.append(path)
        folder = ResearchDataDirectory()
        folder.mkdir(parents=True, exist_ok=True)
        file = ScriptRegistryPath()
        temporary = file.with_suffix(".tmp")
        temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(file)


def WidgetKind(widget):
    if isinstance(widget, QtWidgets.QLineEdit):
        return "QLineEdit"
    if isinstance(widget, QtWidgets.QTextEdit):
        return "QTextEdit"
    if isinstance(widget, QtWidgets.QPlainTextEdit):
        return "QPlainTextEdit"
    if isinstance(widget, QtWidgets.QComboBox):
        return "QComboBox"
    if isinstance(widget, QtWidgets.QCheckBox):
        return "QCheckBox"
    if isinstance(widget, QtWidgets.QRadioButton):
        return "QRadioButton"
    if isinstance(widget, QtWidgets.QAbstractButton):
        return "QAbstractButton"
    if isinstance(widget, QtWidgets.QLabel):
        return "QLabel"
    if isinstance(widget, QtWidgets.QAbstractSpinBox):
        return "QAbstractSpinBox"
    return "QWidget"


def AdjacentLabel(widget):
    """Best-effort label: buddy, form layout or preceding widget.
    Never claim an ambiguous relationship is certain.
    """
    parent = widget.parentWidget()
    if parent is None:
        return None
    try:
        labels = [w for w in parent.findChildren(QtWidgets.QLabel)
                  if w.buddy() is widget]
        if len(labels) == 1:
            return labels[0]
        layout = parent.layout()
        if isinstance(layout, QtWidgets.QFormLayout):
            for row in range(layout.rowCount()):
                field = layout.itemAt(row, QtWidgets.QFormLayout.FieldRole)
                label = layout.itemAt(row, QtWidgets.QFormLayout.LabelRole)
                if field and field.widget() is widget and label and label.widget():
                    return label.widget()
        if layout:
            for i in range(layout.count()):
                part = layout.itemAt(i)
                if part and part.widget() is widget and i > 0:
                    before = layout.itemAt(i - 1)
                    if before and before.widget():
                        return before.widget()
        siblings = [w for w in parent.children() if isinstance(w, QtWidgets.QWidget)]
        if widget in siblings and siblings.index(widget) > 0:
            return siblings[siblings.index(widget) - 1]
    except (RuntimeError, AttributeError, TypeError):
        pass
    return None


def UpdateGeneratorFromSelection(*args):
    fields = ("genPrevType", "genPrevShow", "genTargetType", "genTargetShow")
    if not all(UI.get(k) is not None for k in fields):
        return
    item = UI["tree"].currentItem()
    target = item.data(0, QtCore.Qt.UserRole) if item else None
    for key in fields:
        UI[key].clear()
    if target is None:
        return
    # Model items, tabs and graphics items are snapshots, NOT QWidget targets.
    # Keep the existing Qt-code generator from generating a false locator.
    if item.data(0, QtCore.Qt.UserRole + 1):
        return
    try:
        previous = AdjacentLabel(target)
        UI["genPrevType"].setText(WidgetKind(previous) if previous else "")
        UI["genPrevShow"].setText(str(GetUIDisplay(previous)) if previous else "")
        UI["genTargetType"].setText(WidgetKind(target))
        UI["genTargetShow"].setText(str(GetUIDisplay(target)))
        if isinstance(target, QtWidgets.QAbstractButton):
            UI["genAction"].setCurrentText("Click")
        else:
            UI["genAction"].setCurrentText("Fill")
    except (RuntimeError, TypeError):
        pass


HELPER_FILENAME = "ResearchUIHelper.py"


def HelperSourcePath():
    # Source helper ships alongside Research.py; fallback to a known installed copy.
    return Path(__file__).resolve().with_name(HELPER_FILENAME)


def InstallScriptHelper(script_path):
    """Copy helper alongside the script; never silently overwrite existing helper."""
    source = HelperSourcePath()
    destination = Path(script_path).resolve().parent / HELPER_FILENAME
    if not source.is_file():
        raise RuntimeError("Missing helper next to Research.py: {}".format(source))
    if source.resolve() != destination.resolve() and not destination.exists():
        shutil.copy2(str(source), str(destination))
    return destination

def GenerateDoubleClickCode(params):
    """Generate self-contained, safe Qt Double Click code.

    Try the existing exact locator first.  When it fails with 0 candidates,
    resolve a subclass of the selected Qt type near the previous QLabel.
    Do not guess if a label/target is ambiguous.
    """
    locate_code = """_research_find = dict(\n{}\n)
_result_error = None
try:
    result = ResearchUIHelper.locate(**_research_find)
except RuntimeError as error:
    # A zero-candidate or multi-candidate result needs a safer Qt fallback.
    if 'candidate' not in str(error).lower():
        raise
    _result_error = str(error)
    result = None
""".format("\n".join(params))

    fallback_code = """
try:
    from PySide6 import QtCore, QtWidgets, QtTest
except ImportError:
    from PySide2 import QtCore, QtWidgets, QtTest


def _research_norm(value):
    return ' '.join(str(value or '').replace('&', '').strip().casefold().split())


def _research_display(widget):
    for name in ('text', 'title', 'windowTitle', 'placeholderText'):
        method = getattr(widget, name, None)
        if callable(method):
            try:
                value = method()
                if value:
                    return str(value)
            except (RuntimeError, TypeError):
                pass
    return ''


def _research_ancestry(widget):
    result = []
    current = widget
    while current is not None:
        result.append(current)
        current = current.parentWidget()
    return result


def _research_center_distance(first, second):
    point1 = first.mapToGlobal(first.rect().center())
    point2 = second.mapToGlobal(second.rect().center())
    return abs(point1.x() - point2.x()) + abs(point1.y() - point2.y())


def _research_window_match(actual, desired):
    a = _research_norm(actual)
    b = _research_norm(desired)
    if a == b:
        return True
    # Maya appends [*] for a dirty scene and changes its file/title suffix.
    strip_dirty = lambda s: s.replace('[*]', '')
    a, b = strip_dirty(a), strip_dirty(b)
    if a == b:
        return True
    # Compare scene name, not a generic "Autodesk Maya" prefix.
    a_scene = a.split(' - autodesk maya', 1)[0]
    b_scene = b.split(' - autodesk maya', 1)[0]
    return bool(a_scene and b_scene and a_scene == b_scene)


def _research_resolve(params):
    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError('Double Click: QApplication not running')
    title = params.get('window_title', '')
    windows = [w for w in app.topLevelWidgets()
               if w.isVisible() and _research_window_match(w.windowTitle(), title)]
    if not windows:
        titles = [w.windowTitle() for w in app.topLevelWidgets() if w.isVisible()]
        raise RuntimeError('Double Click: Window not found: {!r}. Visible windows: {!r}'.format(
            title, titles[:10]))
    if len(windows) != 1:
        raise RuntimeError('Double Click: {} matching windows; refine Window title'.format(len(windows)))
    root = windows[0]
    target_type = params.get('target_type') or 'QWidget'
    parent_type = params.get('previous_type') or 'QLabel'
    target_cls = getattr(QtWidgets, target_type, None)
    previous_cls = getattr(QtWidgets, parent_type, None)
    if target_cls is None or previous_cls is None:
        raise RuntimeError('Double Click: Unknown Qt class: {} / {}'.format(target_type, parent_type))
    target_text = _research_norm(params.get('target_show'))
    previous_text = _research_norm(params.get('previous_show'))

    def acceptable(widget, klass, desired):
        if not isinstance(widget, klass) or not widget.isVisible() or not widget.isEnabled():
            return False
        return not desired or _research_norm(_research_display(widget)) == desired

    all_widgets = [root] + root.findChildren(QtWidgets.QWidget)
    targets = [w for w in all_widgets if acceptable(w, target_cls, target_text)]
    if not targets:
        raise RuntimeError('Double Click: No visible {} with Show={!r}'.format(
            target_type, params.get('target_show')))

    if previous_text:
        labels = [w for w in all_widgets if acceptable(w, previous_cls, previous_text)]
        if len(labels) != 1:
            raise RuntimeError('Double Click: expected 1 previous {} {!r}, found {}. '
                               'Specify a more precise label/window.'.format(
                                   parent_type, params.get('previous_show'), len(labels)))
        label = labels[0]
        ancestors = _research_ancestry(label)

        def relation(target):
            chain = _research_ancestry(target)
            # Minimize hops from label to button in the widget hierarchy.
            common = [a for a in ancestors if a in chain]
            if not common:
                return (9999, 9999)
            a = common[0]
            return (ancestors.index(a) + chain.index(a),
                    _research_center_distance(label, target))

        ranked = sorted(((relation(w), i, w) for i, w in enumerate(targets)),
                        key=lambda entry: entry[0])
        best_score, _, best = ranked[0]
        # Require structural proximity (same row or at most a few nested groups).
        if best_score[0] > 4:
            raise RuntimeError('Double Click: found label but no nearby {}. '
                               'Check selected target class and Previous Show.'.format(target_type))
        if len(ranked) > 1:
            second_score = ranked[1][0]
            if second_score[0] == best_score[0] and second_score[1] - best_score[1] < 12:
                raise RuntimeError('Double Click: {} equally close buttons near {!r}; '
                                   'specify Target Show or objectName'.format(
                                       len(targets), params.get('previous_show')))
        return best

    if len(targets) != 1:
        raise RuntimeError('Double Click: {} {} candidates without an anchor; '
                           'specify Target Show / Previous Show'.format(len(targets), target_type))
    return targets[0]


if result is None:
    result = _research_resolve(_research_find)
if result is None:
    raise RuntimeError('Double Click: Target widget was not found')

# A real mouse-double-click event; do not simulate by clicking twice.
widget = result
if isinstance(widget, QtWidgets.QAbstractItemView):
    target = widget.viewport()
    index = widget.currentIndex()
    if not index.isValid():
        selected = widget.selectedIndexes()
        if selected:
            index = selected[0]
    if not index.isValid():
        raise RuntimeError('Double Click: Select an item in the target view first')
    position = widget.visualRect(index).center()
elif isinstance(widget, QtWidgets.QGraphicsView):
    target = widget.viewport()
    position = target.rect().center()
else:
    target = widget
    position = target.rect().center()
if not target.isVisible() or not target.isEnabled():
    raise RuntimeError('Double Click: Target widget is hidden or disabled')
QtTest.QTest.mouseDClick(target, QtCore.Qt.LeftButton, pos=position)
"""
    return locate_code + fallback_code


def GenerateUICode(*args):
    """Generate code using ResearchUIHelper without importing again."""

    windowTitle = UI["windowName"].text().strip()
    prevType = UI["genPrevType"].text().strip()
    prevShow = UI["genPrevShow"].text()
    targetType = UI["genTargetType"].text().strip()
    targetShow = UI["genTargetShow"].text()

    mode = UI["genMode"].currentText()
    action = UI["genAction"].currentText()

    if not windowTitle or not targetType:
        cmds.warning("Get Code: select a UI with Window and Target Type first.")
        return

    if not targetShow and not prevShow:
        cmds.warning("Get Code: enter Target Show or Previous Show.")
        return

    # Select helper method
    method = "locate" if mode == "Get Widget" else "interact"
    # Widget identification parameters
    params = [
        "    window_title={!r},".format(windowTitle),
        "    target_type={!r},".format(targetType),
        "    target_show={!r},".format(targetShow),
        "    previous_type={!r},".format(prevType),
        "    previous_show={!r},".format(prevShow),
    ]

    # Double Click uses Qt's native mouse-double-click event, because older
    # ResearchUIHelper.interact() versions do not implement this action.
    if method == "interact" and action == "Double Click":
        source = GenerateDoubleClickCode(params)
    else:
        if method == "interact":
            value = "Example" if action == "Fill" else None
            params.extend([
                "    action={!r},".format(action),
                "    value={!r},".format(value),
            ])
        source = "result = ResearchUIHelper.{}(\n{}\n)\n".format(
            method, "\n".join(params))
    UI["generatedCode"].setPlainText(source)
    print("NLTA Research: generated {} code.".format(mode))
    return source

def UpdateGeneratorMode(*args):
    """Action selector is irrelevant when returning the QWidget itself."""
    UI["genAction"].setEnabled(UI["genMode"].currentText() == "Get Action")

def CopyGeneratedCode(*args):
    QtWidgets.QApplication.clipboard().setText(UI["generatedCode"].toPlainText())


def RefreshScriptFiles(*args):
    listing = UI["scriptFiles"]
    listing.clear()
    for filename in LoadScriptRegistry():
        path = Path(filename)
        item = QtWidgets.QListWidgetItem(path.name)
        item.setData(QtCore.Qt.UserRole, str(path))
        item.setToolTip(str(path))
        if not path.is_file():
            item.setText("[Missing] " + path.name)
            item.setForeground(QtCore.Qt.gray)
        listing.addItem(item)


def BrowseScriptPath(dialog=None, *args):
    """Choose a destination; Save uses the path shown in scriptPath."""
    if dialog is None:
        dialog = UI.get("scriptDialog")
    if dialog is None:
        return
    current = dialog.scriptPath.text().strip()
    name = dialog.scriptName.text().strip() or "new_script.py"
    initial = current or str(Path.home() / name)
    chosen, _ = QtWidgets.QFileDialog.getSaveFileName(
        dialog, "Choose Python Script Location", initial, "Python Script (*.py)"
    )
    if chosen:
        dest = Path(chosen).expanduser()
        if dest.suffix.lower() != ".py":
            dest = dest.with_suffix(".py")
        dialog.scriptPath.setText(str(dest))
        dialog.scriptName.setText(dest.name)


def OpenScriptLocation(dialog=None, *args):
    import subprocess
    if dialog is None:
        dialog = UI.get("scriptDialog")
    if dialog is None:
        return
    entered = dialog.scriptPath.text().strip()
    if not entered:
        cmds.warning("Set the script path first.")
        return
    path = Path(entered).expanduser()
    location = path if path.is_dir() else path.parent
    if not location.is_dir():
        cmds.warning("Script folder does not exist: {}".format(location))
        return
    try:
        if os.name == "nt":
            if path.is_file():
                subprocess.Popen(["explorer.exe", "/select,", str(path.resolve())])
            else:
                os.startfile(str(location.resolve()))
        else:
            subprocess.Popen(["xdg-open", str(location.resolve())])
    except (OSError, ValueError) as error:
        cmds.warning("Open Location failed: {}".format(error))


def ScriptEditorDialog(path=None):
    """Independent editor. Save always follows the path input."""
    dialog = UI.get("scriptDialog")
    if dialog is not None and dialog.isVisible():
        if path is not None and str(path) != dialog.currentPath:
            if dialog.scriptEditor.document().isModified():
                reply = QtWidgets.QMessageBox.question(
                    dialog, "Unsaved Changes", "Discard unsaved changes and open another script?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No)
                if reply != QtWidgets.QMessageBox.Yes:
                    return dialog
            dialog.scriptEditor.setPlainText(Path(path).read_text(encoding="utf-8"))
            dialog.scriptName.setText(Path(path).name)
            dialog.scriptPath.setText(str(Path(path).resolve()))
            dialog.currentPath = str(Path(path).resolve())
            dialog.scriptEditor.document().setModified(False)
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    dialog = QtWidgets.QDialog(UI["widget"])
    dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    dialog.setWindowTitle("NLTA / Script File Editor")
    dialog.resize(1000, 700)
    layout = QtWidgets.QVBoxLayout(dialog)

    name = QtWidgets.QLineEdit()
    name.setPlaceholderText("script_name.py")
    layout.addWidget(QtWidgets.QLabel("Script Name"))
    layout.addWidget(name)

    pathRow = QtWidgets.QHBoxLayout()
    scriptPath = QtWidgets.QLineEdit()
    scriptPath.setPlaceholderText("Full script path (.py) — Browse to choose")
    browse = QtWidgets.QPushButton("Browse...")
    location = QtWidgets.QPushButton("Open Location")
    pathRow.addWidget(scriptPath, 1)
    pathRow.addWidget(browse)
    pathRow.addWidget(location)
    layout.addWidget(QtWidgets.QLabel("Script Path (Save destination)"))
    layout.addLayout(pathRow)

    editor = QtWidgets.QPlainTextEdit()
    editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
    layout.addWidget(editor, 1)

    actions = QtWidgets.QHBoxLayout()
    save = QtWidgets.QPushButton("Save")
    saveAs = QtWidgets.QPushButton("Save As...")
    run = QtWidgets.QPushButton("Run in Maya")
    close = QtWidgets.QPushButton("Close")
    for button in (save, saveAs, run, close):
        actions.addWidget(button)
    layout.addLayout(actions)

    dialog.scriptName = name
    dialog.scriptPath = scriptPath
    dialog.scriptEditor = editor
    dialog.currentPath = ""
    UI["scriptDialog"] = dialog

    if path is None:
        name.setText("new_script.py")
        editor.setPlainText("import ResearchUIHelper\n\n# Paste Get Code output here and edit as needed.\n")
    else:
        path = Path(path).resolve()
        editor.setPlainText(path.read_text(encoding="utf-8"))
        name.setText(path.name)
        scriptPath.setText(str(path))
        dialog.currentPath = str(path)
    editor.document().setModified(False)

    browse.clicked.connect(lambda checked=False: BrowseScriptPath(dialog))
    location.clicked.connect(lambda checked=False: OpenScriptLocation(dialog))
    save.clicked.connect(lambda checked=False: SaveScript(dialog))
    saveAs.clicked.connect(lambda checked=False: SaveScriptAs(dialog))
    run.clicked.connect(lambda checked=False: RunScript(dialog))
    close.clicked.connect(dialog.close)
    dialog.finished.connect(lambda result: UI.pop("scriptDialog", None)
                            if UI.get("scriptDialog") is dialog else None)
    dialog.show()
    return dialog


def NewScript(*args):
    existing = UI.get("scriptDialog")
    if existing is not None and existing.isVisible():
        if existing.scriptEditor.document().isModified():
            reply = QtWidgets.QMessageBox.question(
                existing, "Unsaved Changes",
                "Discard unsaved changes and create a new script?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if reply != QtWidgets.QMessageBox.Yes:
                return existing
        existing.scriptName.setText("new_script.py")
        existing.scriptPath.clear()
        existing.scriptEditor.setPlainText(
            "import ResearchUIHelper\n\n# Paste Get Code output here and edit as needed.\n")
        existing.currentPath = ""
        existing.scriptEditor.document().setModified(False)
        existing.raise_()
        existing.activateWindow()
        return existing
    return ScriptEditorDialog()


def SaveScript(dialog=None):
    """Save to the exact path displayed in the editable Script Path field."""
    if dialog is None or isinstance(dialog, bool):
        dialog = UI.get("scriptDialog")
    if dialog is None:
        cmds.warning("Open a Script File Editor first.")
        return False

    entered = dialog.scriptPath.text().strip().strip('"')
    if not entered:
        cmds.warning("Enter Script Path or click Browse before saving.")
        return False
    path = Path(entered).expanduser()
    if not path.is_absolute():
        cmds.warning("Script Path must be an absolute path.")
        return False
    if path.suffix.lower() != ".py":
        cmds.warning("Script Path must end with .py")
        return False
    if path.name.casefold() == HELPER_FILENAME.casefold():
        cmds.warning("Choose a script name different from the helper module.")
        return False

    path = path.resolve()
    try:
        code = dialog.scriptEditor.toPlainText()
        compile(code, str(path), "exec")
        path.parent.mkdir(parents=True, exist_ok=True)
        InstallScriptHelper(path)
        path.write_text(code, encoding="utf-8")
        RegisterScript(path)
    except (OSError, SyntaxError, UnicodeError, RuntimeError, ValueError) as error:
        cmds.warning("Save Script failed: {}".format(error))
        return False

    dialog.currentPath = str(path)
    dialog.scriptPath.setText(str(path))
    dialog.scriptName.setText(path.name)
    dialog.scriptEditor.document().setModified(False)
    RefreshScriptFiles()
    print("Saved script:", path)
    return True


def SaveScriptAs(dialog=None):
    """Choose a new path, then save via the same Script Path field."""
    if dialog is None or isinstance(dialog, bool):
        dialog = UI.get("scriptDialog")
    if dialog is None:
        cmds.warning("Open a Script File Editor first.")
        return False
    before = dialog.scriptPath.text()
    BrowseScriptPath(dialog)
    if dialog.scriptPath.text() == before:
        return False
    return SaveScript(dialog)


def OpenScript(*args):
    item = UI["scriptFiles"].currentItem()
    if item is None:
        return
    path = Path(item.data(QtCore.Qt.UserRole))
    if not path.is_file():
        cmds.warning("Saved script no longer exists: {}".format(path))
        return
    try:
        ScriptEditorDialog(path)
    except (OSError, UnicodeError) as error:
        cmds.warning("Open Script failed: {}".format(error))


def RunScript(dialog=None):
    if dialog is None or isinstance(dialog, bool):
        dialog = UI.get("scriptDialog")
    if dialog is None:
        cmds.warning("Open a Script File Editor first.")
        return
    code = dialog.scriptEditor.toPlainText()
    if not code.strip():
        cmds.warning("Script Editor is empty.")
        return
    try:
        source = dialog.currentPath or "<NLTA_Research_Editor>"
        compiled = compile(code, source, "exec")
        # Saved files use their own folder for ResearchUIHelper imports.
        # Unsaved drafts use the helper beside Research.py.
        folder = str(Path(source).resolve().parent) if dialog.currentPath else str(HelperSourcePath().parent)
        original_path = list(sys.path)
        try:
            sys.path.insert(0, folder)
            namespace = {"__name__": "__main__", "__file__": source}
            exec(compiled, namespace, namespace)
        finally:
            sys.path[:] = original_path
        print("NLTA Research: Script execution finished.")
    except Exception:
        import traceback
        traceback.print_exc()
        cmds.warning("Run Script failed. See Script Editor traceback.")


def CreateUI(data):
    global UI
    parent = data["parent"]
    module = data["module"]
    layoutFlags = data.get("layoutFlags", {})

    if cmds.layout(module, exists=True):
        cmds.deleteUI(module)
    UI.clear()

    root = cmds.rowColumnLayout(module, numberOfColumns=1, parent=parent)
    if layoutFlags:
        cmds.rowColumnLayout(root, e=True, **layoutFlags)
    host = cmds.columnLayout(adjustableColumn=True, parent=root)

    widget = QtWidgets.QWidget()
    widget.setObjectName("NLTA_ResearchWidget")
    widget.setMinimumWidth(1350)
    main = QtWidgets.QVBoxLayout(widget)
    main.setContentsMargins(5, 5, 5, 5)
    main.setSpacing(5)

    header = QtWidgets.QHBoxLayout()
    header.addWidget(QtWidgets.QLabel("NLTA / RESEARCH"))
    header.addStretch()
    main.addLayout(header)

    splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
    main.addWidget(splitter)

    left = QtWidgets.QWidget()
    leftLayout = QtWidgets.QVBoxLayout(left)
    leftLayout.setContentsMargins(3, 3, 3, 3)
    leftLayout.addWidget(QtWidgets.QLabel("UI EXPLORER"))

    windowRow = QtWidgets.QHBoxLayout()
    UI["window"] = QtWidgets.QComboBox()
    UI["window"].addItem("Select Window", None)
    UI["reload"] = QtWidgets.QPushButton("Reload")
    UI["reload"].setFixedWidth(60)
    windowRow.addWidget(UI["window"], 1)
    windowRow.addWidget(UI["reload"])
    leftLayout.addLayout(windowRow)

    searchRow = QtWidgets.QHBoxLayout()
    UI["search"] = QtWidgets.QLineEdit()
    UI["search"].setPlaceholderText("Search UI label or name...")
    UI["find"] = QtWidgets.QPushButton("Find")
    UI["find"].setFixedWidth(60)
    searchRow.addWidget(UI["search"], 1)
    searchRow.addWidget(UI["find"])
    leftLayout.addLayout(searchRow)

    UI["typeFilter"] = QtWidgets.QComboBox()
    UI["typeFilter"].addItems([
        "All Widgets", "Button", "Input", "ComboBox", "CheckBox",
        "RadioButton", "Label", "Layout", "Other"
    ])
    leftLayout.addWidget(UI["typeFilter"])

    UI["tree"] = QtWidgets.QTreeWidget()
    UI["tree"].setHeaderLabels(["UI Name", "Type", "Display"])
    UI["tree"].setColumnWidth(0, 220)
    UI["tree"].setColumnWidth(1, 140)
    UI["tree"].setColumnWidth(2, 220)
    UI["tree"].setAlternatingRowColors(True)
    UI["tree"].setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    leftLayout.addWidget(UI["tree"])
    splitter.addWidget(left)

    right = QtWidgets.QWidget()
    rightLayout = QtWidgets.QVBoxLayout(right)
    rightLayout.setContentsMargins(3, 3, 3, 3)
    rightLayout.addWidget(QtWidgets.QLabel("UI INFORMATION"))
    form = QtWidgets.QFormLayout()
    fields = [
        ("Window", "windowName"),
        ("Show Text", "showText"),        
        ("Root Path", "rootPath"),
        ("Class Module", "module"),
        ("Module File", "moduleFile"),        
    ]
    for label, key in fields:
        field = QtWidgets.QLineEdit()
        #field.setReadOnly(key not in {"showText", "rootPath"})
        UI[key] = field
        form.addRow(label, field)
    UI["module"].textChanged.connect(UpdateModuleFile)
    rightLayout.addLayout(form)

    rightLayout.addWidget(QtWidgets.QLabel("ACTIONS"))
    actions = QtWidgets.QGridLayout()
    actionNames = [
        ("Pick UI", "pick", None),
        ("Find Source", "findSource", FindSource),
        ("Locate Import", "locateImport", LocateImport),
        ("Open Module Folder", "openModuleFolder", OpenModuleFolder),
        ("Open Source", "openSource", None),
        ("Read", "read", ReadUIData),
        ("Click", "click", None),
        ("Fill", "fill", None),
        ("Add Workflow", "addWorkflow", None),
        ("Run Workflow", "runWorkflow", None),
    ]
    for i, (label, key, function) in enumerate(actionNames):
        button = QtWidgets.QPushButton(label)
        UI[key] = button
        if function is None:
            button.setEnabled(False)
        else:
            button.clicked.connect(function)
        actions.addWidget(button, i // 2, i % 2)
    rightLayout.addLayout(actions)

    rightLayout.addWidget(QtWidgets.QLabel("SOURCE RESULTS (double-click to open)"))
    UI["sourceResults"] = QtWidgets.QTreeWidget()
    UI["sourceResults"].setHeaderLabels(["File", "Line", "Content"])
    UI["sourceResults"].setColumnWidth(0, 220)
    UI["sourceResults"].setColumnWidth(1, 55)
    UI["sourceResults"].setColumnWidth(2, 300)
    UI["sourceResults"].setAlternatingRowColors(True)
    rightLayout.addWidget(UI["sourceResults"])
    splitter.addWidget(right)

    # THIRD COLUMN - CODE GENERATOR / SCRIPT WORKSPACE
    codePanel = QtWidgets.QWidget()
    codeLayout = QtWidgets.QVBoxLayout(codePanel)
    codeLayout.setContentsMargins(3, 3, 3, 3)
    codeLayout.addWidget(QtWidgets.QLabel("UI CODE GENERATOR"))
    generator = QtWidgets.QFormLayout()
    for label, key in [
        ("Previous Type", "genPrevType"),
        ("Previous Show", "genPrevShow"),
        ("Target Type", "genTargetType"),
        ("Target Show", "genTargetShow"),
    ]:
        field = QtWidgets.QLineEdit()
        UI[key] = field
        generator.addRow(label, field)
    UI["genMode"] = QtWidgets.QComboBox()
    UI["genMode"].addItems(["Get Widget", "Get Action"])
    generator.addRow("Output", UI["genMode"])
    UI["genAction"] = QtWidgets.QComboBox()
    UI["genAction"].addItems([
        "Fill", "Click", "Double Click", "Read", "Check", "Uncheck", "Select", "Set Value"
    ])
    generator.addRow("Action", UI["genAction"])
    UpdateGeneratorMode()
    codeLayout.addLayout(generator)
    UI["getCode"] = QtWidgets.QPushButton("Get Code")
    codeLayout.addWidget(UI["getCode"])

    codeLayout.addWidget(QtWidgets.QLabel("GENERATED CODE (copy into a script file)"))
    UI["generatedCode"] = QtWidgets.QPlainTextEdit()
    UI["generatedCode"].setReadOnly(True)
    UI["generatedCode"].setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
    codeLayout.addWidget(UI["generatedCode"], 2)
    buttons = QtWidgets.QHBoxLayout()
    UI["copyCode"] = QtWidgets.QPushButton("Copy Code")
    UI["newScript"] = QtWidgets.QPushButton("New File (Editor Window)")
    buttons.addWidget(UI["copyCode"])
    buttons.addWidget(UI["newScript"])
    codeLayout.addLayout(buttons)
    filesTitle = QtWidgets.QHBoxLayout()
    filesTitle.addWidget(QtWidgets.QLabel("SAVED PYTHON FILES"))
    UI["refreshScripts"] = QtWidgets.QPushButton("Refresh")
    filesTitle.addWidget(UI["refreshScripts"])
    codeLayout.addLayout(filesTitle)
    UI["scriptFiles"] = QtWidgets.QListWidget()
    codeLayout.addWidget(UI["scriptFiles"], 1)
    UI["openScript"] = QtWidgets.QPushButton("Open Selected File")
    codeLayout.addWidget(UI["openScript"])
    splitter.addWidget(codePanel)
    splitter.setSizes([390, 490, 480])

    UI["widget"] = widget
    UI["root"] = root
    UI["host"] = host
    UI["splitter"] = splitter
    UI["sourceMatches"] = []

    UI["window"].currentIndexChanged.connect(LoadHierarchy)
    UI["reload"].clicked.connect(ReloadWindows)
    UI["search"].returnPressed.connect(FindUI)
    UI["find"].clicked.connect(FindUI)
    UI["typeFilter"].currentIndexChanged.connect(FindUI)
    UI["tree"].currentItemChanged.connect(InspectUI)
    UI["sourceResults"].itemDoubleClicked.connect(OpenSourceResult)
    UI["tree"].currentItemChanged.connect(UpdateGeneratorFromSelection)
    UI["genMode"].currentIndexChanged.connect(UpdateGeneratorMode)
    UI["getCode"].clicked.connect(GenerateUICode)
    UI["newScript"].clicked.connect(NewScript)
    UI["copyCode"].clicked.connect(CopyGeneratedCode)
    UI["refreshScripts"].clicked.connect(RefreshScriptFiles)
    UI["openScript"].clicked.connect(OpenScript)
    UI["scriptFiles"].itemDoubleClicked.connect(OpenScript)

    mayaPointer = omui.MQtUtil.findLayout(host)
    if mayaPointer is None:
        widget.deleteLater()
        raise RuntimeError("Cannot find Maya parent layout")
    qtPointer = int(getCppPointer(widget)[0])
    omui.MQtUtil.addWidgetToMayaLayout(qtPointer, int(mayaPointer))

    ReloadWindows()
    RefreshScriptFiles()
    return root
