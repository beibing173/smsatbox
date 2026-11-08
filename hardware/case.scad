// ============================================================================
//  SMSATBOX 外壳 · OpenSCAD 参数化源码
//  ---------------------------------------------------------------------------
//  用途：ESP32-S3 + 2× ML307A 双模组盒子的 3D 打印外壳
//  用法：OpenSCAD 打开本文件 → F5 预览 → F6 渲染 → F7 导出 STL
//
//  默认输出「下壳」；把 part 改成 "lid" 输出「上盖」，
//  改成 "both" 一次看完整装配。
// ============================================================================

// ---------------------------- 用户可调参数 ----------------------------
part = "base";        // "base" = 下壳 | "lid" = 上盖 | "both" = 总览

// PCB 尺寸
pcb_w        = 120;   // 板宽
pcb_d        = 90;    // 板深
pcb_t        = 1.6;   // 板厚
pcb_standoff = 6;     // 板离底面高度（留给底部走线/焊点）

// 外壳
wall         = 2.5;   // 壁厚（0.4mm 喷嘴建议 ≥2.0）
fit_gap      = 0.35;  // 上下壳配合间隙
base_h       = 28;    // 下壳内高
lid_h        = 8;     // 上盖内高（与 STL 一致）
corner_r     = 6;     // 外形圆角

// 螺丝柱
screw_d      = 3.2;   // M3 螺丝过孔
screw_boss_d = 7.0;   // 螺丝柱外径
screw_inset  = 5;     // 螺丝中心距边

// 接口开孔
usb_w        = 12;    // USB-C 开口宽
usb_h        = 7;     // USB-C 开口高
sim_w        = 16;    // SIM 卡座开口宽
sim_h        = 3.2;   // SIM 卡座开口高
ant_d        = 6.5;   // 天线孔直径（SMA 座）
vent_d       = 3;     // 散热孔直径
vent_n       = 5;     // 每排散热孔数量

// 计算量
inner_w = pcb_w + 2 * 1.5;   // PCB 与内壁留 1.5mm 余量
inner_d = pcb_d + 2 * 1.5;
outer_w = inner_w + 2 * wall;
outer_d = inner_d + 2 * wall;
total_h = pcb_standoff + base_h;   // 下壳总高

$fn = 48;

// ---------------------------- 工具函数 ----------------------------
module rounded_box(w, d, h, r, center = false) {
    // 带圆角的方块
    x = center ? -w / 2 : 0;
    y = center ? -d / 2 : 0;
    z = center ? -h / 2 : 0;
    if (r <= 0.01) {
        translate([x, y, z]) cube([w, d, h]);
    } else {
        hull() {
            for (dx = [r, w - r]) {
                for (dy = [r, d - r]) {
                    translate([x + dx, y + dy, z]) cylinder(r = r, h = h);
                }
            }
        }
    }
}

module rounded_shell(w, d, h, r, t) {
    // 空心圆角壳（外壁 t 厚）
    difference() {
        rounded_box(w, d, h, r);
        translate([t, t, -0.1])
            rounded_box(w - 2 * t, d - 2 * t, h + 0.2, max(r - t, 0.5));
    }
}

