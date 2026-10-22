"""Descriptor-based workspace I/O. Windows parent handles deny directory replacement."""

import os
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

from pydantic import Field

from mysoul.domain import Contract


class ReadArgs(Contract):
    path: str = Field(min_length=1, max_length=500)


class WriteArgs(ReadArgs):
    text: str = Field(max_length=64000)


class WorkspaceFiles:
    def __init__(self, root: Path, max_bytes=64000):
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.max_bytes = max_bytes

    def parts(self, name):
        win = PureWindowsPath(name)
        normalized = name.replace("\\", "/")
        parts = normalized.split("/")
        if (
            not name
            or Path(name).is_absolute()
            or win.drive
            or win.root
            or any(
                p in {"", ".", ".."}
                or ":" in p
                or p.endswith((".", " "))
                or PureWindowsPath(p).is_reserved()
                for p in parts
            )
        ):
            raise PermissionError("Workspace-relative regular path required")
        return parts

    @contextmanager
    def descriptor(self, name, write=False):
        parts = self.parts(name)
        handles = []
        fd = None
        try:
            if os.name == "nt":
                import ctypes
                import msvcrt
                from ctypes import wintypes

                api = ctypes.WinDLL("kernel32", use_last_error=True)
                api.CreateFileW.argtypes = [
                    wintypes.LPCWSTR,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.LPVOID,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.HANDLE,
                ]
                api.CreateFileW.restype = wintypes.HANDLE
                api.CloseHandle.argtypes = [wintypes.HANDLE]
                api.GetFinalPathNameByHandleW.argtypes = [
                    wintypes.HANDLE,
                    wintypes.LPWSTR,
                    wintypes.DWORD,
                    wintypes.DWORD,
                ]
                api.GetFinalPathNameByHandleW.restype = wintypes.DWORD

                def actual(handle):
                    buffer = ctypes.create_unicode_buffer(32768)
                    size = api.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
                    if not size or size >= len(buffer):
                        raise PermissionError("Cannot verify opened file path")
                    return Path(buffer.value.removeprefix("\\\\?\\")).resolve()

                parent = self.root
                for segment in [None, *parts[:-1]]:
                    if segment is not None:
                        parent = parent / segment
                    if parent.is_symlink() or parent.is_junction():
                        raise PermissionError("Reparse-point directories are not workspace tools")
                    handle = api.CreateFileW(
                        str(parent), 0x80000000, 3, None, 3, 0x02000000 | 0x00200000, None
                    )
                    if handle == ctypes.c_void_p(-1).value:
                        raise PermissionError("Cannot lock workspace directory")
                    handles.append(handle)
                    if not actual(handle).is_relative_to(self.root):
                        raise PermissionError("Directory escaped workspace")
                target = parent / parts[-1]
                if target.is_symlink() or target.is_junction():
                    raise PermissionError("Reparse-point file denied")
                flags = os.O_RDWR | os.O_CREAT if write else os.O_RDONLY
                fd = os.open(target, flags | os.O_BINARY, 0o600)
                if not actual(msvcrt.get_osfhandle(fd)).is_relative_to(self.root):
                    raise PermissionError("Opened file escaped workspace")
            else:
                parent_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                handles.append(parent_fd)
                for segment in parts[:-1]:
                    try:
                        parent_fd = os.open(
                            segment, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
                        )
                    except OSError as exc:
                        raise PermissionError("Unsafe workspace directory") from exc
                    handles.append(parent_fd)
                flags = (os.O_RDWR | os.O_CREAT if write else os.O_RDONLY) | os.O_NOFOLLOW
                try:
                    fd = os.open(parts[-1], flags, 0o600, dir_fd=parent_fd)
                except OSError as exc:
                    raise PermissionError("Unsafe workspace file") from exc
            info = os.fstat(fd)
            import stat

            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise PermissionError("Only single-link regular files are allowed")
            yield fd
        finally:
            if fd is not None:
                os.close(fd)
            for handle in reversed(handles):
                if os.name == "nt":
                    api.CloseHandle(handle)
                else:
                    os.close(handle)

    def read(self, name: str) -> str:
        with self.descriptor(name) as fd:
            data = os.read(fd, self.max_bytes + 1)
            if len(data) > self.max_bytes:
                raise ValueError("File exceeds output limit")
            return data.decode("utf-8")

    def write(self, name: str, text: str):
        data = text.encode("utf-8")
        if len(data) > self.max_bytes:
            raise ValueError("File exceeds write limit")
        with self.descriptor(name, write=True) as fd:
            os.ftruncate(fd, 0)
            remaining = memoryview(data)
            while remaining:
                count = os.write(fd, remaining)
                remaining = remaining[count:]
            os.fsync(fd)
        return name
