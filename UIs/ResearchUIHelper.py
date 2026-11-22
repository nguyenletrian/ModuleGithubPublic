"""Reusable Qt UI lookup/actions for NLTA Research generated scripts.
No Maya dependency. No automatic action on import.
"""
try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets


def widget_kind(widget):
    if isinstance(widget, QtWidgets.QLineEdit): return "QLineEdit"
    if isinstance(widget, QtWidgets.QTextEdit): return "QTextEdit"
    if isinstance(widget, QtWidgets.QPlainTextEdit): return "QPlainTextEdit"
    if isinstance(widget, QtWidgets.QComboBox): return "QComboBox"
    if isinstance(widget, QtWidgets.QCheckBox): return "QCheckBox"
    if isinstance(widget, QtWidgets.QRadioButton): return "QRadioButton"
    if isinstance(widget, QtWidgets.QAbstractButton): return "QAbstractButton"
    if isinstance(widget, QtWidgets.QLabel): return "QLabel"
    if isinstance(widget, QtWidgets.QAbstractSpinBox): return "QAbstractSpinBox"
    return "QWidget"


def widget_show(widget):
    if isinstance(widget, QtWidgets.QLineEdit):
        return widget.placeholderText() or widget.text()
    if isinstance(widget, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
        return widget.placeholderText() or widget.toPlainText()
    if isinstance(widget, QtWidgets.QComboBox): return widget.currentText()
    if isinstance(widget, QtWidgets.QAbstractButton): return widget.text()
    if isinstance(widget, QtWidgets.QLabel): return widget.text()
    if isinstance(widget, QtWidgets.QGroupBox): return widget.title()
    if isinstance(widget, QtWidgets.QAbstractSpinBox): return widget.text()
    return widget.windowTitle()


def preceding(widget):
    parent = widget.parentWidget()
    if parent is None: return []
    results = []
    results.extend(w for w in parent.findChildren(QtWidgets.QLabel) if w.buddy() is widget)
    layout = parent.layout()
    if isinstance(layout, QtWidgets.QFormLayout):
        for row in range(layout.rowCount()):
            field = layout.itemAt(row, QtWidgets.QFormLayout.FieldRole)
            label = layout.itemAt(row, QtWidgets.QFormLayout.LabelRole)
            if field and field.widget() is widget and label and label.widget():
                results.append(label.widget())
    if layout:
        for i in range(1, layout.count()):
            part = layout.itemAt(i)
            if part and part.widget() is widget:
                before = layout.itemAt(i - 1)
                if before and before.widget(): results.append(before.widget())
    siblings = [w for w in parent.children() if isinstance(w, QtWidgets.QWidget)]
    if widget in siblings and siblings.index(widget) > 0:
        results.append(siblings[siblings.index(widget) - 1])
    return results


def locate(window_title, target_type, target_show="", previous_type="", previous_show=""):
    app = QtWidgets.QApplication.instance()
    if app is None: raise RuntimeError("Qt application is not running")
    windows = [w for w in app.topLevelWidgets()
               if w.isVisible() and w.windowTitle() == window_title]
    if len(windows) != 1:
        raise RuntimeError("Expected one window {!r}, found {}".format(window_title, len(windows)))
    widgets = [windows[0]] + windows[0].findChildren(QtWidgets.QWidget)
    candidates = []
    for widget in widgets:
        try:
            if widget_kind(widget) != target_type: continue
            if target_show and widget_show(widget) != target_show: continue
            if previous_type or previous_show:
                if not any((not previous_type or widget_kind(prev) == previous_type) and
                           (not previous_show or widget_show(prev) == previous_show)
                           for prev in preceding(widget)):
                    continue
            candidates.append(widget)
        except (RuntimeError, TypeError):
            continue
    if len(candidates) != 1:
        raise RuntimeError("UI locator found {} candidates; expected exactly one".format(len(candidates)))
    return candidates[0]


def interact(window_title, target_type, target_show="", previous_type="", previous_show="",
             action="Read", value=None):
    """Find exactly one widget and perform an action.

    Supported: Read, Click, Fill (legacy), Check, Uncheck, Select, Set Value.
    Check/Uncheck are idempotent; Click toggles checkboxes.
    Qt widgets must be accessed from Maya's main UI thread.
    """
    widget = locate(window_title, target_type, target_show, previous_type, previous_show)
    action = str(action).strip().casefold().replace("_", " ")

    if action == "read":
        if isinstance(widget, QtWidgets.QLineEdit):
            return widget.text()
        if isinstance(widget, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
            return widget.toPlainText()
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.currentText()
        if isinstance(widget, QtWidgets.QAbstractButton) and widget.isCheckable():
            return widget.isChecked()
        if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            return widget.value()
        if isinstance(widget, QtWidgets.QAbstractSpinBox):
            return widget.text()
        return widget_show(widget)

    if action == "click":
        if not isinstance(widget, QtWidgets.QAbstractButton):
            raise TypeError("Click requires an AbstractButton")
        widget.click()
        return True

    if action in ("check", "uncheck"):
        if not isinstance(widget, QtWidgets.QAbstractButton) or not widget.isCheckable():
            raise TypeError("Check/Uncheck requires a checkable button")
        desired = action == "check"
        # Use click when a transition is necessary: emits clicked and toggled,
        # like a user interaction. No change on repeated calls.
        if widget.isChecked() != desired:
            widget.click()
        if widget.isChecked() != desired:
            raise RuntimeError("Could not change check state (widget may be disabled or tri-state)")
        return widget.isChecked()

    if action == "select":
        if isinstance(widget, QtWidgets.QComboBox):
            if isinstance(value, int) and not isinstance(value, bool):
                index = value
            else:
                index = widget.findText(str(value))
            if not 0 <= index < widget.count():
                raise ValueError("ComboBox option not found: {!r}".format(value))
            widget.setCurrentIndex(index)
            return widget.currentText()
        if isinstance(widget, QtWidgets.QRadioButton):
            if not widget.isChecked():
                widget.click()
            if not widget.isChecked():
                raise RuntimeError("Could not select radio button")
            return True
        raise TypeError("Select supports QComboBox or QRadioButton")

    if action in ("set value", "setvalue"):
        if isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value))
            return widget.value()
        if isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.setValue(float(value))
            return widget.value()
        raise TypeError("Set Value requires QSpinBox or QDoubleSpinBox")

    if action == "fill":
        # Compatibility with scripts generated by older Research versions.
        if isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(str(value))
        elif isinstance(widget, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
            widget.setPlainText(str(value))
        elif isinstance(widget, QtWidgets.QComboBox):
            index = widget.findText(str(value))
            if index < 0:
                raise ValueError("ComboBox option not found: {!r}".format(value))
            widget.setCurrentIndex(index)
        elif isinstance(widget, QtWidgets.QAbstractButton) and widget.isCheckable():
            widget.setChecked(bool(value))
        elif isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.setValue(float(value))
        else:
            raise TypeError("This widget type does not support Fill")
        return True

    raise ValueError("Unknown action: {!r}".format(action))
