"""生成一个演示用的假用户目录（demo_home），用来安全地试用清理功能。

    python tools/make_demo.py
    python app.py --fake-root demo_home --browser
"""
import os
import random
import shutil
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_home")
H = os.path.join(ROOT, "home")
L = os.path.join(H, "AppData", "Local")
A = os.path.join(H, "AppData", "Roaming")
MB = 1024 * 1024
random.seed(7)


def f(path, size, age=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fp:
        fp.truncate(int(size))
    t = time.time() - age * 86400
    os.utime(path, (t, t))


def many(base, n, size, max_age, ext=".jsonl", sub=None):
    for i in range(n):
        age = random.uniform(0, max_age)
        name = f"{i:04x}{random.randint(0, 1 << 30):08x}{ext}"
        f(os.path.join(base, sub(i) if sub else "", name), size * random.uniform(0.3, 1.7), age)


def main():
    if os.path.exists(ROOT):
        shutil.rmtree(ROOT)
    # Claude Code
    for p in ("F--work-web", "F--work-api", "C--Users-demo"):
        many(os.path.join(H, ".claude", "projects", p), 30, 0.4 * MB, 120)
        f(os.path.join(H, ".claude", "projects", p, "memory", "MEMORY.md"), 2000, 200)
    many(os.path.join(H, ".claude", "file-history"), 20, 0.3 * MB, 60, ".bak", sub=lambda i: f"s{i % 6}")
    many(os.path.join(H, ".claude", "shell-snapshots"), 15, 0.02 * MB, 10, ".sh")
    f(os.path.join(H, ".claude", "settings.json"), 900)
    f(os.path.join(H, ".claude", ".credentials.json"), 400)
    many(os.path.join(H, ".claude", "plugins"), 8, 1 * MB, 30, ".js")
    for v in ("2.1.226", "2.1.258", "2.1.310"):
        f(os.path.join(H, ".local", "share", "claude", "versions", v), 12 * MB, 30)
    many(os.path.join(L, "Temp", "claude"), 12, 1.5 * MB, 20, ".txt", sub=lambda i: f"proj{i % 4}")
    # Claude 桌面版
    cd = os.path.join(L, "Claude-Data", "claude_demo")
    many(os.path.join(cd, "Cache", "Cache_Data"), 30, 0.5 * MB, 5, "")
    many(os.path.join(cd, "Code Cache", "js"), 20, 0.3 * MB, 5, "")
    many(os.path.join(cd, "logs"), 10, 0.4 * MB, 30, ".log")
    f(os.path.join(cd, "vm_bundles", "claudevm.bundle", "rootfs.vhdx"), 60 * MB, 10)
    for v in ("2.1.304", "2.1.308"):
        f(os.path.join(cd, "claude-code", v, "claude.exe"), 9 * MB, 20)
    many(os.path.join(cd, "local-agent-mode-sessions"), 6, 2 * MB, 30, ".json")
    # Codex
    many(os.path.join(H, ".codex", "sessions"), 60, 0.35 * MB, 200, ".jsonl.zst",
         sub=lambda i: os.path.join("2026", f"{i % 10 + 1:02d}", f"{i % 27 + 1:02d}"))
    many(os.path.join(H, ".codex", "log"), 6, 0.3 * MB, 40, ".log")
    many(os.path.join(H, ".codex", "generated_images"), 10, 0.8 * MB, 90, ".png")
    f(os.path.join(H, ".codex", "thread_history_1.sqlite"), 18 * MB)
    f(os.path.join(H, ".codex", "auth.json"), 300)
    for d in ("codex-primary-runtime", "codex-primary-runtime.previous-1a2b"):
        f(os.path.join(H, ".cache", "codex-runtimes", d, "node.exe"), 8 * MB, 40)
    # Cursor
    many(os.path.join(A, "Cursor", "Cache", "Cache_Data"), 20, 0.5 * MB, 3, "")
    many(os.path.join(A, "Cursor", "CachedData"), 10, 0.6 * MB, 20, ".bin", sub=lambda i: f"c{i % 3}")
    many(os.path.join(A, "Cursor", "User", "workspaceStorage"), 24, 0.6 * MB, 150, ".vscdb", sub=lambda i: f"ws{i % 8}")
    for v in ("anysphere.cursorpyright-1.0.2", "anysphere.cursorpyright-1.0.5", "github.copilot-1.300.0"):
        f(os.path.join(H, ".cursor", "extensions", v, "dist.js"), 4 * MB, 30)
    many(os.path.join(A, "Cursor", "User", "globalStorage", "saoudrizwan.claude-dev", "checkpoints"),
         10, 1.2 * MB, 60, ".pack", sub=lambda i: f"t{i % 5}")
    # 模型与依赖
    f(os.path.join(H, ".ollama", "models", "blobs", "sha256-qwen"), 70 * MB, 90)
    f(os.path.join(H, ".ollama", "models", "blobs", "sha256-llama"), 45 * MB, 200)
    f(os.path.join(H, ".cache", "huggingface", "hub", "models--bert", "model.safetensors"), 25 * MB, 120)
    many(os.path.join(L, "npm-cache", "_npx"), 12, 1 * MB, 40, ".js", sub=lambda i: f"npx{i % 5}")
    many(os.path.join(L, "uv", "cache", "archive-v0"), 20, 1.2 * MB, 30, ".whl")
    for v in ("chromium-1140", "chromium-1155", "ffmpeg-1010"):
        f(os.path.join(L, "ms-playwright", v, "chrome.exe"), 14 * MB, 60)
    # 未识别
    f(os.path.join(A, "SuperAgent Studio", "data.bin"), 30 * MB, 10)
    print("演示目录已生成：", ROOT)


if __name__ == "__main__":
    sys.exit(main())
