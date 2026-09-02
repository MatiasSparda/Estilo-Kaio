"""OneOCR (Snipping Tool) — motor OCR por defecto."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import uuid
from ctypes import (
    Structure,
    c_byte,
    c_char_p,
    c_float,
    c_int,
    c_int64,
    c_long,
    c_void_p,
    POINTER,
    byref,
)
from pathlib import Path

from PIL import Image

from ..ocr_types import OcrLineBox
from .base import bbox_quad_to_rect

ONEOCR_MODEL_KEY = 'kj)TGtrK>f]b[Piow.gU+nC@s""""""4'
ONEOCR_DLL = "oneocr.dll"
ONEOCR_MODEL = "oneocr.onemodel"
ONNX_DLL = "onnxruntime.dll"

LOAD_LIBRARY_SEARCH_DEFAULT_DIRS = 0x00001000


class BoundingBox(Structure):
    _fields_ = [
        ("x1", c_float),
        ("y1", c_float),
        ("x2", c_float),
        ("y2", c_float),
        ("x3", c_float),
        ("y3", c_float),
        ("x4", c_float),
        ("y4", c_float),
    ]


class Img(Structure):
    _fields_ = [
        ("t", c_int),
        ("col", c_int),
        ("row", c_int),
        ("_unk", c_int),
        ("step", c_int64),
        ("data_ptr", c_void_p),
    ]


def _dll_dir() -> Path:
    """DLLs OneOCR fuera del repo: evita que Windows cargue ORT Microsoft al usar RapidOCR."""
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "EstiloKaio" / "oneocr-dlls"


def _get_appx_install(package: str) -> str | None:
    try:
        cmd = (
            f"(Get-AppxPackage -Name {package} -ErrorAction SilentlyContinue)"
            ".InstallLocation"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        path = (r.stdout or "").strip()
        return path or None
    except Exception:
        return None


def _register_dll_path(dll_path: Path) -> None:
    """Solo add_dll_directory local. NO SetDefaultDllDirectories (rompe ORT de RapidOCR)."""
    if os.name != "nt":
        return
    try:
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(dll_path))
    except Exception as e:
        print(f"OneOCR: aviso DLL path: {e}")


def _copy_oneocr_from_system() -> bool:
    dest = _dll_dir()
    dest.mkdir(parents=True, exist_ok=True)
    sources: list[Path] = []

    sketch = _get_appx_install("Microsoft.ScreenSketch")
    if sketch:
        snip = Path(sketch) / "SnippingTool"
        if (snip / ONEOCR_DLL).is_file():
            sources.append(snip)

    if not sources:
        photo = _get_appx_install("Microsoft.Windows.Photos")
        if photo and (Path(photo) / ONEOCR_DLL).is_file():
            sources.append(Path(photo))

    if not sources:
        return False

    src = sources[0]
    try:
        for name in (ONEOCR_DLL, ONEOCR_MODEL, ONNX_DLL):
            s = src / name
            if s.is_file():
                shutil.copy2(s, dest / name)
        return (dest / ONEOCR_DLL).is_file()
    except OSError as e:
        print(f"OneOCR copy error: {e}")
        return False


class OneOcrBackend:
    id = "oneocr"

    def __init__(self, language_code: str = "en"):
        self.language_code = language_code
        self.last_error: str | None = None
        self._dll: ctypes.CDLL | None = None
        self._pipeline = c_int64(0)
        self._opt = c_int64(0)
        self._initialized = False
        self._last_img_buffer: bytearray | None = None

    def prepare_dlls(self) -> bool:
        """Detecta y copia oneocr.dll desde Snipping Tool / Photos."""
        dll_path = _dll_dir()
        if not (dll_path / ONEOCR_DLL).is_file():
            if not _copy_oneocr_from_system():
                self.last_error = (
                    "OneOCR: no encontré oneocr.dll. Instalá Recortes (Snipping Tool) en Windows."
                )
                return False
        return True

    def warmup(self) -> bool:
        """Inicializa pipeline (evita 2–5 s en el primer Alt+T)."""
        return self._ensure_initialized()

    def _bind_dll(self) -> None:
        assert self._dll is not None
        d = self._dll
        d.CreateOcrPipeline.argtypes = [
            c_char_p,
            c_char_p,
            c_int64,
            ctypes.POINTER(c_int64),
        ]
        d.CreateOcrPipeline.restype = c_int64
        d.CreateOcrProcessOptions.argtypes = [ctypes.POINTER(c_int64)]
        d.CreateOcrProcessOptions.restype = c_int64
        d.OcrProcessOptionsSetMaxRecognitionLineCount.argtypes = [c_int64, c_int64]
        d.OcrProcessOptionsSetMaxRecognitionLineCount.restype = c_int64
        d.RunOcrPipeline.argtypes = [
            c_int64,
            ctypes.POINTER(Img),
            c_int64,
            ctypes.POINTER(c_int64),
        ]
        d.RunOcrPipeline.restype = c_int64
        d.GetOcrLineCount.argtypes = [c_int64, ctypes.POINTER(c_int64)]
        d.GetOcrLineCount.restype = c_int64
        d.GetOcrLine.argtypes = [c_int64, c_int64, ctypes.POINTER(c_int64)]
        d.GetOcrLine.restype = c_int64
        d.GetOcrLineContent.argtypes = [c_int64, ctypes.POINTER(c_void_p)]
        d.GetOcrLineContent.restype = c_int64
        d.GetOcrLineBoundingBox.argtypes = [c_int64, ctypes.POINTER(c_void_p)]
        d.GetOcrLineBoundingBox.restype = c_int64

    def _load_dll(self) -> bool:
        if self._dll is not None:
            return True
        if not self.prepare_dlls():
            return False
        dll_path = _dll_dir()
        _register_dll_path(dll_path)
        try:
            self._dll = ctypes.CDLL(str(dll_path / ONEOCR_DLL))
            self._bind_dll()
            return True
        except OSError as e:
            self.last_error = f"OneOCR: no pude cargar DLL: {e}"
            return False

    def _try_create_pipeline(self, model_path: str) -> bool:
        assert self._dll is not None
        dll = self._dll
        ctx = c_int64(0)
        pipeline = c_int64(0)

        create_utf8 = dll.CreateOcrPipeline
        create_utf8.argtypes = [c_char_p, c_char_p, c_int64, POINTER(c_int64)]
        create_utf8.restype = c_int64

        create_utf16 = getattr(dll, "CreateOcrPipeline", None)
        if hasattr(dll, "CreateOcrPipeline"):
            pass

        key_b = ONEOCR_MODEL_KEY.encode("utf-8")
        path_b = model_path.encode("utf-8")
        r = create_utf8(path_b, key_b, ctx, byref(pipeline))
        if r == 0 and pipeline.value:
            self._pipeline = pipeline
            return True

        # UTF-16 overload (same name, unicode on Windows)
        try:
            create_w = dll.CreateOcrPipeline
            create_w.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, c_int64, POINTER(c_int64)]
            create_w.restype = c_int64
            r = create_w(model_path, ONEOCR_MODEL_KEY, ctx, byref(pipeline))
            if r == 0 and pipeline.value:
                self._pipeline = pipeline
                return True
        except Exception:
            pass

        # Copia a ruta ASCII-only
        try:
            temp_dir = Path(os.environ.get("TEMP", ".")) / "oneocr_model"
            temp_dir.mkdir(parents=True, exist_ok=True)
            ext = Path(model_path).suffix
            tmp = temp_dir / f"oneocr_{uuid.uuid4().hex}{ext}"
            shutil.copy2(model_path, tmp)
            r = create_utf8(str(tmp).encode("utf-8"), key_b, ctx, byref(pipeline))
            if r == 0 and pipeline.value:
                self._pipeline = pipeline
                return True
        except Exception as e:
            self.last_error = f"OneOCR pipeline: {e}"
        return False

    def _ensure_initialized(self) -> bool:
        if self._initialized and self._pipeline.value:
            return True
        if not self._load_dll():
            return False
        assert self._dll is not None
        model_path = str((_dll_dir() / ONEOCR_MODEL).resolve())
        if not os.path.isfile(model_path):
            self.last_error = f"OneOCR: falta {ONEOCR_MODEL}"
            return False
        if not self._try_create_pipeline(model_path):
            self.last_error = self.last_error or "OneOCR: CreateOcrPipeline falló"
            return False

        opt = c_int64(0)
        r = self._dll.CreateOcrProcessOptions(byref(opt))
        if r != 0:
            self.last_error = f"OneOCR: CreateOcrProcessOptions={r}"
            return False
        self._dll.OcrProcessOptionsSetMaxRecognitionLineCount(opt, 1000)
        self._opt = opt
        self._initialized = True
        self.last_error = None
        return True

    def set_language(self, code: str) -> None:
        self.language_code = code

    def is_available(self) -> bool:
        if not sys.platform.startswith("win"):
            return False
        dll_path = _dll_dir()
        if (dll_path / ONEOCR_DLL).is_file():
            return True
        return _copy_oneocr_from_system()

    def status_message(self) -> str:
        if not sys.platform.startswith("win"):
            return "OneOCR: solo Windows"
        dll_path = _dll_dir()
        if not (dll_path / ONEOCR_DLL).is_file() and not _copy_oneocr_from_system():
            return "OneOCR: no instalado — usá «Preparar OneOCR» o instalá Recortes"
        if self._ensure_initialized():
            return f"OneOCR listo · {dll_path}"
        return self.last_error or "OneOCR: no disponible"

    def _ptr_to_utf8(self, ptr: int) -> str:
        if not ptr:
            return ""
        try:
            return ctypes.string_at(ptr).decode("utf-8")
        except Exception:
            length = 0
            while ctypes.cast(ptr + length, POINTER(c_byte))[0]:
                length += 1
            return ctypes.string_at(ptr, length).decode("utf-8", errors="replace")

    def recognize_lines(self, image: Image.Image) -> list[OcrLineBox]:
        if not self._ensure_initialized():
            return []
        assert self._dll is not None

        rgb = image.convert("RGB")
        w, h = rgb.size
        raw = rgb.tobytes()
        # RGB → BGR row-major con stride alineado a 4 bytes
        stride = ((w * 3 + 3) // 4) * 4
        buffer = bytearray(stride * h)
        for y in range(h):
            row_off = y * stride
            src_off = y * w * 3
            for x in range(w):
                i = src_off + x * 3
                o = row_off + x * 3
                buffer[o] = raw[i + 2]
                buffer[o + 1] = raw[i + 1]
                buffer[o + 2] = raw[i]

        self._last_img_buffer = buffer
        arr = (c_byte * len(buffer)).from_buffer(self._last_img_buffer)
        img_struct = Img(
            t=1,
            col=w,
            row=h,
            _unk=0,
            step=stride,
            data_ptr=ctypes.cast(arr, c_void_p),
        )

        instance = c_int64(0)
        r = self._dll.RunOcrPipeline(
            self._pipeline.value, byref(img_struct), self._opt.value, byref(instance)
        )
        if r != 0 or not instance.value:
            self.last_error = f"OneOCR RunOcrPipeline={r}"
            return []

        line_count = c_int64(0)
        if self._dll.GetOcrLineCount(instance, byref(line_count)) != 0:
            return []

        out: list[OcrLineBox] = []
        for i in range(line_count.value):
            line_handle = c_int64(0)
            if self._dll.GetOcrLine(instance, i, byref(line_handle)) != 0:
                continue
            content_ptr = c_void_p()
            if self._dll.GetOcrLineContent(line_handle, byref(content_ptr)) != 0:
                continue
            text = self._ptr_to_utf8(content_ptr.value or 0).strip()
            if not text:
                continue
            bb_ptr = c_void_p()
            if self._dll.GetOcrLineBoundingBox(line_handle, byref(bb_ptr)) != 0:
                out.append(OcrLineBox(text=text, x=0, y=float(i * 20), w=100, h=16))
                continue
            bb = ctypes.cast(bb_ptr, POINTER(BoundingBox)).contents
            x, y, bw, bh = bbox_quad_to_rect(
                bb.x1, bb.y1, bb.x2, bb.y2, bb.x3, bb.y3, bb.x4, bb.y4
            )
            out.append(OcrLineBox(text=text, x=x, y=y, w=bw, h=bh))
        return out
