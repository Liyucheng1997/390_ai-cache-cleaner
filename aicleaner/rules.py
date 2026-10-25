"""AI 工具缓存识别规则。

每条规则描述一类数据：在哪里、属于哪个工具、是什么类型、清理优先级、怎么清理。

清理方式 mode：
  contents      清空目录里的内容，保留目录本身（pattern 可只挑选部分子项）
  whole         删除匹配到的路径本身（常配合通配符清理残留目录/文件）
  files         递归删除目录里匹配 pattern 的文件
  old_versions  目录里按“名称-版本号”分组，每组只保留最新版本

按时间筛选 age_by：
  None    不按时间筛选，全部清理
  "file"  逐个文件比较修改时间
  "entry" 以每个顶层子项（如一个会话目录）里最新的文件时间为准，整项保留或删除
"""
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 优先级与类型

PRIORITIES = {
    1: {"label": "安全清理", "desc": "纯缓存，删除后会自动重新生成"},
    2: {"label": "建议清理", "desc": "旧日志、旧版本、临时文件，清理基本无影响"},
    3: {"label": "谨慎清理", "desc": "会话历史、模型等，删除后无法找回或需重新下载"},
    4: {"label": "建议保留", "desc": "配置、登录信息、数据库等，本工具不会清理"},
    5: {"label": "未识别", "desc": "疑似 AI 相关的大目录，需要你自己确认"},
}

CATEGORIES = {
    "cache": "缓存",
    "log": "日志",
    "session": "会话记录",
    "checkpoint": "快照与回退",
    "temp": "临时文件",
    "version": "旧版本",
    "runtime": "运行环境",
    "model": "模型文件",
    "package": "依赖包",
    "crash": "崩溃转储",
    "data": "用户数据",
    "other": "其他数据",
}

AGE_STEPS = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365]


@dataclass
class Tool:
    key: str
    name: str
    color: str
    roots: list = field(default_factory=list)   # 用于统计“其他数据（保留）”
    procs: list = field(default_factory=list)   # 进程名（小写），运行时提示先关闭
    desc: str = ""


@dataclass
class Rule:
    id: str
    tool: str
    name: str
    paths: list
    category: str
    priority: int
    desc: str
    impact: str = ""
    mode: str = "contents"
    pattern: tuple = ()
    exclude: tuple = ()
    age_by: str = None
    age: int = 0
    max_depth: int = None
    note: str = ""


def chromium_caches(base):
    """Electron / Chromium 应用的可再生缓存子目录。"""
    subs = [
        "Cache", "Code Cache", "GPUCache", "GrShaderCache", "GraphiteDawnCache",
        "GPUPersistentCache", "ShaderCache", "DawnGraphiteCache", "DawnWebGPUCache",
        "Service Worker/CacheStorage", "Service Worker/ScriptCache", "component_crx_cache",
        "Default/Cache", "Default/Code Cache", "Default/GPUCache", "Default/DawnGraphiteCache",
        "Default/DawnWebGPUCache", "Default/Service Worker/CacheStorage",
        "Default/Service Worker/ScriptCache", "Partitions/*/Cache", "Partitions/*/Code Cache",
        "Partitions/*/GPUCache",
    ]
    return [f"{base}/{s}" for s in subs]


# ---------------------------------------------------------------- 工具

