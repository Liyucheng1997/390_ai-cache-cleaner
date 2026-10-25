# AI 缓存清理

重度使用 Claude Code、Codex、Cursor 这类 AI 编程工具后，C 盘会慢慢堆满会话记录、浏览器缓存、旧版本程序、MCP 依赖包和本地模型。这个工具会找出这些数据，按优先级告诉你哪些可以放心删、哪些要谨慎，然后用方块图把占用情况画出来。

- **方块图**：方块越大占用越多，按工具分组；颜色可以切换为「优先级 / 工具 / 类型」，大小可以切换为「总占用 / 可清理」。点击分组标题放大查看单个工具。
- **优先级**：
  - 🟢 **安全清理**：纯缓存，删除后会自动重新生成（浏览器缓存、npx/uv 包缓存、旧版运行环境等）
  - 🟡 **建议清理**：旧日志、旧版本程序、临时文件、编辑快照
  - 🟠 **谨慎清理**：会话历史、本地模型、Cowork 虚拟机镜像，删除后找不回或要重新下载
  - ⚪ **建议保留**：配置、登录信息、数据库、记忆，本工具不会清理
  - 🟣 **未识别**：名字像 AI 工具、但不在内置规则里的大目录，只展示不清理
- **按时间清理**：会话记录、日志等可以选「只清理 30 天前没再用过的内容」，详情里有各时间段的占用柱状图。
- **安全**：默认移到回收站；不跟随符号链接和目录联接；配置、密钥类文件名一律跳过；只删除规则允许的路径；检测到对应软件正在运行时会提醒先退出。

## 使用

直接运行打包好的 `dist\AICacheCleaner.exe`。

从源码运行（需要 Python 3.10+）：

```bash
python app.py
```

或双击 `启动.bat`。其他参数：

```bash
python app.py --browser
```

```bash
python app.py --report
```

`--browser` 用默认浏览器打开界面；`--report` 只在终端输出扫描报告，不启动界面，也不会删除任何东西。

## 能识别的工具

| 工具 | 主要内容 |
| --- | --- |
| Claude Code | 会话记录（projects）、文件编辑快照、调试日志、Shell 快照、MCP 日志、旧版本程序、临时草稿区 |
| Claude 桌面版 | 浏览器缓存、日志、内置 Claude Code 旧版本、Cowork 虚拟机镜像、MSIX 沙盒内工具缓存 |
| Codex | 会话记录（含 .jsonl.zst）、已归档会话、日志、临时文件、旧版运行环境、生成的图片、工作树、桌面版缓存 |
| Cursor / Windsurf / Trae / Kiro / Qoder / Antigravity / VS Code | 编辑器缓存、日志、工作区存储、本地文件历史、扩展旧版本、Cline / Roo Code / Kilo Code 任务与检查点 |
| Gemini CLI、Copilot CLI、OpenCode、Continue、Aider、Qwen Code | 会话、检查点、日志、缓存 |
| Ollama、LM Studio、Hugging Face、PyTorch、ModelScope 等 | 本地模型、更新安装包、编译缓存 |
| MCP / 依赖缓存 | npx 临时包、npm / uv / pip / pnpm / bun 缓存、Playwright / Puppeteer 旧版浏览器、conda 安装包 |

每个工具根目录里没被规则覆盖的部分，会显示为灰色的「其他数据（建议保留）」，方便你看清到底是什么在占空间。

## 添加或修改规则

规则都在 [aicleaner/rules.py](aicleaner/rules.py)。每条规则写明路径、所属工具、类型、优先级和清理方式（`contents` 清空目录内容 / `whole` 删除匹配项 / `files` 按文件名删除 / `old_versions` 只保留最新版本），以及是否按时间筛选。改完运行测试：

```bash
python -m unittest discover -s tests -v
```

测试在临时的假用户目录里进行，其中一项会检查所有规则之间没有路径重叠（避免重复统计）。

想安全地试用清理功能，可以生成一个演示目录：

```bash
python tools/make_demo.py
```

```bash
python app.py --fake-root demo_home
```

## 打包

```bash
build.bat
```

生成 `dist\AICacheCleaner.exe`（PyInstaller 单文件，界面使用 pywebview + 系统自带的 WebView2）。

## 结构

```
app.py               启动入口
aicleaner/
  rules.py           工具与规则定义
  engine.py          规则展开、扫描统计、清理计划、安全检查
  scanner.py         并行扫描、其他数据统计、未识别目录发现、进程检测
  cleaner.py         执行清理（回收站 / 永久删除）
  fsutil.py          目录遍历、删除、回收站（不跟随链接）
  server.py          本地 HTTP 服务（仅 127.0.0.1，随机令牌校验）
web/                 界面（原生 HTML/CSS/JS，无外部依赖）
tests/               单元测试
tools/make_demo.py   生成演示目录
```
