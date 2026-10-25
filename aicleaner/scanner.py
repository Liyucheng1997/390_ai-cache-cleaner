"""扫描调度：并行执行所有规则，统计各工具的“其他数据”，发现未识别的 AI 目录。"""
import hashlib
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import engine, fsutil, paths
from .rules import (CATEGORIES, PRIORITIES, RULE_MAP, RULES, TOOL_MAP, TOOLS, UNKNOWN_KEYWORDS,
                    UNKNOWN_MIN_SIZE, UNKNOWN_SCAN_DIRS)


def running_processes():
    """返回正在运行的进程名集合（小写）。"""
    if os.name != "nt":
        return set()
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        text = out.decode("mbcs", errors="ignore") if hasattr(out, "decode") else out
    except Exception:
        return set()
    names = set()
    for line in text.splitlines():
        if line.startswith('"'):
            names.add(line.split('","', 1)[0].strip('"').lower())
    return names


def disk_info():
    drive = os.path.splitdrive(paths.home())[0] or "/"
    try:
        u = shutil.disk_usage(drive + os.sep)
        return {"drive": drive, "total": u.total, "used": u.used, "free": u.free}
    except OSError:
        return {"drive": drive, "total": 0, "used": 0, "free": 0}


def _item_from_rule(rule, stats):
    return {
        "id": rule.id, "tool": rule.tool, "name": rule.name, "category": rule.category,
        "priority": rule.priority, "desc": rule.desc, "impact": rule.impact, "note": rule.note,
        "mode": rule.mode, "age_by": rule.age_by, "default_age": rule.age,
        "paths": stats["roots"], "total": stats["total"], "files": stats["files"],
        "newest": stats["newest"], "buckets": stats["buckets"], "top": stats["top"],
        "selectable": rule.priority <= 3,
    }