TOOLS = [
    Tool("claude_code", "Claude Code", "#d97757",
         ["~/.claude", "~/.local/share/claude", "~/.cache/claude",
          "%LOCALAPPDATA%/claude-cli-nodejs", "%TEMP%/claude"],
         ["claude.exe"], "Anthropic 的命令行编程助手"),
    Tool("claude_desktop", "Claude 桌面版", "#a8674d",
         ["%LOCALAPPDATA%/Claude-Data/*", "%APPDATA%/Claude", "%LOCALAPPDATA%/Claude",
          "%LOCALAPPDATA%/AnthropicClaude", "%LOCALAPPDATA%/Packages/Claude_*"],
         ["claude.exe"], "Claude 桌面应用（含 Cowork 与内置 Claude Code）"),
    Tool("codex", "Codex", "#10a37f",
         ["~/.codex", "~/.cache/codex-runtimes", "%LOCALAPPDATA%/Packages/OpenAI.Codex_*",
          "%LOCALAPPDATA%/OpenAI/Codex"],
         ["codex.exe"], "OpenAI 的编程助手（CLI / 桌面版）"),
    Tool("chatgpt", "ChatGPT 桌面版", "#5aa889",
         ["%LOCALAPPDATA%/Packages/OpenAI.ChatGPT-Desktop_*"], ["chatgpt.exe"]),
    Tool("cursor", "Cursor", "#4e79a7", ["%APPDATA%/Cursor", "~/.cursor"], ["cursor.exe"]),
    Tool("windsurf", "Windsurf", "#59a5d8",
         ["%APPDATA%/Windsurf", "~/.windsurf", "~/.codeium"], ["windsurf.exe"]),
    Tool("trae", "Trae", "#e15759",
         ["%APPDATA%/Trae", "%APPDATA%/Trae CN", "~/.trae", "~/.trae-cn"],
         ["trae.exe", "trae cn.exe"]),
    Tool("kiro", "Kiro", "#9467bd", ["%APPDATA%/Kiro", "~/.kiro"], ["kiro.exe"]),
    Tool("qoder", "Qoder", "#2ca089", ["%APPDATA%/Qoder", "~/.qoder"], ["qoder.exe"]),
    Tool("antigravity", "Antigravity", "#4285f4",
         ["%APPDATA%/Antigravity", "~/.antigravity", "~/.gemini/antigravity",
          "~/.gemini/antigravity-browser-profile"], ["antigravity.exe"]),
    Tool("gemini", "Gemini CLI", "#8ab4f8", ["~/.gemini"], []),
    Tool("vscode", "VS Code", "#007acc", ["%APPDATA%/Code", "~/.vscode"], ["code.exe"],
         "含 Copilot、Cline、Roo Code 等 AI 插件"),
    Tool("copilot", "GitHub Copilot", "#6e40c9",
         ["~/.copilot", "%LOCALAPPDATA%/github-copilot",
          "%LOCALAPPDATA%/Packages/Microsoft.Copilot_*"], ["copilot.exe"]),
    Tool("opencode", "OpenCode", "#f28e2b",
         ["~/.local/share/opencode", "~/.cache/opencode", "%APPDATA%/ai.opencode.desktop",
          "%LOCALAPPDATA%/ai.opencode.desktop"],
         ["opencode.exe"]),
    Tool("other_ai", "其他 AI 工具", "#ff9da7", ["~/.continue", "~/.aider", "~/.qwen"], []),
    Tool("ollama", "Ollama", "#6b6b6b", ["~/.ollama", "%LOCALAPPDATA%/Ollama", "%APPDATA%/ollama app.exe"],
         ["ollama.exe", "ollama app.exe"], "本地大模型运行工具"),
    Tool("lmstudio", "LM Studio", "#6a5acd",
         ["~/.lmstudio", "~/.cache/lm-studio", "%APPDATA%/LM Studio"], ["lm studio.exe"]),
    Tool("model_hub", "模型缓存", "#b07aa1",
         ["~/.cache/huggingface", "~/.cache/torch", "~/.cache/modelscope", "~/.cache/whisper",
          "~/.u2net", "~/.paddlex", "~/.cache/paddle", "%LOCALAPPDATA%/torch_extensions"], [],
         "Hugging Face、PyTorch、ModelScope 等下载的模型"),
    Tool("dev_cache", "MCP / 依赖缓存", "#d4a72c", [], ["node.exe", "uv.exe", "uvx.exe"],
         "MCP 服务器和 AI 工具依赖的 npm / uv / pip / Playwright 等缓存"),
    Tool("system", "崩溃转储", "#9c755f", [], []),
    Tool("unknown", "未识别目录", "#8e8ec4", [], []),
]
TOOL_MAP = {t.key: t for t in TOOLS}

# ---------------------------------------------------------------- 规则

R = Rule
CD = "%LOCALAPPDATA%/Claude-Data/*"  # Claude 桌面版数据目录（子目录名因安装而异）
CD_BASES = [CD, "%APPDATA%/Claude", "%LOCALAPPDATA%/Packages/Claude_*/LocalCache/Roaming/Claude"]
CODEX_PKG = "%LOCALAPPDATA%/Packages/OpenAI.Codex_*/LocalCache/Roaming/Codex"
CLAUDE_VENDOR_NOTE = ("Claude 官方建议优先在应用内清理：设置 > 此电脑 > 系统 > 存储，"
                      "或 帮助 > 故障排除 > 清除缓存并重启。在这里清理前请先完全退出 Claude。")

