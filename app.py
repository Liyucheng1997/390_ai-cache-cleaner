"""AI 缓存清理 - 启动入口。

    python app.py            打开桌面窗口（需要 pywebview，否则自动用浏览器）
    python app.py --browser  用默认浏览器打开
    python app.py --report   只在终端输出扫描报告，不启动界面
    python app.py --serve --port 8765   只启动本地服务（开发调试用）
"""
import argparse
import os
import sys
import time
import webbrowser


def fmt(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def report():
    from aicleaner.rules import PRIORITIES
    from aicleaner.scanner import TOOL_NAMES, Scanner

    res = Scanner().scan()
    items = res["items"]
    print(f"扫描用时 {res['elapsed']} 秒，共发现 {len(items)} 项，合计 {fmt(sum(i['total'] for i in items))}\n")
    for pri in sorted(PRIORITIES):
        group = [i for i in items if i["priority"] == pri]
        if not group:
            continue
        print(f"== {PRIORITIES[pri]['label']}（{fmt(sum(i['total'] for i in group))}）")
        for i in group:
            steps = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365]
            age = i["default_age"] if i["age_by"] else 0
            clean = i["buckets"][max(k for k, s in enumerate(steps) if s <= age)]
            tip = f"  可清理 {fmt(clean)}" + (f"（{age} 天前）" if age else "") if i["selectable"] else ""
            print(f"  {fmt(i['total']):>10}  {TOOL_NAMES.get(i['tool'], i['tool'])} / {i['name']}{tip}")
        print()


def main():
    ap = argparse.ArgumentParser(description="AI 缓存清理")
    ap.add_argument("--browser", action="store_true", help="用浏览器打开界面")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--report", action="store_true", help="只输出扫描报告")
    ap.add_argument("--serve", action="store_true", help="只启动本地服务，不打开窗口")
    ap.add_argument("--fake-root", help="测试用：把用户目录指向这个文件夹")
    args = ap.parse_args()
    if args.fake_root:
        os.environ["AICLEAN_FAKE_ROOT"] = os.path.abspath(args.fake_root)
    if args.report:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        return report()

    from aicleaner import APP_NAME
    from aicleaner.server import serve

    _, httpd, url = serve(args.port)
    webview = None
    if not args.browser and not args.serve:
        try:
            import webview
        except ImportError:
            webview = None
    if webview:
        webview.create_window(APP_NAME, url, width=1360, height=880, min_size=(960, 640))
        webview.start()
    else:
        print(f"{APP_NAME} 已启动：{url}  （按 Ctrl+C 退出）", flush=True)
        if not args.serve:
            webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    httpd.shutdown()


if __name__ == "__main__":
    main()
