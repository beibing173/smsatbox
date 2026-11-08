"""检查 GitHub 上的 eSIM 代码是否完整推送"""
import base64
import json
import subprocess
import urllib.request

TOK = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
REPO = "beibing173/smsatbox"


def api(path: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Authorization": f"Bearer {TOK}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_file(path: str) -> str | None:
    try:
        d = api(f"/repos/{REPO}/contents/{path}")
        return base64.b64decode(d["content"]).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None


print("=== GitHub 上的 eSIM 相关文件 ===")
for p in [
    "server/app/routers/esim.py",
    "server/app/static/esim.html",
    "server/app/main.py",
    "server/app/schemas.py",
    "server/app/db.py",
]:
    content = get_file(p)
    if content is None:
        print(f"  ✗ {p} 不存在")
        continue
    size = len(content)
    extra = ""
    if p.endswith("main.py"):
        extra = " [含 esim 路由]" if "esim.router" in content else " [!! 缺 esim 路由]"
    elif p.endswith("schemas.py"):
        extra = " [含 EuiccReport]" if "EuiccReport" in content else " [!! 缺模型]"
    elif p.endswith("db.py"):
        extra = " [含 euicc 表]" if "CREATE TABLE IF NOT EXISTS euicc" in content else " [!! 缺表]"
    elif p.endswith("esim.html"):
        extra = f" [API 前缀: {'/api/v1' if '/api/v1' in content else '?'}]"
    print(f"  ✓ {p}  {size} 字符{extra}")

print()
print("=== esim.html 里的所有 API 调用 ===")
content = get_file("server/app/static/esim.html") or ""
import re

for m in re.finditer(r'api\(\s*"([^"]+)"', content):
    print(f"  api({m.group(1)!r})")
for m in re.finditer(r'location\.href\s*=\s*[\'"]([^\'"]+)', content):
    print(f"  location.href = {m.group(1)!r}")

print()
print("=== 最新提交 ===")
commits = api(f"/repos/{REPO}/commits?per_page=3")
for c in commits:
    print(f"  {c['sha'][:7]}  {c['commit']['message'].splitlines()[0][:60]}")
