#!/usr/bin/env bash
# ============================================================================
#  SMSATBOX · 分平台版本号脚本
#  ---------------------------------------------------------------------------
#  为什么分平台？
#    APK 与 EXE 各自独立演进，版本号不强制一致；
#    Server 又是独立的一套版本节奏。
#
#  为什么还能共用一个 Release？
#    Release 的 tag 用「版本快照号」统一标识（如 v2026.11.02-r1），
#    而**每个平台真正的版本号写在各自的附件文件名里**：
#        smsatbox-android-1.2.0.apk
#        smsatbox-windows-1.0.5.exe
#        server-1.0.0-image.txt
#    客户端升级时只比对「自己那个附件文件名里的版本」，
#    所以任何一端升级都不会误导另一端。
#
#  用法：
#    ./scripts/version.sh android name      → 1.0.0
#    ./scripts/version.sh windows name      → 1.0.0
#    ./scripts/version.sh server name       → 1.0.0
#    ./scripts/version.sh android code      → 10000
#    ./scripts/version.sh snapshot          → 2026.11.02-r1  （Release tag 用）
#    ./scripts/version.sh tag               → v2026.11.02-r1
#    ./scripts/version.sh all               → 打印所有平台版本
#    ./scripts/version.sh write-gradle <dir>→ 生成 android/version.properties
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSIONS_DIR="$ROOT/versions"

PLATFORMS=(server android windows)

fail() {
  echo "::error::$*" >&2
  exit 1
}

read_platform_version() {
  local platform="$1"
  local file="$VERSIONS_DIR/$platform.txt"
  [ -f "$file" ] || fail "找不到版本文件 versions/$platform.txt"
  tr -d ' \t\r\n' < "$file"
}

validate_semver() {
  local v="$1" name="$2"
  [[ "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || fail "$name 版本号格式非法: '$v'（应形如 1.0.0）"
}

to_version_code() {
  local v="$1"
  local major minor patch
  IFS='.' read -r major minor patch <<< "$v"
  printf "%d" $(( major * 10000 + minor * 100 + patch ))
}

# 快照号：按日期 + 当日序号，用于 Release tag。
#   当天第一次 → 2026.11.07
#   当天第二次 → 2026.11.07-2
#   当天第三次 → 2026.11.07-3
# 序号来源优先查 GitHub 已存在的 tag（保证跨机器/多次运行不重号），
# 查不到时退化为本地计数文件。
snapshot_id() {
  local today serial_file next candidate
  today="$(date -u +%Y.%m.%d)"
  serial_file="$VERSIONS_DIR/.snapshot-$today"

  # 1) 先看本地计数
  if [ -f "$serial_file" ]; then
    next=$(( $(tr -d ' \t\r\n' < "$serial_file") + 1 ))
  else
    next=1
  fi

  # 2) 如果 gh 可用，查远端已被占用的最大序号，取更大者
  if command -v gh >/dev/null 2>&1 && [ -n "${GITHUB_REPOSITORY:-}" ]; then
    local max_remote=0
    local existing
    existing="$(gh release list --repo "$GITHUB_REPOSITORY" --limit 100 \
                 --json tagName -q '.[].tagName' 2>/dev/null || true)"
    while IFS= read -r t; do
      [ -z "$t" ] && continue
      case "$t" in
        "v$today")        [ "$max_remote" -lt 1 ] && max_remote=1 ;;
        "v$today-"*)      n="${t#v$today-}"
                          if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -gt "$max_remote" ]; then
                            max_remote="$n"
                          fi ;;
      esac
    done <<< "$existing"
    [ "$max_remote" -ge "$next" ] && next=$(( max_remote + 1 ))
  fi

  printf "%s" "$next" > "$serial_file"

  if [ "$next" -le 1 ]; then
    printf "%s" "$today"
  else
    printf "%s-%s" "$today" "$next"
  fi
}

cmd="${1:-all}"
sub="${2:-}"

case "$cmd" in
  server|android|windows)
    v="$(read_platform_version "$cmd")"
    case "${sub:-name}" in
      name) echo "$v" ;;
      code) to_version_code "$v" ;;
      file) echo "$VERSIONS_DIR/$cmd.txt" ;;
      validate)
        validate_semver "$v" "$cmd"
        echo "$cmd 版本校验通过: $v"
        ;;
      *) fail "未知子命令: $sub（可用: name | code | file | validate）" ;;
    esac
    ;;

  snapshot)
    snapshot_id
    ;;

  tag)
    echo "v$(snapshot_id)"
    ;;

  all)
    echo "SMSATBOX 版本总览"
    echo "-----------------------------"
    for p in "${PLATFORMS[@]}"; do
      validate_semver "$(read_platform_version "$p")" "$p"
      printf "  %-8s v%s\n" "$p" "$(read_platform_version "$p")"
    done
    echo "-----------------------------"
    echo "  Release tag: v$(snapshot_id)"
    ;;

  write-gradle)
    target="${sub:-.}"
    v="$(read_platform_version android)"
    validate_semver "$v" "android"
    code="$(to_version_code "$v")"
    cat > "$target/version.properties" <<EOF
# 由 scripts/version.sh 自动生成，请勿手改
VERSION_NAME=$v
VERSION_CODE=$code
EOF
    echo "已写入 $target/version.properties → $v (code=$code)"
    ;;

  sync)
    # 把 versions/*.txt 同步到各端源码，保证单一事实来源
    sv="$(read_platform_version server)"
    av="$(read_platform_version android)"
    wv="$(read_platform_version windows)"

    # Server
    sed -i.bak -E "s/^VERSION = \".*\"/VERSION = \"$sv\"/" "$ROOT/server/app/version.py" \
      && rm -f "$ROOT/server/app/version.py.bak"

    # Android
    bash "$0" write-gradle "$ROOT/android"

    # Windows：AppInfo.cs 的 Version 常量
    if [ -f "$ROOT/windows/SmsatBox.Desktop/Core/AppInfo.cs" ]; then
      sed -i.bak -E "s/(public const string Version = )\"[^\"]*\"/\1\"$wv\"/" \
        "$ROOT/windows/SmsatBox.Desktop/Core/AppInfo.cs" \
        && rm -f "$ROOT/windows/SmsatBox.Desktop/Core/AppInfo.cs.bak"
    fi

    # ESP32 固件版本跟 Server 走（协同升级维度）
    if [ -f "$ROOT/esp32/include/config.h" ]; then
      sed -i.bak -E "s/(#define SMSATBOX_VERSION )\"[^\"]*\"/\1\"$sv\"/" \
        "$ROOT/esp32/include/config.h" \
        && rm -f "$ROOT/esp32/include/config.h.bak"
    fi

    echo "已同步：server=$sv android=$av windows=$wv esp32=$sv"
    ;;

  validate-all)
    for p in "${PLATFORMS[@]}"; do
      validate_semver "$(read_platform_version "$p")" "$p"
      echo "$p: $(read_platform_version "$p") OK"
    done
    ;;

  *)
    cat >&2 <<USAGE
未知命令: $cmd

可用命令：
  server|android|windows name|code|validate   读取单个平台版本
  all                                        打印全部平台版本
  snapshot                                   生成 Release 快照号（日期+rN）
  tag                                        生成完整 tag（含 v 前缀）
  write-gradle <dir>                         生成 Android version.properties
  sync                                       把 versions/*.txt 写进各端源码
  validate-all                               校验全部版本号格式
USAGE
    exit 1
    ;;
esac
