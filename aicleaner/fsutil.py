"""文件系统工具：统计大小、安全删除、移到回收站。

所有遍历都不会跟随符号链接 / 目录联接（junction），删除时只删链接本身，
避免误删链接指向的其他盘数据。
"""
import ctypes
import os
import stat
import time

from . import paths

REPARSE = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT


def is_link(entry_or_path):
    """是否为符号链接或目录联接。接受 os.DirEntry 或路径字符串。"""
    try:
        if isinstance(entry_or_path, os.DirEntry):
            if entry_or_path.is_symlink():
                return True
            st = entry_or_path.stat(follow_symlinks=False)
        else:
            st = os.lstat(entry_or_path)
            if stat.S_ISLNK(st.st_mode):
                return True
        return bool(getattr(st, "st_file_attributes", 0) & REPARSE) and stat.S_ISDIR(st.st_mode)
    except OSError:
        return True


def walk(path, on_file=None, skip=None):
    """统计 path 的大小。返回 (字节数, 文件数, 最新修改时间)。

    on_file(path, size, mtime, depth)：每个文件的回调，depth 为相对 path 的层级（直接子文件为 1）。
    skip：路径键集合，命中的子路径整体跳过（不计入）。
    """
    try:
        st = os.lstat(path)
    except OSError:
        return 0, 0, 0
    if not stat.S_ISDIR(st.st_mode):
        if on_file:
            on_file(path, st.st_size, st.st_mtime, 0)
        return st.st_size, 1, st.st_mtime
    if is_link(path):
        return 0, 0, st.st_mtime
    # 最新时间只看文件：目录时间会因为新建、复制而变化，不可靠；空目录才用目录自身的时间
    total, count, newest = 0, 0, 0
    stack = [(path, 0)]
    while stack:
        cur, depth = stack.pop()
        try:
            it = os.scandir(cur)
        except OSError:
            continue
        with it:
            for e in it:
                if skip and paths.norm_key(e.path) in skip:
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        if is_link(e):
                            continue
                        stack.append((e.path, depth + 1))
                    else:
                        s = e.stat(follow_symlinks=False)
                        total += s.st_size
                        count += 1
                        if s.st_mtime > newest:
                            newest = s.st_mtime
                        if on_file:
                            on_file(e.path, s.st_size, s.st_mtime, depth + 1)
                except OSError:
                    continue
    return total, count, newest if count else st.st_mtime


def list_dir(path):
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


# ---------------------------------------------------------------- 删除

class Result:
    def __init__(self):
        self.freed = 0
        self.removed = 0
        self.failed = 0
        self.errors = []

    def error(self, path, exc):
        self.failed += 1
        if len(self.errors) < 8:
            self.errors.append(f"{path}: {exc.__class__.__name__} {getattr(exc, 'strerror', '') or exc}")


def _unlink(path):
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        os.unlink(path)


def _rmdir(path):
    try:
        os.rmdir(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        os.rmdir(path)


def delete_file(path, size, res):
    try:
        _unlink(path)
        res.freed += size
        res.removed += 1
    except FileNotFoundError:
        pass
    except OSError as exc:
        res.error(path, exc)


def delete_tree(path, res):
    """永久删除文件或目录。链接只删除链接本身。"""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        res.error(path, exc)
        return
    if not stat.S_ISDIR(st.st_mode):
        delete_file(path, st.st_size, res)
        return
    if is_link(path):
        try:
            _rmdir(path)
        except OSError as exc:
            res.error(path, exc)
        return
    # 后序遍历：先删内容，再删目录
    stack = [(path, False)]
    while stack:
        cur, visited = stack.pop()
        if visited:
            try:
                _rmdir(cur)
            except OSError as exc:
                if not isinstance(exc, FileNotFoundError) and not _nonempty(cur):
                    # 目录里还有被占用的文件时，里面的文件已经记过错，这里不再重复
                    res.error(cur, exc)
            continue
        stack.append((cur, True))
        for e in list_dir(cur):
            try:
                if e.is_dir(follow_symlinks=False):
                    if is_link(e):
                        _rmdir(e.path)
                    else:
                        stack.append((e.path, False))
                else:
                    delete_file(e.path, e.stat(follow_symlinks=False).st_size, res)
            except OSError as exc:
                res.error(e.path, exc)


def _nonempty(path):
    try:
        with os.scandir(path) as it:
            return any(True for _ in it)
    except OSError:
        return False



def prune_empty_dirs(root, keep_root=True):
    """自底向上删除 root 下的空目录。"""
    dirs = []
    stack = [root]
    while stack:
        cur = stack.pop()
        dirs.append(cur)
        for e in list_dir(cur):
            if e.is_dir(follow_symlinks=False) and not is_link(e):
                stack.append(e.path)
    for d in reversed(dirs):
        if keep_root and d == root:
            continue
        try:
            os.rmdir(d)
        except OSError:
            pass


# ---------------------------------------------------------------- 回收站

if os.name == "nt":
    from ctypes import wintypes

    class _SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", ctypes.c_void_p),
            ("pTo", ctypes.c_void_p),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    _FO_DELETE = 3
    _FLAGS = 0x0040 | 0x0010 | 0x0004 | 0x0400 | 0x4000  # 可撤销|不确认|静默|不弹错误|放不进回收站时提醒


def recycle(items, res, batch=100):
    """把 [(path, size)] 移到回收站。"""
    if os.name != "nt":
        raise OSError("回收站仅支持 Windows")
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        s = "\0".join(os.path.abspath(p) for p, _ in chunk) + "\0\0"
        buf = (ctypes.c_wchar * len(s))(*s)
        op = _SHFILEOPSTRUCTW()
        op.wFunc = _FO_DELETE
        op.pFrom = ctypes.cast(buf, ctypes.c_void_p)
        op.fFlags = _FLAGS
        code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        for p, size in chunk:
            if os.path.lexists(p):
                res.error(p, OSError(f"回收站操作未完成（代码 {code:#x}，可能文件被占用）"))
            else:
                res.freed += size
                res.removed += 1


def age_days(mtime, now=None):
    return ((now or time.time()) - mtime) / 86400
