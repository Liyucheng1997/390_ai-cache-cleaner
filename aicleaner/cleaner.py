"""执行清理。只接受规则 id，具体路径一律由服务端按规则重新计算。"""
import threading
import time

from . import engine, fsutil
from .rules import RULE_MAP


class Cleaner:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"phase": "idle", "done": 0, "total": 0, "current": "", "report": None}

    def status(self):
        with self.lock:
            return dict(self.state)

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def run(self, requests, mode="recycle"):
        """requests: [{"id": 规则id, "age": 天数}]；mode: recycle 回收站 / delete 永久删除。"""
        rules = [(RULE_MAP[r["id"]], int(r.get("age") or 0)) for r in requests if r.get("id") in RULE_MAP]
        rules = [(rule, age) for rule, age in rules if rule.priority <= 3]
        self._set(phase="cleaning", done=0, total=len(rules), current="", report=None)
        report, started = [], time.time()
        for rule, age in rules:
            self._set(current=rule.name)
            res = fsutil.Result()
            blocked = 0
            try:
                trees, files, prune = engine.plan(rule, max(age, 0))
                targets = []
                for p, size in trees + files:
                    if engine.is_safe_target(p):
                        targets.append((p, size))
                    else:
                        blocked += 1
                if mode == "delete":
                    tree_set = {p for p, _ in trees}
                    for p, size in targets:
                        if p in tree_set:
                            fsutil.delete_tree(p, res)
                        else:
                            fsutil.delete_file(p, size, res)
                else:
                    fsutil.recycle(targets, res)
                for root in prune:
                    fsutil.prune_empty_dirs(root)
            except Exception as exc:  # 单项失败不影响其他项
                res.error(rule.name, exc)
            report.append({"id": rule.id, "name": rule.name, "freed": res.freed, "removed": res.removed,
                           "failed": res.failed, "blocked": blocked, "errors": res.errors})
            with self.lock:
                self.state["done"] += 1
        self._set(phase="done", current="", report={
            "items": report, "mode": mode, "elapsed": round(time.time() - started, 1),
            "freed": sum(r["freed"] for r in report), "failed": sum(r["failed"] for r in report),
        })
        return report