RULES = [
    # ------------------------------------------------ Claude Code
    R("cc_projects", "claude_code", "会话记录（projects）", ["~/.claude/projects/*"], "session", 3,
      "每次对话的完整记录（JSONL），用于 /resume 继续旧会话、回看历史。",
      "删除后这些旧会话无法再 /resume。各项目的 memory 记忆文件夹不会被删除。",
      pattern=("*.jsonl", "????????-????-????-????-????????????"), exclude=("memory",),
      age_by="entry", age=30),
    R("cc_file_history", "claude_code", "文件编辑快照", ["~/.claude/file-history"], "checkpoint", 2,
      "Claude Code 修改文件前保存的备份，用于 /rewind 回退代码。",
      "旧会话将无法回退到修改前的版本。", age_by="entry", age=14),
    R("cc_shell", "claude_code", "Shell 环境快照", ["~/.claude/shell-snapshots"], "temp", 1,
      "启动会话时记录的 Shell 环境，每次会话都会重新生成。", "无影响。", age_by="entry", age=1),
    R("cc_debug", "claude_code", "调试日志", ["~/.claude/debug"], "log", 1,
      "Claude Code 的调试输出日志。", "无影响。", age_by="entry", age=1),
    R("cc_todos", "claude_code", "任务清单记录", ["~/.claude/todos"], "session", 2,
      "历史会话中的 Todo 任务列表。", "旧会话的任务清单不再显示。", age_by="entry", age=30),
    R("cc_session_env", "claude_code", "会话环境", ["~/.claude/session-env"], "temp", 2,
      "每个会话的环境变量记录。", "基本无影响。", age_by="entry", age=7),
    R("cc_cache", "claude_code", "通用缓存",
      ["~/.claude/cache", "~/.claude/statsig", "~/.claude/telemetry", "~/.claude/paste-cache",
       "~/.claude/image-cache"], "cache", 1,
      "更新日志、模型目录、功能开关、粘贴内容等缓存。", "会自动重新生成。"),
    R("cc_backups", "claude_code", "配置备份",
      ["~/.claude/backups/*", "~/.claude.json.backup*"], "other", 2,
      "Claude Code 自动保存的 .claude.json 历史备份。", "仅保留当前配置，无法再回滚到旧备份。",
      mode="whole", age_by="entry", age=7),
    R("cc_versions", "claude_code", "旧版本程序", ["~/.local/share/claude/versions"], "version", 2,
      "原生安装版自动更新后留下的旧版本程序（每个约 200 MB）。", "保留最新版本，旧版本被删除。",
      mode="old_versions"),
    R("cc_staging", "claude_code", "更新下载缓存", ["~/.cache/claude/staging"], "temp", 1,
      "自动更新时下载的临时安装包。", "无影响。"),
    R("cc_mcp_logs", "claude_code", "MCP 日志", ["%LOCALAPPDATA%/claude-cli-nodejs/Cache"], "log", 1,
      "各项目 MCP 服务器的运行日志。", "无影响。", age_by="file", age=3),
    R("cc_temp", "claude_code", "临时草稿区", ["%TEMP%/claude"], "temp", 2,
      "会话使用的临时目录（scratchpad）和后台任务输出。", "仅删除较早的会话目录，正在进行的会话不受影响。",
      age_by="entry", age=3),

    # ------------------------------------------------ Claude 桌面版
    R("cd_cache", "claude_desktop", "浏览器缓存",
      sum((chromium_caches(b) for b in CD_BASES), []), "cache", 2,
      "桌面应用内置浏览器（Electron）的网页、代码和 GPU 缓存。", "下次打开会稍慢，缓存会重新生成。",
      note=CLAUDE_VENDOR_NOTE),
    R("cd_cache_backup", "claude_desktop", "缓存残留备份", [f"{CD}/*.backup-*"], "cache", 2,
      "之前修复/清理缓存时留下的备份目录。", "无影响。", mode="whole", note=CLAUDE_VENDOR_NOTE),
    R("cd_logs", "claude_desktop", "日志",
      [f"{CD}/logs", "%LOCALAPPDATA%/Claude/logs", "%APPDATA%/Claude/logs"], "log", 1,
      "桌面应用与 MCP 服务器的运行日志。", "无影响。", age_by="file", age=7),
    R("cd_crash", "claude_desktop", "崩溃报告", [f"{CD}/Crashpad", f"{CD}/sentry"], "crash", 1,
      "崩溃转储和错误上报缓存。", "无影响。"),
    R("cd_code_bins", "claude_desktop", "内置 Claude Code 旧版本",
      [f"{CD}/claude-code", f"{CD}/claude-code-vm"], "version", 2,
      "桌面版自动下载的 Claude Code 程序，每次更新会留下旧版本。", "保留最新版本。",
      mode="old_versions", note=CLAUDE_VENDOR_NOTE),
    R("cd_msix_caches", "claude_desktop", "沙盒内工具缓存",
      [f"%LOCALAPPDATA%/Packages/Claude_*/LocalCache/Local/{d}" for d in
       ("claude-cli-nodejs", "node-gyp", "electron-builder", "electron", "npm-cache", "pip", "uv",
        "pnpm-cache", "ms-playwright", "ffmpeg-static-nodejs", "Temp")], "cache", 2,
      "Claude 桌面版是 MSIX 应用，在它里面运行的 npm、node-gyp、Playwright 等工具写入的缓存会被重定向到这里。",
      "这些工具下次运行时会重新下载。"),
    R("cd_vm", "claude_desktop", "Cowork 虚拟机镜像", [f"{CD}/vm_bundles"], "runtime", 3,
      "Cowork 功能运行所需的虚拟机镜像，体积通常为数 GB。", "下次使用 Cowork 时会重新下载。",
      note=CLAUDE_VENDOR_NOTE),
    R("cd_squirrel", "claude_desktop", "旧版安装文件",
      ["%LOCALAPPDATA%/AnthropicClaude"], "version", 1,
      "旧版安装器保留的历史版本目录（app-x.y.z）。", "保留最新版本。", mode="old_versions"),
    R("cd_nupkg", "claude_desktop", "安装包缓存", ["%LOCALAPPDATA%/AnthropicClaude/packages/*.nupkg"],
      "version", 1, "自动更新下载的安装包。", "无影响。", mode="whole"),

    # ------------------------------------------------ Codex
    R("cx_sessions", "codex", "会话记录（sessions）", ["~/.codex/sessions"], "session", 3,
      "每次会话的 rollout 记录（JSONL），用于 codex resume 和历史查看。",
      "删除后这些旧会话无法再恢复或查看。", mode="files", pattern=("*.jsonl", "*.jsonl.zst"),
      age_by="file", age=30),
    R("cx_archived", "codex", "已归档会话", ["~/.codex/archived_sessions"], "session", 2,
      "你已经归档的旧会话记录。", "归档列表中的会话将无法打开。", mode="files",
      pattern=("*.jsonl", "*.jsonl.zst"), age_by="file", age=30),
    R("cx_logs", "codex", "日志", ["~/.codex/log", "~/.codex/*.log"], "log", 1,
      "Codex 的运行日志与沙箱日志。", "无影响。", mode="whole", age_by="file", age=7),
    R("cx_tmp", "codex", "临时文件",
      ["~/.codex/tmp/*", "~/.codex/.tmp/git-*", "~/.codex/..codex-global-state.json.*"], "temp", 1,
      "运行过程中的临时目录、临时 git 克隆和写入失败留下的临时状态文件。", "无影响。",
      mode="whole", age_by="entry", age=1),
    R("cx_cache", "codex", "缓存", ["~/.codex/cache"], "cache", 1, "Codex 的通用缓存。", "会自动重新生成。"),
    R("cx_worktrees", "codex", "任务工作树", ["~/.codex/worktrees"], "checkpoint", 3,
      "Codex 为后台任务创建的 git worktree，可能含有尚未合并的修改。",
      "未合并的修改会丢失，请先确认任务已完成。", age_by="entry", age=14),
    R("cx_images", "codex", "生成的图片", ["~/.codex/generated_images"], "data", 3,
      "你让 Codex 生成的图片。", "图片会被删除，请先把需要的另存。", age_by="entry", age=30),
    R("cx_runtimes", "codex", "旧版运行环境",
      ["~/.cache/codex-runtimes/*.previous-*", "~/.cache/codex-runtimes/codex-runtime-install-*"],
      "version", 1, "升级后保留的上一版运行环境和未完成的安装目录。", "无影响。", mode="whole"),
    R("cx_desktop_cache", "codex", "桌面版浏览器缓存",
      chromium_caches(f"{CODEX_PKG}/web/Codex") + chromium_caches(CODEX_PKG), "cache", 1,
      "Codex 桌面版内置浏览器的网页、代码和 GPU 缓存。", "下次打开会稍慢，缓存会重新生成。"),
    R("cx_desktop_crash", "codex", "桌面版崩溃报告", [f"{CODEX_PKG}/web/Codex/Crashpad"], "crash", 1,
      "崩溃转储。", "无影响。"),

    # ------------------------------------------------ ChatGPT
    R("gpt_cache", "chatgpt", "浏览器缓存",
      chromium_caches("%LOCALAPPDATA%/Packages/OpenAI.ChatGPT-Desktop_*/LocalCache/Roaming/ChatGPT"),
      "cache", 1, "ChatGPT 桌面版的网页与 GPU 缓存。", "会自动重新生成。"),

    # ------------------------------------------------ Antigravity / Gemini
    R("ag_recordings", "antigravity", "浏览器操作录像", ["~/.gemini/antigravity/browser_recordings"],
      "data", 2, "Agent 操作浏览器时录制的视频/截图。", "旧任务的录像无法回看。", age_by="entry", age=14),
    R("ag_conversations", "antigravity", "对话记录", ["~/.gemini/antigravity/conversations"],
      "session", 3, "Agent 的历史对话数据。", "旧对话无法再打开。", age_by="entry", age=60),
    R("ag_browser_cache", "antigravity", "Agent 浏览器缓存",
      chromium_caches("~/.gemini/antigravity-browser-profile"), "cache", 1,
      "Agent 专用浏览器的网页缓存。", "会自动重新生成，登录状态不受影响。"),
    R("gm_tmp", "gemini", "项目临时数据", ["~/.gemini/tmp"], "session", 2,
      "Gemini CLI 为每个项目保存的检查点、聊天记录和日志。", "旧项目的检查点和聊天记录会丢失。",
      exclude=("bin",), age_by="entry", age=30),

    # ------------------------------------------------ Copilot / OpenCode / 其他
    R("cp_sessions", "copilot", "Copilot CLI 会话", ["~/.copilot/session-state"], "session", 3,
      "Copilot CLI 的历史会话。", "旧会话无法恢复。", age_by="entry", age=30),
    R("cp_logs", "copilot", "Copilot CLI 日志", ["~/.copilot/logs"], "log", 1, "运行日志。", "无影响。",
      age_by="file", age=7),
    R("oc_log", "opencode", "日志", ["~/.local/share/opencode/log"], "log", 1, "运行日志。", "无影响。",
      age_by="file", age=7),
    R("oc_snapshot", "opencode", "代码快照", ["~/.local/share/opencode/snapshot"], "checkpoint", 2,
      "OpenCode 用于撤销修改的 git 快照。", "旧项目无法再撤销到快照。", age_by="entry", age=14),
    R("oc_ui_cache", "opencode", "桌面版界面缓存",
      chromium_caches("%LOCALAPPDATA%/ai.opencode.desktop/EBWebView"), "cache", 1,
      "OpenCode 桌面版（WebView2）的网页缓存。", "会自动重新生成。"),
    R("oc_modules", "opencode", "自动安装的依赖", ["~/.cache/opencode/node_modules"], "package", 1,
      "按需安装的模型提供商 SDK。", "下次使用时自动重新安装。", mode="whole"),
    R("ct_index", "other_ai", "Continue 代码索引", ["~/.continue/index"], "cache", 1,
      "Continue 插件的代码库索引。", "下次会重新建立索引。"),
    R("ct_sessions", "other_ai", "Continue 会话", ["~/.continue/sessions"], "session", 3,
      "Continue 插件的聊天记录。", "旧聊天记录会丢失。", age_by="entry", age=30),
    R("ct_logs", "other_ai", "Continue 日志", ["~/.continue/logs"], "log", 1, "运行日志。", "无影响。"),
    R("aider_cache", "other_ai", "Aider 缓存", ["~/.aider/caches"], "cache", 1,
      "Aider 的代码地图等缓存。", "会自动重新生成。"),
    R("qwen_tmp", "other_ai", "Qwen Code 临时数据", ["~/.qwen/tmp"], "session", 2,
      "Qwen Code 的项目检查点与日志。", "旧检查点会丢失。", age_by="entry", age=30),

    # ------------------------------------------------ 本地模型
    R("ol_models", "ollama", "本地模型", ["~/.ollama/models"], "model", 3,
      "通过 ollama pull 下载的大模型文件。", "所有模型都会被删除，需要时重新下载。",
      note="建议在终端用 ollama list 查看、ollama rm <模型名> 只删除不用的模型。"),
    R("ol_logs", "ollama", "日志", ["%LOCALAPPDATA%/Ollama/*.log"], "log", 1, "服务运行日志。", "无影响。",
      mode="whole"),
    R("ol_updates", "ollama", "更新安装包", ["%LOCALAPPDATA%/Ollama/updates", "%LOCALAPPDATA%/Ollama/updates_v2"],
      "version", 1,
      "自动更新下载的安装包。", "无影响。"),
    R("ol_ui_cache", "ollama", "界面缓存", chromium_caches("%APPDATA%/ollama app.exe/EBWebView"), "cache", 1,
      "Ollama 桌面界面（WebView2）的网页缓存。", "会自动重新生成。"),
    R("ol_cache", "ollama", "缓存", ["~/.ollama/cache"], "cache", 2, "Ollama 的运行缓存。", "会自动重新生成。"),
    R("lm_models", "lmstudio", "本地模型", ["~/.lmstudio/models", "~/.cache/lm-studio/models"], "model", 3,
      "LM Studio 下载的大模型文件。", "需要时重新下载。", note="建议在 LM Studio 的“我的模型”中按需删除。"),
    R("lm_logs", "lmstudio", "服务日志", ["~/.lmstudio/server-logs", "~/.cache/lm-studio/server-logs"],
      "log", 1, "本地服务器日志。", "无影响。", age_by="file", age=7),
    R("lm_cache", "lmstudio", "浏览器缓存", chromium_caches("%APPDATA%/LM Studio"), "cache", 1,
      "应用界面缓存。", "会自动重新生成。"),
    R("hf_hub", "model_hub", "Hugging Face 模型",
      ["~/.cache/huggingface/hub", "~/.cache/huggingface/datasets"], "model", 3,
      "transformers / diffusers 等下载的模型和数据集。", "需要时重新下载，可能很慢。",
      note="可用 huggingface-cli delete-cache 按模型选择删除。"),
    R("hf_xet", "model_hub", "Hugging Face 分块缓存", ["~/.cache/huggingface/xet"], "cache", 1,
      "下载加速用的分块缓存。", "无影响。"),
    R("torch_hub", "model_hub", "PyTorch 模型", ["~/.cache/torch/hub"], "model", 3,
      "torch.hub 下载的预训练权重。", "需要时重新下载。"),
    R("torch_kernels", "model_hub", "PyTorch 编译缓存",
      ["~/.cache/torch/kernels", "%LOCALAPPDATA%/torch_extensions"], "cache", 2,
      "自定义算子与内核的编译结果。", "下次运行时重新编译。"),
    R("ms_models", "model_hub", "ModelScope 模型", ["~/.cache/modelscope"], "model", 3,
      "魔搭社区下载的模型。", "需要时重新下载。"),
    R("misc_models", "model_hub", "其他模型权重",
      ["~/.cache/whisper", "~/.u2net", "~/.paddlex", "~/.cache/paddle"], "model", 3,
      "Whisper、rembg、PaddleOCR 等工具下载的模型。", "需要时重新下载。"),

    # ------------------------------------------------ MCP / 依赖缓存
    R("npx", "dev_cache", "npx 临时包（MCP）", ["%LOCALAPPDATA%/npm-cache/_npx"], "package", 1,
      "用 npx 启动 MCP 服务器时下载的包。", "下次启动时自动重新下载。正在运行的 MCP 可能需要重启。",
      age_by="entry", age=7),
    R("npm_cache", "dev_cache", "npm 下载缓存",
      ["%LOCALAPPDATA%/npm-cache/_cacache", "%LOCALAPPDATA%/npm-cache/_logs"], "package", 1,
      "npm 安装依赖时的下载缓存和日志。", "下次安装时重新下载。"),
    R("uv_cache", "dev_cache", "uv / uvx 缓存", ["%LOCALAPPDATA%/uv/cache"], "package", 1,
      "uv 和 uvx（很多 Python MCP 服务器用它启动）的包缓存。", "下次运行时重新下载。正在运行的 MCP 可能需要重启。",
      note="也可以在终端运行 uv cache clean。"),
    R("pip_cache", "dev_cache", "pip 缓存", ["%LOCALAPPDATA%/pip/cache"], "package", 1,
      "pip 安装时的下载缓存。", "无影响。"),
    R("pnpm_cache", "dev_cache", "pnpm 缓存", ["%LOCALAPPDATA%/pnpm-cache"], "package", 1,
      "pnpm 的元数据缓存。", "无影响。"),
    R("bun_cache", "dev_cache", "bun 缓存", ["~/.bun/install/cache"], "package", 1,
      "bun 安装依赖时的缓存。", "无影响。"),
    R("playwright", "dev_cache", "Playwright 浏览器",
      ["%LOCALAPPDATA%/ms-playwright", "%LOCALAPPDATA%/ms-playwright-go"], "runtime", 1,
      "Playwright MCP / 浏览器自动化下载的浏览器，每次升级会留下旧版本。", "保留每种浏览器的最新版本。",
      mode="old_versions"),
    R("puppeteer", "dev_cache", "Puppeteer 浏览器", ["~/.cache/puppeteer/*"], "runtime", 1,
      "Puppeteer 下载的 Chrome，每次升级会留下旧版本。", "保留最新版本。", mode="old_versions"),
    R("cdp_mcp", "dev_cache", "Chrome DevTools MCP 缓存",
      chromium_caches("~/.cache/chrome-devtools-mcp/*"), "cache", 1,
      "Chrome DevTools MCP 专用浏览器的网页缓存。", "会自动重新生成。"),
    R("ripgrep_dl", "dev_cache", "ripgrep 下载缓存", ["~/.cache/vscode-ripgrep"], "package", 1,
      "AI 工具安装时下载的 ripgrep 压缩包。", "无影响。"),
    R("conda_tarballs", "dev_cache", "conda 安装包",
      ["~/anaconda3/pkgs", "~/miniconda3/pkgs", "~/.conda/pkgs"], "package", 2,
      "conda 下载后保留的 .conda / .tar.bz2 安装包（已解压的包不会动）。", "无影响，环境照常使用。",
      mode="files", pattern=("*.conda", "*.tar.bz2"), max_depth=1,
      note="也可以运行 conda clean --tarballs。"),

    # ------------------------------------------------ 系统
    R("crash_dumps", "system", "AI 应用崩溃转储", ["%LOCALAPPDATA%/CrashDumps"], "crash", 1,
      "Windows 为崩溃的 AI 应用保存的内存转储（.dmp）。", "无影响。", mode="files",
      pattern=("claude*.dmp", "codex*.dmp", "cursor*.dmp", "windsurf*.dmp", "trae*.dmp", "kiro*.dmp",
               "antigravity*.dmp", "code.exe*.dmp", "node.exe*.dmp", "ollama*.dmp", "chatgpt*.dmp",
               "lm studio*.dmp", "qoder*.dmp", "opencode*.dmp"), max_depth=1),
]


