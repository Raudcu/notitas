"""Ícono en la barra superior (StatusNotifierItem + com.canonical.dbusmenu).

Lo muestra la extensión "AppIndicator" que Ubuntu trae activada. Se implementa
directo sobre D-Bus porque libayatana-appindicator es GTK3 y no se puede mezclar
con GTK4 en el mismo proceso.
"""

import os

from gi.repository import Gio, GLib

ICONS_DIR = os.path.join(os.path.dirname(__file__), "icons")
ICON_NAME = "notitas-tray-symbolic"

SNI_XML = """
<node><interface name="org.kde.StatusNotifierItem">
  <property name="Category" type="s" access="read"/>
  <property name="Id" type="s" access="read"/>
  <property name="Title" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="IconName" type="s" access="read"/>
  <property name="IconThemePath" type="s" access="read"/>
  <property name="Menu" type="o" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
  <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
  <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
  <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
  <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
  <signal name="NewIcon"/>
  <signal name="NewTitle"/>
  <signal name="NewStatus"><arg type="s"/></signal>
</interface></node>
"""

MENU_XML = """
<node><interface name="com.canonical.dbusmenu">
  <property name="Version" type="u" access="read"/>
  <property name="TextDirection" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="IconThemePath" type="as" access="read"/>
  <method name="GetLayout">
    <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
    <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/>
  </method>
  <method name="GetGroupProperties">
    <arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/>
  </method>
  <method name="GetProperty">
    <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/>
  </method>
  <method name="Event">
    <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/>
    <arg type="u" direction="in"/>
  </method>
  <method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
  <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
  <method name="AboutToShowGroup">
    <arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/>
  </method>
  <signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
  <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
</interface></node>
"""

SNI_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
WATCHER = "org.kde.StatusNotifierWatcher"


class _Item:
    def __init__(self, label=None, callback=None, children=None, separator=False, toggled=None):
        self.label = label
        self.callback = callback
        self.children = children or []
        self.separator = separator
        self.toggled = toggled

    def props(self):
        p = {}
        if self.separator:
            p["type"] = GLib.Variant("s", "separator")
        if self.label is not None:
            p["label"] = GLib.Variant("s", self.label.replace("_", "__"))
        if self.children:
            p["children-display"] = GLib.Variant("s", "submenu")
        if self.toggled is not None:
            p["toggle-type"] = GLib.Variant("s", "checkmark")
            p["toggle-state"] = GLib.Variant("i", 1 if self.toggled else 0)
        if self.label is not None and not self.callback and not self.children:
            p["enabled"] = GLib.Variant("b", False)
        return p


class TrayIcon:
    def __init__(self, connection, build_menu, on_activate):
        """build_menu() -> lista de ítems (item()/separator()); se vuelve a llamar en cada refresh()."""
        self.conn = connection
        self.build_menu = build_menu
        self.on_activate = on_activate
        self.revision = 1
        self.items = {}
        self.service = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._rebuild()

        sni = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self._regs = [
            self.conn.register_object(SNI_PATH, sni, self._sni_call, self._sni_prop, None),
            self.conn.register_object(MENU_PATH, menu, self._menu_call, self._menu_prop, None),
        ]
        self._owner = Gio.bus_own_name_on_connection(
            self.conn, self.service, Gio.BusNameOwnerFlags.NONE, None, None
        )
        # Si gnome-shell se reinicia, el watcher vuelve a aparecer: re-registrarse.
        self._watch = Gio.bus_watch_name_on_connection(
            self.conn, WATCHER, Gio.BusNameWatcherFlags.NONE, self._register, None
        )

    def _register(self, *_):
        self.conn.call(
            WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (self.service,)), None, Gio.DBusCallFlags.NONE, -1, None, None, None,
        )

    # ---------- menú ----------

    def refresh(self):
        self._rebuild()
        self.revision += 1
        self.conn.emit_signal(None, MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                              GLib.Variant("(ui)", (self.revision, 0)))

    def _rebuild(self):
        self.items = {0: _Item(children=self.build_menu())}
        next_id = 1

        def number(item):
            nonlocal next_id
            for child in item.children:
                child.id = next_id
                self.items[next_id] = child
                next_id += 1
                number(child)

        number(self.items[0])

    def _layout(self, item_id, depth):
        item = self.items[item_id]
        children = []
        if depth != 0:
            children = [GLib.Variant("(ia{sv}av)", self._layout(c.id, depth - 1)) for c in item.children]
        return (item_id, item.props(), children)

    def _menu_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        args = params.unpack()
        if method == "GetLayout":
            parent, depth, _names = args
            parent = parent if parent in self.items else 0
            invocation.return_value(
                GLib.Variant("(u(ia{sv}av))", (self.revision, self._layout(parent, depth)))
            )
        elif method == "GetGroupProperties":
            ids = args[0] or list(self.items)
            result = [(i, self.items[i].props()) for i in ids if i in self.items]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (result,)))
        elif method == "GetProperty":
            item_id, name = args
            value = self.items.get(item_id, _Item()).props().get(name, GLib.Variant("s", ""))
            invocation.return_value(GLib.Variant("(v)", (value,)))
        elif method == "Event":
            item_id, event, _data, _ts = args
            self._fire(item_id, event)
            invocation.return_value(None)
        elif method == "EventGroup":
            for item_id, event, _data, _ts in args[0]:
                self._fire(item_id, event)
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))

    def _fire(self, item_id, event):
        item = self.items.get(item_id)
        if event == "clicked" and item and item.callback:
            GLib.idle_add(lambda: item.callback() and False)

    def _menu_prop(self, _conn, _sender, _path, _iface, name):
        return {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", [ICONS_DIR]),
        }.get(name)

    # ---------- ítem ----------

    def _sni_call(self, _conn, _sender, _path, _iface, method, _params, invocation):
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(lambda: self.on_activate() and False)
        invocation.return_value(None)

    def _sni_prop(self, _conn, _sender, _path, _iface, name):
        return {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", "notitas"),
            "Title": GLib.Variant("s", "Notitas"),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", ICON_NAME),
            "IconThemePath": GLib.Variant("s", ICONS_DIR),
            "Menu": GLib.Variant("o", MENU_PATH),
            "ItemIsMenu": GLib.Variant("b", False),
            "ToolTip": GLib.Variant("(sa(iiay)ss)", (ICON_NAME, [], "Notitas", "")),
        }.get(name)


def item(label, callback=None, children=None, toggled=None):
    return _Item(label=label, callback=callback, children=children, toggled=toggled)


def separator():
    return _Item(separator=True)
