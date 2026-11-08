"""SMSATBOX 全局版本常量。

全平台（server / esp32 / android / windows）初始版本统一为 1.0.0。
CI 会读取本文件中的 VERSION 作为 Docker 镜像 Tag 与发布版本号。
"""

VERSION = "1.0.6"
BUILD_DATE = "2026-11-08"
PRODUCT = "SMSATBOX"
API_PREFIX = "/api/v1"
