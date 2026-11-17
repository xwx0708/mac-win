"""从 ../index.html 提取成品着色器，生成导出视频用的版本 splash.frag。

导出版和成品只有两处差别，都是为了让"循环"那一段能首尾相接：
  1. 悬浮液滴的波动、上下浮动改成同一个基频 W0 = 2π / 循环时长，循环一圈后回到原位。
     成品里是 1.1、1.7、1.3 三个互不成整数比的频率，永远不会精确重复。
  2. 相撞后的回弹和余振原本按指数衰减、永远不精确归零；这里在相撞后 2~3 时间线秒内
     把它们平滑收到 0，之后的画面就是纯周期的。
其余形态、轨迹参数与成品完全相同。
"""
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).parent
SRC = (HERE.parent / "index.html").read_text(encoding="utf-8")

# ---- 导出规格 ----
FPS = 60                 # 成片帧率
RATE = 2                 # 成品速度：时间线 1 秒 = 屏幕 0.5 秒
T1 = 2.2                 # 相撞时刻（时间线秒）
SETTLE = 3.0             # 相撞后多久进入纯周期状态（时间线秒）
LOOP_FRAMES = 171        # 循环段帧数 → 2.85 秒
E1, E2 = 0.7, 0.5        # 展开、揭开（时间线秒）
WIDTH, HEIGHT = 3840, 2160   # 1920×1080 的二倍

DT = RATE / FPS                          # 每帧前进的时间线秒
T_LOOP = T1 + SETTLE                     # 循环段起点
INTRO_FRAMES = round(T_LOOP / DT)        # 156 帧 = 2.6 秒
LOOP_PERIOD = LOOP_FRAMES * DT           # 5.7 时间线秒
OUTRO_FRAMES = round((E1 + E2) / DT) + 1 # 37 帧（第 0 帧与循环第 0 帧相同）
W0 = 2 * math.pi / LOOP_PERIOD

m = re.search(r"const FRAG = `\n(.*?)`;", SRC, re.S)
frag = m.group(1)


def sub(old, new):
    global frag
    assert frag.count(old) == 1, f"没有唯一匹配：{old!r}"
    frag = frag.replace(old, new)


sub("${T1.toFixed(2)}", f"{T1:.2f}")
sub("${MARGIN.toFixed(3)}", "0.060")
sub("${CORNER.toFixed(3)}", "0.030")
sub("const float RC = 0.030;",
    "const float RC = 0.030;\n"
    f"const float W0 = {W0:.7f};   // 循环基频 = 2π / {LOOP_PERIOD:.2f}（仅导出版）")
sub(".035*sin(2.*th + 1.1*t) + .020*sin(3.*th - 1.7*t)",
    ".035*sin(2.*th + W0*t) + .020*sin(3.*th - W0*t)")
sub("float spring = 1. - .2 * exp(-2.6*u) * cos(5.5*u);",
    "float settle = 1. - smoothstep(2., 3., u);              // 仅导出版：余振在 u=3 精确归零\n"
    "  float spring = 1. - .2 * settle * exp(-2.6*u) * cos(5.5*u);")
sub("p.y -= BOB * sin(u * 1.3) * smoothstep(0., 2., u);",
    "p.y -= BOB * sin(u * W0) * smoothstep(0., 2., u);")
sub("float lobe = .20 * exp(-2.2*u)", "float lobe = .20 * settle * exp(-2.2*u)")

(HERE / "splash.frag").write_text(frag, encoding="utf-8")
spec = {
    "fps": FPS, "rate": RATE, "width": WIDTH, "height": HEIGHT, "dt": DT,
    "t_loop": T_LOOP, "loop_period": LOOP_PERIOD, "e1": E1, "e2": E2,
    "segments": {"intro": INTRO_FRAMES, "loop": LOOP_FRAMES, "outro": OUTRO_FRAMES},
}
(HERE / "spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
print(json.dumps(spec))
