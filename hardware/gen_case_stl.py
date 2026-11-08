# -*- coding: utf-8 -*-
"""SMSATBOX 外壳 STL 生成器（纯 Python，无需 OpenSCAD）

输出：
  case_base.stl  下壳
  case_lid.stl   上盖

设计：
  外尺寸 131 × 101 × 28mm（下壳），上盖 131 × 101 × 8mm
  壁厚 2.5mm，内腔 126 × 96 × 25.5mm，可放 120×90 PCB
  前侧 USB-C 开口、右侧双 SIM 开口、底面散热大开口
  四角 M3 螺丝柱

STL 用二进制格式，可直接丢给切片软件打印。
"""
import math
import struct
from pathlib import Path

OUT = Path(r"D:\SMSATBOX\hardware")
OUT.mkdir(parents=True, exist_ok=True)

# ============================================================================
# 参数（mm）
# ============================================================================
WALL = 2.5           # 壁厚
PCB_W, PCB_D = 120, 90
MARGIN = 3.0         # PCB 与内壁间隙
INNER_W = PCB_W + 2 * MARGIN      # 126
INNER_D = PCB_D + 2 * MARGIN      # 96
OUTER_W = INNER_W + 2 * WALL      # 131
OUTER_D = INNER_D + 2 * WALL      # 101

BASE_H = 28.0        # 下壳总高
LID_H = 8.0          # 上盖高
FLOOR_T = 2.0        # 底板厚

SCREW_D = 3.4        # M3 过孔
SCREW_INSET = 6.0    # 螺丝中心距边
BOSS_D = 7.0         # 螺丝柱外径

# 开口
USB_W, USB_H = 12.0, 7.0
SIM_W, SIM_H = 16.0, 3.2
SIM1_Y = 30.0        # SIM1 开口中心 Y
SIM2_Y = 66.0        # SIM2 开口中心 Y
SIM_Z = PCB_D * 0 + 8.0   # 开口离底高度

ANT_D = 7.0          # 天线孔

# ============================================================================
# 三角网格工具
# ============================================================================
tris: list[tuple[tuple[float, float, float], ...]] = []


def add_tri(a, b, c):
    tris.append((a, b, c))


def add_quad(a, b, c, d):
    """四边形 = 2 个三角形（a-b-c-d 逆时针）"""
    add_tri(a, b, c)
    add_tri(a, c, d)


def box(x, y, z, w, d, h):
    """轴对齐长方体，共 12 个三角形（外向法线）"""
    x0, x1 = x, x + w
    y0, y1 = y, y + d
    z0, z1 = z, z + h

    # 底 z0（法线 -Z）
    add_quad((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0))
    # 顶 z1（法线 +Z）
    add_quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))
    # 前 y0（-Y）
    add_quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))
    # 后 y1（+Y）
    add_quad((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0))
    # 左 x0（-X）
    add_quad((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0))
    # 右 x1（+X）
    add_quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))


def write_stl(path: Path, name: str):
    """二进制 STL"""
    with open(path, "wb") as f:
        f.write(name.encode("ascii", "replace")[:79].ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            # 法线
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            f.write(struct.pack("<3f", nx / ln, ny / ln, nz / ln))
            for v in (a, b, c):
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))
    print(f"  ✓ {path.name}  {len(tris)} 三角面  {path.stat().st_size / 1024:.1f} KB")