def editor_rules(tool, app, ext_dir):
    """VS Code 系编辑器（Cursor、Windsurf、Trae、Kiro…）的通用规则。"""
    base = f"%APPDATA%/{app}"
    gs = f"{base}/User/globalStorage"
    caches = chromium_caches(base) + [f"{base}/CachedData", f"{base}/CachedExtensionVSIXs",
                                      f"{base}/CachedProfilesData", f"{base}/CachedConfigurations"]
    rules = [
        R(f"{tool}_cache", tool, "编辑器缓存", caches, "cache", 1,
          "界面缓存、扩展安装包缓存和编译后的代码缓存。", "下次启动稍慢，缓存会重新生成。"),
        R(f"{tool}_logs", tool, "日志", [f"{base}/logs"], "log", 1, "编辑器与扩展的运行日志。", "无影响。",
          age_by="entry", age=7),
        R(f"{tool}_crash", tool, "崩溃报告", [f"{base}/Crashpad"], "crash", 1, "崩溃转储。", "无影响。"),
        R(f"{tool}_history", tool, "本地文件历史", [f"{base}/User/History"], "checkpoint", 2,
          "编辑器自动保存的文件历史版本（时间线）。", "无法再从时间线恢复旧版本。", age_by="entry", age=30),
        R(f"{tool}_ws", tool, "工作区存储", [f"{base}/User/workspaceStorage"], "session", 3,
          "每个打开过的项目的状态，包含 AI 聊天记录、代码索引等。", "很久没打开的项目会丢失聊天记录和界面状态。",
          age_by="entry", age=60),
        R(f"{tool}_ext_old", tool, "扩展旧版本", [ext_dir], "version", 2,
          "扩展升级后残留的旧版本目录。", "保留每个扩展的最新版本。", mode="old_versions"),
        R(f"{tool}_agent_tasks", tool, "AI 插件任务记录",
          [f"{gs}/saoudrizwan.claude-dev/tasks", f"{gs}/rooveterinaryinc.roo-cline/tasks",
           f"{gs}/kilocode.kilo-code/tasks"], "session", 3,
          "Cline / Roo Code / Kilo Code 的历史任务（对话、截图、上下文）。", "旧任务无法再打开。",
          age_by="entry", age=30),
        R(f"{tool}_agent_ckpt", tool, "AI 插件检查点",
          [f"{gs}/saoudrizwan.claude-dev/checkpoints", f"{gs}/rooveterinaryinc.roo-cline/checkpoints",
           f"{gs}/kilocode.kilo-code/checkpoints"], "checkpoint", 2,
          "AI 插件为回退代码保存的影子 git 仓库，通常很大。", "旧任务无法回退代码。",
          age_by="entry", age=14),
    ]
    return rules


