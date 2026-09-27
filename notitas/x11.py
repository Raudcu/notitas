"""Pequeños pedidos al gestor de ventanas en X11 vía libX11 (ctypes).

GTK4 ya no expone "siempre encima", mover ventanas ni forzar el foco. En X11
se los pedimos a Mutter con los mensajes EWMH estándar. En Wayland todas las
funciones son no-ops.
"""

import ctypes
import ctypes.util

_lib = None


class _ClientMessage(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", ctypes.c_long * 5),
    ]


class _SetWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("background_pixmap", ctypes.c_ulong),
        ("background_pixel", ctypes.c_ulong),
        ("border_pixmap", ctypes.c_ulong),
        ("border_pixel", ctypes.c_ulong),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int),
        ("event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int),
        ("colormap", ctypes.c_ulong),
        ("cursor", ctypes.c_ulong),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [("xclient", _ClientMessage), ("pad", ctypes.c_long * 24)]


def _load():
    global _lib
    if _lib is None:
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XInternAtom.restype = ctypes.c_ulong
        lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XSendEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.POINTER(_XEvent)
        ]
        lib.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
        ]
        lib.XChangeWindowAttributes.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(_SetWindowAttributes)
        ]
        lib.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
        lib.XQueryPointer.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint),
        ]
        lib.XFlush.argtypes = [ctypes.c_void_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        _lib = lib
    return _lib


class _Display:
    def __enter__(self):
        self.lib = _load()
        self.dpy = self.lib.XOpenDisplay(None)
        if not self.dpy:
            raise OSError("sin display X11")
        self.root = self.lib.XDefaultRootWindow(self.dpy)
        return self

    def __exit__(self, *_):
        self.lib.XFlush(self.dpy)
        self.lib.XCloseDisplay(self.dpy)

    def atom(self, name):
        return self.lib.XInternAtom(self.dpy, name.encode(), 0)

    def send(self, xid, message_type, *data):
        ev = _XEvent()
        ev.xclient.type = 33  # ClientMessage
        ev.xclient.send_event = 1
        ev.xclient.display = self.dpy
        ev.xclient.window = xid
        ev.xclient.message_type = self.atom(message_type)
        ev.xclient.format = 32
        for i, value in enumerate(data):
            ev.xclient.data[i] = value
        mask = (1 << 19) | (1 << 20)  # SubstructureNotify | SubstructureRedirect
        self.lib.XSendEvent(self.dpy, self.root, 0, mask, ctypes.byref(ev))


def xid_of(window):
    """XID de una Gtk.Window ya realizada, o None si no es X11."""
    try:
        import gi

        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11
    except (ImportError, ValueError):
        return None
    surface = window.get_surface()
    if not isinstance(surface, GdkX11.X11Surface):
        return None
    return surface.get_xid()


def activate(xid, timestamp=0):
    """Pide el foco como un "pager" (source=2): Mutter lo concede siempre."""
    with _Display() as d:
        d.send(xid, "_NET_ACTIVE_WINDOW", 2, timestamp, 0)


def set_states(xid, *states):
    """Agrega estados EWMH, p. ej. "ABOVE", "STICKY", "SKIP_TASKBAR"."""
    with _Display() as d:
        atoms = [d.atom(f"_NET_WM_STATE_{s}") for s in states]
        for i in range(0, len(atoms), 2):
            pair = atoms[i : i + 2] + [0]
            d.send(xid, "_NET_WM_STATE", 1, pair[0], pair[1], 2)


def make_unmanaged(xid):
    """Ventana que el gestor no administra (como un tooltip): nunca toma el foco.

    Tiene que hacerse antes de mostrarla; después hay que ubicarla con place().
    """
    with _Display() as d:
        attrs = _SetWindowAttributes(override_redirect=1)
        cw_override_redirect = 1 << 9
        d.lib.XChangeWindowAttributes(d.dpy, xid, cw_override_redirect, ctypes.byref(attrs))


def place(xid, x, y):
    """Mover una ventana no administrada (ver make_unmanaged)."""
    with _Display() as d:
        d.lib.XMoveWindow(d.dpy, xid, x, y)


def pointer():
    with _Display() as d:
        root, child = ctypes.c_ulong(), ctypes.c_ulong()
        rx, ry, wx, wy, mask = ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_uint()
        d.lib.XQueryPointer(d.dpy, d.root, ctypes.byref(root), ctypes.byref(child), ctypes.byref(rx),
                            ctypes.byref(ry), ctypes.byref(wx), ctypes.byref(wy), ctypes.byref(mask))
        return rx.value, ry.value


def move(xid, x, y):
    """Mueve la ventana pidiéndoselo al gestor (_NET_MOVERESIZE_WINDOW, como un pager)."""
    with _Display() as d:
        flags = (1 << 8) | (1 << 9) | (2 << 12)  # x | y | source=pager (gravity por defecto)
        d.send(xid, "_NET_MOVERESIZE_WINDOW", flags, x, y, 0, 0)


def position(xid):
    with _Display() as d:
        x, y, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
        d.lib.XTranslateCoordinates(
            d.dpy, xid, d.root, 0, 0, ctypes.byref(x), ctypes.byref(y), ctypes.byref(child)
        )
        return x.value, y.value