class Scanner:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"phase": "idle", "done": 0, "total": 0, "current": "", "started": 0}
        self.items = {}
        self.covered = {}  # rule id -> 覆盖路径
        self.result = None

    def status(self):
        with self.lock:
            return dict(self.state)

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def _tick(self, name):
        with self.lock:
            self.state["done"] += 1
            self.state["current"] = name

    # ------------------------------------------------------------ 主流程

    def scan(self, ids=None):
        """全量扫描；传入 ids 时只重扫这些规则（清理之后用）。"""
        rules = [RULE_MAP[i] for i in ids if i in RULE_MAP] if ids else RULES
        self._set(phase="scanning", done=0, total=len(rules) + (0 if ids else 2),
                  current="", started=time.time())
        now = time.time()

        def work(rule):
            stats = engine.scan_rule(rule, now)
            self._tick(rule.name)
            return rule, stats

        with ThreadPoolExecutor(max_workers=8) as pool:
            for rule, stats in pool.map(work, rules):
                self.covered[rule.id] = stats["covered"]
                if stats["total"] > 0:
                    self.items[rule.id] = _item_from_rule(rule, stats)
                else:
                    self.items.pop(rule.id, None)

        if not ids:
            self._set(current="统计其他数据")
            self._scan_rest()
            self._tick("其他数据")
            self._set(current="查找未识别的 AI 目录")
            self._scan_unknown()
            self._tick("未识别目录")

        procs = running_processes()
        tools = []
        for t in TOOLS:
            running = sorted(p for p in t.procs if p in procs)
            tools.append({"key": t.key, "name": t.name, "color": t.color, "desc": t.desc,
                          "running": running})
        self.result = {
            "items": sorted(self.items.values(), key=lambda x: -x["total"]),
            "tools": tools,
            "priorities": {str(k): v for k, v in PRIORITIES.items()},
            "categories": CATEGORIES,
            "disk": disk_info(),
            "home": paths.home(),
            "scanned_at": time.time(),
            "elapsed": round(time.time() - self.state["started"], 1),
        }
        self._set(phase="done", current="")
        return self.result

    # ------------------------------------------------------------ 其他数据

    def _all_known_keys(self):
        keys = set()
        for cov in self.covered.values():
            keys.update(paths.norm_key(p) for p in cov)
        for t in TOOLS:
            for pat in t.roots:
                keys.update(paths.norm_key(p) for p in paths.expand(pat))
        return keys

    def _scan_rest(self):
        """各工具根目录中没有被任何规则覆盖的部分，归为“其他数据（建议保留）”。"""
        rule_keys = set()
        for cov in self.covered.values():
            rule_keys.update(paths.norm_key(p) for p in cov)
        known = self._all_known_keys()

        def work(tool):
            roots, total, files, newest, top = [], 0, 0, 0, []
            for pat in tool.roots:
                for root in paths.expand(pat):
                    rk = paths.norm_key(root)
                    if rk in rule_keys or any(paths.is_within(root, r) for r in rule_keys if r != rk
                                              and len(r) < len(rk)):
                        continue
                    roots.append(root)
                    skip = known - {rk}
                    if os.path.isdir(root) and not fsutil.is_link(root):
                        for e in fsutil.list_dir(root):
                            if paths.norm_key(e.path) in skip:
                                continue
                            s, c, m = fsutil.walk(e.path, skip=skip)
                            total += s
                            files += c
                            newest = max(newest, m)
                            if s:
                                top.append((s, e.name, m))
                    else:
                        s, c, m = fsutil.walk(root)
                        total, files, newest = total + s, files + c, max(newest, m)
            return tool, roots, total, files, newest, top

        with ThreadPoolExecutor(max_workers=6) as pool:
            for tool, roots, total, files, newest, top in pool.map(work, [t for t in TOOLS if t.roots]):
                rid = f"{tool.key}__rest"
                if total <= 0:
                    self.items.pop(rid, None)
                    continue
                top.sort(reverse=True)
                self.items[rid] = {
                    "id": rid, "tool": tool.key, "name": "其他数据", "category": "data", "priority": 4,
                    "desc": "配置、登录信息、数据库、插件、记忆等未归类数据。",
                    "impact": "本工具不会清理这部分。如需处理，请在对应软件中操作。", "note": "",
                    "mode": "keep", "age_by": None, "default_age": 0, "paths": roots,
                    "total": total, "files": files, "newest": newest,
                    "buckets": [0] * 10, "selectable": False,
                    "top": [{"name": n, "size": s, "cleanable": False, "mtime": m}
                            for s, n, m in top[:10]],
                }

    # ------------------------------------------------------------ 未识别目录

    def _scan_unknown(self):
        known = list(self._all_known_keys())
        for k in [k for k in self.items if k.startswith("unk_")]:
            del self.items[k]
        candidates = []
        seen = set()
        for pat in UNKNOWN_SCAN_DIRS:
            for base in paths.expand(pat):
                for e in fsutil.list_dir(base):
                    name = e.name.lower()
                    if not any(kw in name for kw in UNKNOWN_KEYWORDS):
                        continue
                    k = paths.norm_key(e.path)
                    if k in seen:
                        continue
                    seen.add(k)
                    # 已知路径本身、已知路径内部、或包含已知路径的目录都跳过
                    if any(k == r or k.startswith(r + os.sep) or r.startswith(k + os.sep) for r in known):
                        continue
                    candidates.append(e.path)

        def work(p):
            return p, fsutil.walk(p)

        with ThreadPoolExecutor(max_workers=6) as pool:
            for p, (size, files, newest) in pool.map(work, candidates):
                if size < UNKNOWN_MIN_SIZE:
                    continue
                rid = "unk_" + hashlib.md5(paths.norm_key(p).encode("utf-8")).hexdigest()[:10]
                self.items[rid] = {
                    "id": rid, "tool": "unknown", "name": os.path.basename(p), "category": "other",
                    "priority": 5, "desc": "名称疑似与 AI 工具相关，但不在内置规则中。",
                    "impact": "本工具不会清理。请确认是哪个软件的数据后，在该软件中清理或手动处理。",
                    "note": "", "mode": "keep", "age_by": None, "default_age": 0, "paths": [p],
                    "total": size, "files": files, "newest": newest, "buckets": [0] * 10,
                    "selectable": False, "top": [],
                }

    def path_of(self, item_id):
        it = self.items.get(item_id)
        return it["paths"] if it else []


TOOL_NAMES = {t.key: t.name for t in TOOLS}