// ---------------------------- 下壳 ----------------------------
module base() {
    difference() {
        union() {
            // 外壳主体
            rounded_box(outer_w, outer_d, total_h, corner_r);

            // 四个螺丝柱
            for (px = [screw_inset, outer_w - screw_inset]) {
                for (py = [screw_inset, outer_d - screw_inset]) {
                    translate([px, py, 0])
                        cylinder(d = screw_boss_d, h = total_h);
                }
            }
        }

        // 挖空内部
        translate([wall, wall, pcb_standoff])
            rounded_box(inner_w, inner_d, base_h + 1, max(corner_r - wall, 0.5));

        // 螺丝孔（M3 自攻 / 热熔螺母）
        for (px = [screw_inset, outer_w - screw_inset]) {
            for (py = [screw_inset, outer_d - screw_inset]) {
                translate([px, py, -0.1])
                    cylinder(d = screw_d, h = total_h + 0.2);
            }
        }

        // ---- 前侧 USB-C 开口 ----
        translate([outer_w / 2 - usb_w / 2,
                   -0.1,
                   pcb_standoff + 2])
            cube([usb_w, wall + 0.2, usb_h]);

        // ---- 右侧 SIM 卡开口（两个，上下排）----
        translate([outer_w - wall - 0.1,
                   outer_d * 0.28 - sim_w / 2,
                   pcb_standoff + 3])
            cube([wall + 0.2, sim_w, sim_h]);
        translate([outer_w - wall - 0.1,
                   outer_d * 0.66 - sim_w / 2,
                   pcb_standoff + 3])
            cube([wall + 0.2, sim_w, sim_h]);

        // ---- 顶部天线孔（两个）----
        translate([outer_w * 0.28, outer_d / 2, total_h - 0.1])
            cylinder(d = ant_d, h = wall + 0.2);
        translate([outer_w * 0.72, outer_d / 2, total_h - 0.1])
            cylinder(d = ant_d, h = wall + 0.2);

        // ---- 侧面散热孔（每侧一排）----
        for (i = [0 : vent_n - 1]) {
            y = outer_d * 0.2 + i * (outer_d * 0.6 / max(vent_n - 1, 1));
            // 左侧
            translate([-0.1, y, pcb_standoff + base_h * 0.5])
                rotate([0, 90, 0])
                    cylinder(d = vent_d, h = wall + 0.2);
            // 右侧
            translate([outer_w - wall - 0.1, y, pcb_standoff + base_h * 0.5])
                rotate([0, 90, 0])
                    cylinder(d = vent_d, h = wall + 0.2);
        }

        // ---- 底面散热格栅 ----
        for (i = [0 : vent_n - 1]) {
            x = outer_w * 0.25 + i * (outer_w * 0.5 / max(vent_n - 1, 1));
            translate([x, outer_d * 0.3, -0.1])
                cylinder(d = vent_d, h = wall + 0.2);
            translate([x, outer_d * 0.7, -0.1])
                cylinder(d = vent_d, h = wall + 0.2);
        }

        // ---- PCB 支撑台阶 ----
        // 内壁四周做 1.5mm 高的承托环（也可省略，靠螺丝柱定位）
        translate([wall, wall, pcb_standoff - 0.1])
            rounded_shell(inner_w, inner_d, 1.6, max(corner_r - wall, 0.5), 0.1);
    }
}

// ---------------------------- 上盖 ----------------------------
module lid() {
    difference() {
        union() {
            // 顶板
            rounded_box(outer_w - 2 * fit_gap,
                        outer_d - 2 * fit_gap,
                        wall + 0.4,
                        corner_r);

            // 侧裙（插入下壳）
            translate([0, 0, wall + 0.4])
                rounded_shell(outer_w - 2 * fit_gap - 1.6,
                              outer_d - 2 * fit_gap - 1.6,
                              lid_h,
                              max(corner_r - 2, 1),
                              1.6);
        }

        // 螺丝孔（沉头）
        for (px = [screw_inset, outer_w - screw_inset]) {
            for (py = [screw_inset, outer_d - screw_inset]) {
                translate([px, py, -0.1])
                    cylinder(d = screw_d + 0.4, h = wall + 0.6);
            }
        }

        // 顶面小散热孔
        for (i = [0 : 3]) {
            for (j = [0 : 2]) {
                translate([outer_w * 0.3 + i * outer_w * 0.13,
                           outer_d * 0.35 + j * outer_d * 0.15,
                           -0.1])
                    cylinder(d = 2.5, h = wall + 1);
            }
        }
    }
}

// ---------------------------- 装配总览 ----------------------------
module assembly_preview() {
    color("#4a90d9") base();
    color("#d98c4a") translate([0, 0, total_h + 1]) lid();
    // PCB 示意
    color("#2f7d32", 0.35)
        translate([wall + 1.5, wall + 1.5, pcb_standoff])
            cube([pcb_w, pcb_d, pcb_t]);
}

// ---------------------------- 输出 ----------------------------
if (part == "base") base();
else if (part == "lid") lid();
else if (part == "both") assembly_preview();
else echo("part 只能是 base / lid / both");
