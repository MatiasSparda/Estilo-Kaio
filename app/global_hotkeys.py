"""Atajos globales Windows (RegisterHotKey) — prioridad sobre emuladores/DOSBox."""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None
    kernel32 = None

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_REMOVE = 0x0001
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# NULL hwnd → WM_HOTKEY a la cola del hilo que registró.
_HWND_THREAD = 0


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", _POINT),
    ]


if user32 is not None:
    user32.RegisterHotKey.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(_MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
    user32.DispatchMessageW.restype = wintypes.LPARAM

_VK_BY_NAME: dict[str, int] = {
    "pause": 0x13,
    "scroll": 0x91,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
}
for _i in range(1, 25):
    _VK_BY_NAME[f"f{_i}"] = 0x6F + _i


def parse_hotkey(hotkey: str) -> tuple[int, int]:
    """Convierte 'alt+5', 'ctrl+shift+f9' → (modifiers, virtual_key)."""
    raw = (hotkey or "").strip().lower().replace(" ", "")
    if not raw:
        raise ValueError("Atajo vacío")
    parts = raw.split("+")
    mods = MOD_NOREPEAT
    key = parts[-1]
    for part in parts[:-1]:
        if part in ("alt", "menu"):
            mods |= MOD_ALT
        elif part in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif part == "shift":
            mods |= MOD_SHIFT
        elif part in ("win", "windows", "super"):
            mods |= MOD_WIN
        else:
            raise ValueError(f"Modificador desconocido: {part}")
    if key in _VK_BY_NAME:
        vk = _VK_BY_NAME[key]
    elif len(key) == 1:
        vk = ord(key.upper())
    else:
        raise ValueError(f"Tecla desconocida: {key}")
    return mods, vk


class WindowsGlobalHotkeys:
    """Hilo dedicado GetMessage — funciona en exe PyInstaller y con DOSBox en foco."""

    def __init__(self) -> None:
        if user32 is None:
            raise RuntimeError("Solo Windows")
        self._callbacks: dict[int, callable] = {}
        self._registered: list[int] = []
        self._app = None
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._start_error: Exception | None = None

    def register(self, hotkey_id: int, hotkey: str, callback) -> None:
        mods, vk = parse_hotkey(hotkey)
        ok = user32.RegisterHotKey(_HWND_THREAD, int(hotkey_id), mods, vk)
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(f"RegisterHotKey({hotkey!r}) falló (winerr {err})")
        self._callbacks[int(hotkey_id)] = callback
        self._registered.append(int(hotkey_id))
        print(f"[HOTKEY] registrado id={hotkey_id} combo={hotkey!r} tid={self._thread_id}")

    def _unregister_on_thread(self) -> None:
        for hid in list(self._registered):
            try:
                user32.UnregisterHotKey(_HWND_THREAD, hid)
            except Exception:
                pass
        self._registered.clear()
        self._callbacks.clear()

    def _message_loop(self, specs: list[tuple[int, str, callable]]) -> None:
        self._thread_id = int(kernel32.GetCurrentThreadId())
        try:
            for hid, combo, cb in specs:
                self.register(hid, combo, cb)
        except Exception as e:
            self._start_error = e
            self._unregister_on_thread()
            self._ready.set()
            return

        self._ready.set()
        msg = _MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                cb = self._callbacks.get(int(msg.wParam))
                app = self._app
                if cb and app is not None:
                    try:
                        app.after(0, cb)
                    except Exception as e:
                        print(f"Hotkey encolar UI: {e}")
            else:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        self._unregister_on_thread()

    def start(self, app, specs: list[tuple[int, str, callable]]) -> None:
        self._app = app
        self._thread = threading.Thread(
            target=self._message_loop,
            args=(specs,),
            name="EstiloKaio-Hotkeys",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise TimeoutError("Hilo de hotkeys no arrancó a tiempo")
        if self._start_error is not None:
            raise self._start_error

    def unregister_all(self) -> None:
        tid = self._thread_id
        if tid and user32 is not None:
            try:
                user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._thread_id = None
        self._app = None


def try_register(app, hotkeys: list[tuple[int, str, callable]]) -> WindowsGlobalHotkeys | None:
    """Registra atajos globales; None si falla (p. ej. atajo tomado por otro programa)."""
    if sys.platform != "win32" or user32 is None:
        return None
    gh: WindowsGlobalHotkeys | None = None
    try:
        gh = WindowsGlobalHotkeys()
        gh.start(app, hotkeys)
        return gh
    except Exception as e:
        print(f"Atajos globales Windows no disponibles: {e}")
        if gh is not None:
            try:
                gh.unregister_all()
            except Exception:
                pass
        return None
