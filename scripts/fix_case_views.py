# -*- coding: utf-8 -*-
"""修正三视图文字重叠：重排纵向布局"""
from pathlib import Path

P = Path(r"D:\SMSATBOX\hardware\case_views.svg")
c = P.read_text(encoding="utf-8")

# 删除旧的 USB 标注（位置冲突）
c = c.replace(
    '    <text x="120" y="856" fill="#b3261e">USB-C 开口 12 × 7（中心 X=65.5，距底 6mm）</text>\n',
    "",
)

# 删除旧的 SIM 标注
c = c.replace(
    '''    <text x="120" y="880" fill="#b3261e">SIM1 开口 16 × 3.2（中心 Y=30）</text>
    <text x="120" y="900" fill="#b3261e">SIM2 开口 16 × 3.2（中心 Y=66）</text>
    <text x="120" y="925">距底高度 8mm，便于热插拔</text>''',
    "",
)

# 正视图区域：标题上移，保持图形 662 起
c = c.replace('<text x="118" y="640" class="h2">② 正视图（前视）</text>',
              '<text x="118" y="628" class="h2">② 正视图（前视）</text>')

# 在正视图尺寸标注下方加 USB 说明（y=848）
c = c.replace(
    '<text x="408" y="830" text-anchor="middle" class="dimt">131</text>',
    '''<text x="408" y="830" text-anchor="middle" class="dimt">131</text>
  <text x="120" y="856" fill="#b3261e" class="lbl">USB-C 开口 12 × 7（中心 X=65.5，距底 6mm）</text>''',
)

# 侧视图标题下移到 892，给 USB 说明留空间
c = c.replace('<text x="118" y="880" class="h2">③ 侧视图（右视）</text>',
              '<text x="118" y="892" class="h2">③ 侧视图（右视）</text>')

# 侧视图整体下移 32px（图形 902 → 934）
c = c.replace('<g transform="translate(120,902) scale(4.4)">',
              '<g transform="translate(120,934) scale(4.4)">')

# 侧视图尺寸线跟着下移
c = c.replace('<path d="M120 1050 H564"/>', '<path d="M120 1082 H564"/>')
c = c.replace('<path d="M120 1043 V1057 M564 1043 V1057"/>',
              '<path d="M120 1075 V1089 M564 1075 V1089"/>')
c = c.replace('<text x="342" y="1070" text-anchor="middle" class="dimt">101</text>',
              '<text x="342" y="1102" text-anchor="middle" class="dimt">101</text>')
c = c.replace('<path d="M600 902 V1025"/>', '<path d="M600 934 V1057"/>')
c = c.replace('<path d="M593 902 H607 M593 1025 H607"/>',
              '<path d="M593 934 H607 M593 1057 H607"/>')
c = c.replace('<text x="620" y="970" class="dimt">28</text>',
              '<text x="620" y="1002" class="dimt">28</text>')

# SIM 标注放到最下方（y=1128~1158），不再压图
c = c.replace(
    '<text x="40" y="1140" class="sub">SMSATBOX Case Design',
    '''<text x="120" y="1128" fill="#b3261e" class="lbl">SIM1 开口 16 × 3.2（中心 Y=30，距底 8mm）</text>
  <text x="120" y="1150" fill="#b3261e" class="lbl">SIM2 开口 16 × 3.2（中心 Y=66，距底 8mm）</text>

  <text x="40" y="1140" class="sub">SMSATBOX Case Design''',
)

P.write_bytes(c.encode("utf-8"))
print("✓ 三视图布局已重排")