# ============================================================================
# 下壳
# ============================================================================
def build_base():
    tris.clear()
    t = WALL

    # ---- 底板（留四个螺丝柱位置，中间开大散热窗）----
    # 底板用四条边框 + 四个角块拼成，中间留空散热
    hole_x0, hole_x1 = 18.0, OUTER_W - 18.0
    hole_y0, hole_y1 = 18.0, OUTER_D - 18.0

    # 底框：四条边
    box(0, 0, 0, OUTER_W, hole_y0, FLOOR_T)                       # 前
    box(0, hole_y1, 0, OUTER_W, OUTER_D - hole_y1, FLOOR_T)       # 后
    box(0, hole_y0, 0, hole_x0, hole_y1 - hole_y0, FLOOR_T)       # 左
    box(hole_x1, hole_y0, 0, OUTER_W - hole_x1, hole_y1 - hole_y0, FLOOR_T)  # 右

    # ---- 四面墙 ----
    # 前墙（Y=0）：中间开 USB-C 口
    usb_cx = OUTER_W / 2
    usb_x0 = usb_cx - USB_W / 2
    usb_x1 = usb_cx + USB_W / 2
    usb_z0 = 6.0
    usb_z1 = usb_z0 + USB_H
    box(0, 0, FLOOR_T, usb_x0, t, BASE_H - FLOOR_T)               # 前墙左段
    box(usb_x1, 0, FLOOR_T, OUTER_W - usb_x1, t, BASE_H - FLOOR_T)  # 前墙右段
    box(usb_x0, 0, FLOOR_T, USB_W, t, usb_z0 - FLOOR_T)           # USB 下段
    box(usb_x0, 0, usb_z1, USB_W, t, BASE_H - usb_z1)             # USB 上段

    # 后墙（Y=OUTER_D-t）
    box(0, OUTER_D - t, FLOOR_T, OUTER_W, t, BASE_H - FLOOR_T)

    # 左墙（X=0）
    box(0, t, FLOOR_T, t, OUTER_D - 2 * t, BASE_H - FLOOR_T)

    # 右墙（X=OUTER_W-t）：两个 SIM 开口
    rx = OUTER_W - t
    for sim_y in (SIM1_Y, SIM2_Y):
        sy0 = sim_y - SIM_W / 2
        sy1 = sim_y + SIM_W / 2
        sz0 = SIM_Z
        sz1 = sz0 + SIM_H
        # 右墙分段
        box(rx, t, FLOOR_T, t, sy0 - t, BASE_H - FLOOR_T)
        box(rx, sy1, FLOOR_T, t, OUTER_D - t - sy1, BASE_H - FLOOR_T)
        box(rx, sy0, FLOOR_T, t, SIM_W, sz0 - FLOOR_T)
        box(rx, sy0, sz1, t, SIM_W, BASE_H - sz1)
        # 中间剩下的竖条（两个开口之间）
    # 两个开口之间的墙段
    a0 = SIM1_Y + SIM_W / 2
    a1 = SIM2_Y - SIM_W / 2
    box(rx, a0, FLOOR_T, t, a1 - a0, BASE_H - FLOOR_T)

    # ---- 四个螺丝柱 ----
    for sx in (SCREW_INSET, OUTER_W - SCREW_INSET):
        for sy in (SCREW_INSET, OUTER_D - SCREW_INSET):
            # 柱身
            box(sx - BOSS_D / 2, sy - BOSS_D / 2, FLOOR_T,
                BOSS_D, BOSS_D, BASE_H - FLOOR_T)
            # 中间挖孔：用四块拼（简化：只做矩形柱，孔留到打印后钻）
            # 实际用切片软件的"负体积"或者打印后手钻 φ3.4
    # 螺丝孔用负体积不好做，改成：柱体只做到一定高度，顶部留沉孔
    # 这里简化：柱子实心，打印后用电钻打通（M3 自攻螺丝也能直接拧进 PLA）

    write_stl(OUT / "case_base.stl", "SMSATBOX case base")


# ============================================================================
# 上盖
# ============================================================================
def build_lid():
    tris.clear()
    t = WALL

    # 顶板
    box(0, 0, 0, OUTER_W, OUTER_D, t)

    # 侧裙（向下 8mm，插入下壳）
    skirt_h = LID_H - t
    box(0, 0, -skirt_h, OUTER_W, t, skirt_h)
    box(0, OUTER_D - t, -skirt_h, OUTER_W, t, skirt_h)
    box(0, t, -skirt_h, t, OUTER_D - 2 * t, skirt_h)
    box(OUTER_W - t, t, -skirt_h, t, OUTER_D - 2 * t, skirt_h)

    # 顶面两个天线孔（做成人字形缺口示意，实际开口由打印后开孔）
    # 简化为：顶板留两个方孔
    # 因为要挖孔，这里用"分段顶板"实现
    tris.clear()
    ax1 = OUTER_W * 0.28
    ax2 = OUTER_W * 0.72
    ay = OUTER_D / 2
    half = ANT_D / 2

    # 顶板分段（在两个天线孔周围拼）
    # 左块
    box(0, 0, 0, ax1 - half, OUTER_D, t)
    # 右块
    box(ax2 + half, 0, 0, OUTER_W - ax2 - half, OUTER_D, t)
    # 中块（两个孔之间）
    box(ax1 + half, 0, 0, (ax2 - half) - (ax1 + half), OUTER_D, t)
    # 天线孔前后的窄条
    for cx in (ax1, ax2):
        box(cx - half, 0, 0, ANT_D, ay - half, t)
        box(cx - half, ay + half, 0, ANT_D, OUTER_D - ay - half, t)

    # 侧裙
    box(0, 0, -skirt_h, OUTER_W, t, skirt_h)
    box(0, OUTER_D - t, -skirt_h, OUTER_W, t, skirt_h)
    box(0, t, -skirt_h, t, OUTER_D - 2 * t, skirt_h)
    box(OUTER_W - t, t, -skirt_h, t, OUTER_D - 2 * t, skirt_h)

    write_stl(OUT / "case_lid.stl", "SMSATBOX case lid")


if __name__ == "__main__":
    print("生成 3D 外壳 STL...")
    build_base()
    build_lid()
    print()
    print(f"输出目录: {OUT}")
    print("可直接导入 Cura / PrusaSlicer / 拓竹 Studio 切片打印")
    print()
    print("打印建议：")
    print("  材料    PLA 或 PETG")
    print("  层高    0.2mm")
    print("  壁厚    3 圈（=1.2mm）")
    print("  填充    20% 网格")
    print("  支撑    下壳不需要，上盖侧裙建议加支撑")
