"""用户目录定位与路径展开。

设置环境变量 AICLEAN_FAKE_ROOT 后，所有目录都会指向这个假根目录，测试时不会碰到真实数据。
"""
import glob
import os


def _bases():
    fake = os.environ.get("AICLEAN_FAKE_ROOT")
    if fake:
        home = os.path.join(fake, "home")
        return {
            "~": home,
            "%USERPROFILE%": home,
            "%APPDATA%": os.path.join(home, "AppData", "Roaming"),
            "%LOCALAPPDATA%": os.path.join(home, "AppData", "Local"),
            "%TEMP%": os.path.join(home, "AppData", "Local", "Temp"),
        }
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    return {
        "~": home,
        "%USERPROFILE%": home,
        "%APPDATA%": os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"),
        "%LOCALAPPDATA%": local,
        "%TEMP%": os.environ.get("TEMP") or os.path.join(local, "Temp"),
    }


def bases():
    return _bases()


def home():
    return _bases()["~"]


def expand_one(pattern):
    """把 '~/.claude/*' 这类写法替换成真实路径（不展开通配符）。"""
    b = _bases()
    p = pattern.replace("\\", "/")
    for key in ("%USERPROFILE%", "%APPDATA%", "%LOCALAPPDATA%", "%TEMP%"):
        if p.startswith(key):
            p = b[key] + p[len(key):]
            break
    else:
        if p == "~" or p.startswith("~/"):
            p = b["~"] + p[1:]
    return os.path.normpath(p)


def expand(pattern):
    """展开通配符，返回存在的路径列表（已排序、去重）。"""
    p = expand_one(pattern)
    if any(ch in p for ch in "*?["):
        found = glob.glob(p)
    else:
        found = [p] if os.path.lexists(p) else []
    return sorted(set(os.path.normpath(x) for x in found))


def norm_key(path):
    """用于比较的路径键（Windows 不区分大小写）。"""
    return os.path.normcase(os.path.abspath(path))


def is_within(child, parent):
    c, p = norm_key(child), norm_key(parent)
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def allowed_bases():
    b = _bases()
    return [b["~"], b["%APPDATA%"], b["%LOCALAPPDATA%"], b["%TEMP%"]]
