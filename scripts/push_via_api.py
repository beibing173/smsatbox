"""通过 GitHub REST API 推送本地提交（绕过 git push，适用于 github.com 被墙但 api 可达）。

用法：python scripts/push_via_api.py [--dry-run]
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "beibing173/smsatbox"
BRANCH = "main"
API = "https://api.github.com"


def token() -> str:
    out = subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    )
    return out.stdout.strip()


def git(*args: str) -> str:
    """运行 git 命令并强制 UTF-8 解码（Windows 默认 GBK 会炸中文）。"""
    out = subprocess.run(
        ["git", *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    return out.stdout


def git_bytes(*args: str) -> bytes:
    out = subprocess.run(["git", *args], capture_output=True, check=True)
    return out.stdout


def call(method: str, path: str, tok: str, body: dict | None = None) -> dict:
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {payload[:500]}") from None


def changed_files() -> list[str]:
    """相对于远端 origin/main，本地有哪些文件变了。"""
    return [line.strip() for line in git("diff", "--name-only", "origin/main", "HEAD").splitlines()
            if line.strip()]


def file_at_head(path: str) -> bytes:
    return git_bytes("show", f"HEAD:{path}")


def remote_sha(path: str, tok: str) -> str | None:
    try:
        data = call("GET", f"/repos/{REPO}/contents/{urllib.parse.quote(path)}?ref={BRANCH}", tok)
        return data.get("sha")
    except RuntimeError as exc:
        if "404" in str(exc):
            return None
        raise


def deleted_locally(path: str) -> bool:
    out = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{path}"], capture_output=True
    )
    return out.returncode != 0


def main() -> int:
    dry = "--dry-run" in sys.argv
    tok = token()

    files = changed_files()
    if not files:
        print("没有差异，无需推送")
        return 0

    print(f"共 {len(files)} 个文件需要推送")
    head_msg = git("log", "-1", "--pretty=%s").strip()
    head_body = git("log", "-1", "--pretty=%b").strip()

    ok = 0
    for path in files:
        if deleted_locally(path):
            sha = remote_sha(path, tok)
            if sha and not dry:
                call("DELETE", f"/repos/{REPO}/contents/{urllib.parse.quote(path)}", tok,
                     {"message": f"delete {path}", "sha": sha, "branch": BRANCH})
                print(f"  DELETE {path}")
            elif dry:
                print(f"  [dry] DELETE {path}")
            ok += 1
            continue

        content = file_at_head(path)
        try:
            content.decode("utf-8")
            # 文本文件按 base64 提交
        except UnicodeDecodeError:
            pass

        payload = {
            "message": head_msg if ok == 0 else f"update {path}",
            "content": base64.b64encode(content).decode("ascii"),
            "branch": BRANCH,
        }
        sha = remote_sha(path, tok)
        if sha:
            payload["sha"] = sha

        if dry:
            print(f"  [dry] PUT {path} ({len(content)} bytes)")
        else:
            try:
                call("PUT", f"/repos/{REPO}/contents/{urllib.parse.quote(path)}", tok, payload)
                print(f"  PUT {path} ({len(content)} bytes)")
            except RuntimeError as exc:
                print(f"  FAIL {path}: {exc}")
                return 1
        ok += 1

    print(f"\n完成 {ok}/{len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
