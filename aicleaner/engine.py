"""规则执行：把一条规则展开成具体的“清理单元”，扫描和清理共用同一套逻辑。"""
import fnmatch
import os
import re
import time

from . import fsutil, paths
from .rules import AGE_STEPS, PROTECTED_NAMES

# 名称-版本号：2.1.304、app-1.2.3、github.copilot-1.388.0、chromium-1140、win64-131.0.6778.204
_VERSION_RE = re.compile(r"^(?P<name>.*?)[-_@]?v?(?P<ver>\d+(?:\.\d+)+|\d{3,})(?P<suffix>[-_.+][A-Za-z0-9_.\-+]*)?$")


def parse_version(name):
    m = _VERSION_RE.match(name)
    if not m:
        return None
    nums = tuple(int(x) for x in re.findall(r"\d+", m.group("ver")))
    return m.group("name").lower(), nums


def _match(name, patterns):
    return any(fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns)


def _protected(path):
    return os.path.basename(path).lower() in PROTECTED_NAMES


class Unit:
    """一个清理单元。kind: entry 整项 / files 逐个文件筛选 / keep 只统计不清理。"""
    __slots__ = ("path", "kind")

    def __init__(self, path, kind):
        self.path, self.kind = path, kind


def expand_roots(rule):
    roots = []
    seen = set()
    for pat in rule.paths:
        for p in paths.expand(pat):
            k = paths.norm_key(p)
            if k not in seen:
                seen.add(k)
                roots.append(p)
    return roots


def units(rule):
    """返回 (units, covered)。covered 是本规则统计范围内的路径（用于避免重复统计）。"""
    out, covered = [], []
    for root in expand_roots(rule):
        is_dir = os.path.isdir(root) and not fsutil.is_link(root)
        if rule.mode == "whole" or not is_dir:
            covered.append(root)
            out.append(Unit(root, "keep" if _protected(root) else "entry"))
        elif rule.mode == "contents":
            covered.append(root)
            for e in fsutil.list_dir(root):
                ok = not _protected(e.path) and e.name not in rule.exclude
                if ok and rule.pattern:
                    ok = _match(e.name, rule.pattern)
                out.append(Unit(e.path, "entry" if ok else "keep"))
        elif rule.mode == "files":
            covered.append(root)
            out.append(Unit(root, "files"))
        elif rule.mode == "old_versions":
            groups = {}
            for e in fsutil.list_dir(root):
                v = parse_version(e.name)
                if v is None:
                    continue
                try:
                    mtime = e.stat(follow_symlinks=False).st_mtime
                except OSError:
                    mtime = 0
                groups.setdefault(v[0], []).append((v[1], mtime, e.path))
            for items in groups.values():
                items.sort()
                for i, (_, _, p) in enumerate(items):
                    covered.append(p)
                    out.append(Unit(p, "keep" if i == len(items) - 1 else "entry"))
    return out, covered


def _file_filter(rule, root):
    """files 模式下判断一个文件是否在清理范围内（不含时间条件）。"""
    excl = {x.lower() for x in rule.exclude}

    def ok(path, depth):
        if rule.max_depth is not None and depth > rule.max_depth:
            return False
        name = os.path.basename(path)
        if name.lower() in PROTECTED_NAMES:
            return False
        if excl:
            rel = os.path.relpath(path, root).lower().split(os.sep)
            if any(part in excl for part in rel[:-1]):
                return False
        return not rule.pattern or _match(name, rule.pattern)
    return ok


def _bucket_add(buckets, age, size):
    for i, step in enumerate(AGE_STEPS):
        if age >= step:
            buckets[i] += size
        else:
            break


def scan_rule(rule, now=None):
    """统计一条规则：总占用、可清理量（按时间分档）、最大的子项。"""
    now = now or time.time()
    us, covered = units(rule)
    total = files = 0
    newest = 0
    buckets = [0] * len(AGE_STEPS)
    top = []
    for u in us:
        per_file = []
        if u.kind == "files":
            ok = _file_filter(rule, u.path)

            def on_file(p, size, mtime, depth, ok=ok):
                if ok(p, depth):
                    per_file.append((size, mtime))
        elif u.kind == "entry" and rule.age_by == "file":
            def on_file(p, size, mtime, depth):
                per_file.append((size, mtime))
        else:
            on_file = None
        size, count, mt = fsutil.walk(u.path, on_file)
        if u.kind == "files":  # 只统计匹配的文件，避免把同目录的无关文件算进来
            size, count = sum(s for s, _ in per_file), len(per_file)
            mt = max((m for _, m in per_file), default=0)
        total += size
        files += count
        newest = max(newest, mt)
        if u.kind == "keep":
            pass
        elif u.kind == "files" or rule.age_by == "file":
            for s, m in per_file:
                if rule.age_by:
                    _bucket_add(buckets, fsutil.age_days(m, now), s)
                else:
                    buckets[0] += s
        elif rule.age_by == "entry":
            _bucket_add(buckets, fsutil.age_days(mt, now), size)
        else:
            buckets[0] += size
        if len(us) > 1 and size:
            top.append((size, os.path.basename(u.path), u.kind != "keep", mt))
    if not rule.age_by:
        buckets = [buckets[0]] * len(AGE_STEPS)
    top.sort(reverse=True)
    return {
        "roots": expand_roots(rule),
        "covered": covered,
        "total": total,
        "files": files,
        "newest": newest,
        "buckets": buckets,
        "top": [{"name": n, "size": s, "cleanable": c, "mtime": m} for s, n, c, m in top[:10]],
    }


def plan(rule, age, now=None):
    """计算实际要删除的内容。返回 (trees, files, prune_roots)：
    trees  [(path, size)] 整项删除
    files  [(path, size)] 逐个文件删除
    prune_roots 删完文件后需要清理空目录的根
    """
    now = now or time.time()
    age = age if rule.age_by else 0
    trees, files, prune = [], [], []
    us, _ = units(rule)
    for u in us:
        if u.kind == "keep":
            continue
        if u.kind == "files" or rule.age_by == "file":
            ok = _file_filter(rule, u.path) if u.kind == "files" else (lambda p, d: True)
            found = []

            def on_file(p, size, mtime, depth, ok=ok, found=found):
                if ok(p, depth) and fsutil.age_days(mtime, now) >= age:
                    found.append((p, size))
            fsutil.walk(u.path, on_file)
            files.extend(found)
            if found and os.path.isdir(u.path):
                prune.append(u.path)
            continue
        size, _, mt = fsutil.walk(u.path)
        if rule.age_by == "entry" and fsutil.age_days(mt, now) < age:
            continue
        trees.append((u.path, size))
    return trees, files, prune


def is_safe_target(path):
    """最后一道保险：只允许删除用户目录（含 AppData、Temp）内足够深的路径。"""
    p = os.path.abspath(path)
    home = paths.home()
    bases = paths.allowed_bases()
    if paths.norm_key(p) in {paths.norm_key(b) for b in bases}:
        return False
    for base in sorted(bases, key=len, reverse=True):
        if not paths.is_within(p, base):
            continue
        depth = len(os.path.relpath(p, base).split(os.sep))
        is_dir = os.path.isdir(p) and not fsutil.is_link(p)
        need = 2 if (is_dir and paths.norm_key(base) == paths.norm_key(home)) else 1
        return depth >= need
    return False
