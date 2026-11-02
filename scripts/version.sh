#!/usr/bin/env bash
# ============================================================================
#  SMSATBOX · 统一版本号脚本
#  ---------------------------------------------------------------------------
#  全平台版本号唯一来源：VERSION 文件（仓库根目录）
#  用法：
#    ./scripts/version.sh name       → 1.0.0
#    ./scripts/version.sh tag        → v1.0.0
#    ./scripts/version.sh code       → 10000   （versionCode，Android 用）
#    ./scripts/version.sh validate   → 校验格式，失败退出码非 0
#    ./scripts/version.sh write-gradle <dir>  → 写入指定目录的 version.properties
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_FILE="$ROOT/VERSION"

read_version() {
  if [ ! -f "$VERSION_FILE" ]; then
    echo "::error::找不到版本文件 $VERSION_FILE" >&2
    exit 1
  fi
  tr -d ' \t\r\n' < "$VERSION_FILE"
}

cmd="${1:-name}"
case "$cmd" in
  name)
    read_version
    ;;
  tag)
    echo "v$(read_version)"
    ;;
  code)
    # 1.2.3 → 10203（major*10000 + minor*100 + patch）
    V="$(read_version)"
    IFS='.' read -r MAJOR MINOR PATCH <<< "$V"
    printf "%d\n" $(( MAJOR * 10000 + MINOR * 100 + PATCH ))
    ;;
  validate)
    V="$(read_version)"
    if ! [[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "::error::版本号格式非法: '$V'（应形如 1.0.0）" >&2
      exit 1
    fi
    echo "版本号校验通过: $V"
    ;;
  write-gradle)
    TARGET="${2:-.}"
    V="$(read_version)"
    CODE="$(IFS='.'; read -r A B C <<< "$V"; echo $(( A*10000 + B*100 + C )))"
    cat > "$TARGET/version.properties" <<EOF
# 由 scripts/version.sh 自动生成，请勿手改
VERSION_NAME=$V
VERSION_CODE=$CODE
EOF
    echo "已写入 $TARGET/version.properties → $V (code=$CODE)"
    ;;
  *)
    echo "未知命令: $cmd" >&2
    echo "可用: name | tag | code | validate | write-gradle <dir>" >&2
    exit 1
    ;;
esac