for _tool, _app, _ext in [
    ("cursor", "Cursor", "~/.cursor/extensions"),
    ("windsurf", "Windsurf", "~/.windsurf/extensions"),
    ("trae", "Trae", "~/.trae/extensions"),
    ("trae", "Trae CN", "~/.trae-cn/extensions"),
    ("kiro", "Kiro", "~/.kiro/extensions"),
    ("qoder", "Qoder", "~/.qoder/extensions"),
    ("antigravity", "Antigravity", "~/.antigravity/extensions"),
    ("vscode", "Code", "~/.vscode/extensions"),
]:
    for _r in editor_rules(_tool, _app, _ext):
        if _app == "Trae CN":
            _r.id = _r.id.replace("trae_", "traecn_")
            _r.name = "Trae CN " + _r.name
        RULES.append(_r)

RULE_MAP = {r.id: r for r in RULES}

# 未被规则覆盖、但名字像 AI 工具的大目录会归入“未识别”
UNKNOWN_KEYWORDS = (
    "claude", "anthropic", "codex", "openai", "chatgpt", "cursor", "windsurf", "codeium", "copilot",
    "gemini", "antigravity", "ollama", "lmstudio", "lm-studio", "lm studio", "huggingface", "trae",
    "kiro", "cline", "roo-", "continue", "opencode", "aider", "qwen", "kimi", "deepseek", "tabnine",
    "cody", "sourcegraph", "zcode", "codebuddy", "lingma", "comate", "marscode", "qoder", "mcp",
    "llm", "whisper", "torch", "modelscope", "paddle", "cherry", "chatbox", "gpt", "agent",
)
UNKNOWN_SCAN_DIRS = ["~", "%APPDATA%", "%LOCALAPPDATA%", "~/.cache", "~/.local/share",
                     "%LOCALAPPDATA%/Packages"]
UNKNOWN_MIN_SIZE = 20 * 1024 * 1024

# 清理目标本身叫这些名字时一律跳过（额外保险，只检查目标这一层）
PROTECTED_NAMES = {
    ".credentials.json", "auth.json", "oauth_creds.json", "google_accounts.json", "settings.json",
    "settings.local.json", "config.toml", "config.json", ".claude.json", "claude_desktop_config.json",
    "mcp.json", "mcp_config.json", "keybindings.json", "agents.md", "claude.md", "gemini.md",
    "id_ed25519", "id_ed25519.pub", "credentials", "secrets",
}
