"""在临时的假用户目录里测试扫描和清理，不会碰到真实数据。

    python -m unittest discover -s tests -v
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DAY = 86400


def write(path, size=1000, age_days=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)
    t = time.time() - age_days * DAY
    os.utime(path, (t, t))


class FakeHome(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aiclean-test-")
        os.environ["AICLEAN_FAKE_ROOT"] = self.root
        self.home = os.path.join(self.root, "home")
        self.local = os.path.join(self.home, "AppData", "Local")
        self.roaming = os.path.join(self.home, "AppData", "Roaming")
        os.makedirs(self.local)
        os.makedirs(self.roaming)

    def tearDown(self):
        os.environ.pop("AICLEAN_FAKE_ROOT", None)
        shutil.rmtree(self.root, ignore_errors=True)

    def h(self, *parts):
        return os.path.join(self.home, *parts)

    def clean(self, rule_id, age=None, mode="delete"):
        from aicleaner.cleaner import Cleaner
        from aicleaner.rules import RULE_MAP
        age = RULE_MAP[rule_id].age if age is None else age
        return Cleaner().run([{"id": rule_id, "age": age}], mode)[0]


class TestRules(FakeHome):
    def test_claude_projects_keeps_memory_and_recent(self):
        proj = self.h(".claude", "projects", "F--demo")
        write(os.path.join(proj, "old.jsonl"), 500, age_days=60)
        write(os.path.join(proj, "new.jsonl"), 500, age_days=1)
        write(os.path.join(proj, "12345678-1234-1234-1234-123456789012", "subagents", "a.jsonl"), 300, 90)
        write(os.path.join(proj, "memory", "MEMORY.md"), 100, age_days=400)
        write(os.path.join(proj, "notes.txt"), 100, age_days=400)  # 不匹配 pattern，保留

        from aicleaner import engine
        from aicleaner.rules import RULE_MAP
        stats = engine.scan_rule(RULE_MAP["cc_projects"])
        self.assertEqual(stats["total"], 1500)
        self.assertEqual(stats["buckets"][0], 1300)   # 不限时间：全部会话
        self.assertEqual(stats["buckets"][5], 800)    # 30 天前

        r = self.clean("cc_projects", age=30)
        self.assertEqual(r["freed"], 800)
        self.assertFalse(os.path.exists(os.path.join(proj, "old.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(proj, "new.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(proj, "memory", "MEMORY.md")))
        self.assertTrue(os.path.exists(os.path.join(proj, "notes.txt")))

    def test_old_versions_keep_newest(self):
        vdir = self.h(".local", "share", "claude", "versions")
        for v in ("2.1.9", "2.1.10", "2.0.99"):
            write(os.path.join(vdir, v), 100)
        r = self.clean("cc_versions")
        self.assertEqual(sorted(os.listdir(vdir)), ["2.1.10"])
        self.assertEqual(r["freed"], 200)

    def test_extension_versions_grouped(self):
        ext = self.h(".vscode", "extensions")
        for name in ("github.copilot-1.2.0", "github.copilot-1.10.0", "ms-python.python-2026.4.0-win32-x64",
                     "anthropic.claude-code-2.0.1"):
            write(os.path.join(ext, name, "package.json"), 50)
        write(os.path.join(ext, "extensions.json"), 10)
        self.clean("vscode_ext_old")
        self.assertEqual(sorted(os.listdir(ext)), ["anthropic.claude-code-2.0.1", "extensions.json",
                                                   "github.copilot-1.10.0",
                                                   "ms-python.python-2026.4.0-win32-x64"])

    def test_codex_sessions_by_file_age(self):
        s = self.h(".codex", "sessions", "2026")
        write(os.path.join(s, "01", "05", "rollout-a.jsonl.zst"), 400, age_days=200)
        write(os.path.join(s, "10", "20", "rollout-b.jsonl"), 400, age_days=2)
        write(os.path.join(s, "10", "20", "keep.sqlite"), 400, age_days=200)
        r = self.clean("cx_sessions", age=30)
        self.assertEqual(r["freed"], 400)
        self.assertFalse(os.path.exists(os.path.join(s, "01")))  # 空目录被清掉
        self.assertTrue(os.path.exists(os.path.join(s, "10", "20", "rollout-b.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(s, "10", "20", "keep.sqlite")))

    def test_chromium_cache_contents_only(self):
        base = os.path.join(self.roaming, "Cursor")
        write(os.path.join(base, "Cache", "Cache_Data", "f_0001"), 700)
        write(os.path.join(base, "User", "settings.json"), 10)
        self.clean("cursor_cache")
        self.assertTrue(os.path.isdir(os.path.join(base, "Cache")))
        self.assertEqual(os.listdir(os.path.join(base, "Cache")), [])
        self.assertTrue(os.path.exists(os.path.join(base, "User", "settings.json")))

    def test_junction_target_survives(self):
        import _winapi
        outside = os.path.join(self.root, "outside")
        write(os.path.join(outside, "precious.bin"), 999)
        npx = os.path.join(self.local, "npm-cache", "_npx")
        write(os.path.join(npx, "abc", "node_modules", "x.js"), 100, age_days=30)
        link = os.path.join(npx, "abc", "node_modules", "linked")
        _winapi.CreateJunction(outside, link)
        os.utime(os.path.join(npx, "abc"), (time.time() - 30 * DAY,) * 2)
        self.clean("npx", age=0)
        self.assertTrue(os.path.exists(os.path.join(outside, "precious.bin")))
        self.assertFalse(os.path.exists(os.path.join(npx, "abc")))

    def test_safety_guard(self):
        from aicleaner import engine
        self.assertFalse(engine.is_safe_target(self.home))
        self.assertFalse(engine.is_safe_target(self.local))
        self.assertFalse(engine.is_safe_target(self.roaming))
        os.makedirs(self.h(".claude"), exist_ok=True)
        self.assertFalse(engine.is_safe_target(self.h(".claude")))   # 用户目录下第一层文件夹
        self.assertTrue(engine.is_safe_target(self.h(".claude", "debug")))
        self.assertFalse(engine.is_safe_target(os.path.join(self.root, "elsewhere", "a", "b")))

    def test_protected_names_skipped(self):
        write(self.h(".claude", "cache", "settings.json"), 10)
        write(self.h(".claude", "cache", "changelog.md"), 10)
        self.clean("cc_cache")
        self.assertTrue(os.path.exists(self.h(".claude", "cache", "settings.json")))
        self.assertFalse(os.path.exists(self.h(".claude", "cache", "changelog.md")))

    def test_keep_priority_rules_never_cleaned(self):
        from aicleaner.cleaner import Cleaner
        write(self.h(".codex", "auth.json"), 10)
        report = Cleaner().run([{"id": "codex__rest", "age": 0}], "delete")
        self.assertEqual(report, [])
        self.assertTrue(os.path.exists(self.h(".codex", "auth.json")))

    def test_rest_not_double_counted(self):
        from aicleaner.scanner import Scanner
        write(self.h(".codex", "log", "codex-tui.log"), 300, age_days=10)
        write(self.h(".codex", "state_5.sqlite"), 5000)
        write(self.h(".gemini", "tmp", "abc", "chat.json"), 200, age_days=40)
        write(self.h(".gemini", "antigravity", "conversations", "c1.pb"), 800, age_days=90)
        write(self.h(".gemini", "settings.json"), 7)
        res = Scanner().scan()
        by_id = {i["id"]: i for i in res["items"]}
        self.assertEqual(by_id["cx_logs"]["total"], 300)
        self.assertEqual(by_id["codex__rest"]["total"], 5000)
        self.assertEqual(by_id["gm_tmp"]["total"], 200)
        self.assertEqual(by_id["ag_conversations"]["total"], 800)
        self.assertEqual(by_id["gemini__rest"]["total"], 7)
        self.assertEqual(sum(i["total"] for i in res["items"]), 300 + 5000 + 200 + 800 + 7)

    def test_unknown_ai_folder_detected(self):
        from aicleaner import rules
        from aicleaner.scanner import Scanner
        old = rules.UNKNOWN_MIN_SIZE
        import aicleaner.scanner as sc
        sc.UNKNOWN_MIN_SIZE = 100
        try:
            write(os.path.join(self.roaming, "SuperLLM Studio", "blob.bin"), 500)
            write(os.path.join(self.roaming, "Photoshop", "blob.bin"), 500)
            res = Scanner().scan()
            names = [i["name"] for i in res["items"] if i["priority"] == 5]
            self.assertEqual(names, ["SuperLLM Studio"])
        finally:
            sc.UNKNOWN_MIN_SIZE = old

    def test_no_overlapping_rules(self):
        """任意两条规则覆盖的路径不能互相包含，否则会重复统计。"""
        from aicleaner import engine, paths
        from aicleaner.rules import RULES
        for r in RULES:  # 为每条规则造出它的路径
            for p in r.paths:
                q = paths.expand_one(p).replace("*", "x")
                if r.mode in ("files", "old_versions") or r.mode == "contents":
                    os.makedirs(q, exist_ok=True)
                else:
                    write(q, 1)
        cov = []
        for r in RULES:
            _, c = engine.units(r)
            cov += [(paths.norm_key(p), r.id) for p in c]
        for a, ra in cov:
            for b, rb in cov:
                if ra != rb:
                    self.assertFalse(a == b or a.startswith(b + os.sep), f"{ra} 与 {rb} 重叠: {a}")


class TestVersionParse(unittest.TestCase):
    def test_parse(self):
        from aicleaner.engine import parse_version
        self.assertEqual(parse_version("2.1.304"), ("", (2, 1, 304)))
        self.assertEqual(parse_version("github.copilot-chat-0.30.3"), ("github.copilot-chat", (0, 30, 3)))
        self.assertEqual(parse_version("chromium-1140"), ("chromium", (1140,)))
        self.assertEqual(parse_version("chromium_headless_shell-1140")[0], "chromium_headless_shell")
        self.assertEqual(parse_version("devsense.composer-php-vscode-1.70.18851-universal"),
                         ("devsense.composer-php-vscode", (1, 70, 18851)))
        self.assertEqual(parse_version("app-0.9.1"), ("app", (0, 9, 1)))
        self.assertIsNone(parse_version("extensions.json"))
        self.assertIsNone(parse_version("claudevm.bundle"))


if __name__ == "__main__":
    unittest.main()
