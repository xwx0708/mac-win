"""检查导出的 PNG 序列：帧数、透明通道、三段之间以及循环首尾是否无缝。

"相邻帧差异"= 两帧透明通道逐像素差的绝对值之和 / 255，单位相当于"变化了多少个整像素"。
无缝的判据：接缝处的差异和它前后正常相邻帧的差异在同一水平，没有突增。
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).parent
spec = json.loads((HERE / "spec.json").read_text(encoding="utf-8"))
sys.stdout.reconfigure(encoding="utf-8")   # Windows 控制台默认编码打不出中文
ok = True


def load(seg, i):
    im = Image.open(HERE / "frames" / seg / f"{i:04d}.png")
    assert im.mode == "RGBA", f"{seg}/{i} 不是 RGBA：{im.mode}"
    assert im.size == (spec["width"], spec["height"]), f"{seg}/{i} 尺寸 {im.size}"
    return np.asarray(im)


def alpha(seg, i):
    return load(seg, i)[..., 3].astype(np.int16)


def diff(a, b):
    d = np.abs(a - b)
    return float(d.sum()) / 255.0, int(d.max())


def report(name, passed, detail):
    global ok
    ok &= bool(passed)
    print(("通过  " if passed else "失败  ") + name + "：" + detail)


# 1. 帧数
for seg, n in spec["segments"].items():
    have = len(list((HERE / "frames" / seg).glob("*.png")))
    report(f"{seg} 帧数", have == n, f"{have} / {n}")

# 2. 透明通道：颜色全黑，四角透明，中途确实有不透明像素，收尾最后一帧全透明
mid = load("loop", 0)
report("颜色通道为纯黑", int(mid[..., :3].max()) == 0, f"RGB 最大值 {int(mid[..., :3].max())}")
corners = [int(mid[y, x, 3]) for y in (0, -1) for x in (0, -1)]
report("四角完全透明", max(corners) == 0, f"四角 alpha {corners}")
report("液滴中心不透明", int(mid[spec['height'] // 2, spec['width'] // 2, 3]) == 255,
       f"中心 alpha {int(mid[spec['height'] // 2, spec['width'] // 2, 3])}")
n_out = spec["segments"]["outro"]
report("收尾最后一帧全透明", int(alpha("outro", n_out - 1).max()) == 0,
       f"alpha 最大值 {int(alpha('outro', n_out - 1).max())}")
report("开场第一帧全透明（水滴还在画面外）", int(alpha("intro", 0).max()) == 0,
       f"alpha 最大值 {int(alpha('intro', 0).max())}")

# 3. 循环首尾：循环一整圈后的画面（check/0000）应与循环第 0 帧逐像素相同
N = spec["segments"]["loop"]
s, m = diff(alpha("loop", 0), alpha("check", 0))
report("循环一圈后回到第 0 帧", m <= 1, f"差异 {s:.2f} 像素，单像素最大差 {m}/255")
s, m = diff(alpha("loop", 1), alpha("check", 1))
report("循环一圈后的第 1 帧也一致", m <= 1, f"差异 {s:.2f} 像素，单像素最大差 {m}/255")

# 4. 接缝处的帧间差异不应高于正常相邻帧
loop = [alpha("loop", i) for i in range(N)]
steps = [diff(loop[i], loop[i + 1])[0] for i in range(N - 1)]
wrap = diff(loop[N - 1], loop[0])[0]
near = steps[:5] + steps[-5:]
print(f"      循环内相邻帧差异：最小 {min(steps):.0f}，中位 {float(np.median(steps)):.0f}，最大 {max(steps):.0f} 像素")
report("循环 末帧→首帧 无跳动", wrap <= 1.5 * max(near), f"接缝 {wrap:.0f} 像素，接缝两侧各 5 帧为 {min(near):.0f}~{max(near):.0f}")

n_in = spec["segments"]["intro"]
a, b, c = alpha("intro", n_in - 2), alpha("intro", n_in - 1), loop[0]
report("开场→循环 无跳动", diff(b, c)[0] <= 1.5 * max(diff(a, b)[0], steps[0]) + 1,
       f"接缝 {diff(b, c)[0]:.0f} 像素，前一步 {diff(a, b)[0]:.0f}，后一步 {steps[0]:.0f}")
s, m = diff(loop[0], alpha("outro", 0))
report("收尾第 0 帧 = 循环第 0 帧", m <= 1, f"单像素最大差 {m}/255")
report("循环→收尾 无跳动", diff(loop[N - 1], alpha("outro", 0))[0] <= 1.5 * max(near),
       f"接缝 {diff(loop[N - 1], alpha('outro', 0))[0]:.0f} 像素")

print("\n全部通过" if ok else "\n有未通过的项")
sys.exit(0 if ok else 1)
