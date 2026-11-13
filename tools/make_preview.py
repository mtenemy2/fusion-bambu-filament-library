"""Social preview (1280x640) for the GitHub repo, drawn from the real Bambu color data."""
import colorsys, json, sys
from PIL import Image, ImageDraw, ImageFont

data_path, out_path = sys.argv[1], sys.argv[2]
S = 2                                   # supersample
W, H = 1280 * S, 640 * S
BG = (17, 19, 24)
FG = (240, 242, 245)
MUTED = (150, 156, 168)
ACCENT = (0, 174, 66)                   # Bambu Green filament hex #00AE42 (from the data)
F = "C:/Windows/Fonts/"
font = lambda name, px: ImageFont.truetype(F + name, px * S)

recs = json.load(open(data_path, encoding="utf-8"))
n_colors, n_lines = len(recs), len({r["line"] for r in recs})

# ---- choose swatches: solid colors, unique hex, sorted by hue bands then lightness
seen, sw = set(), []
for r in recs:
    h = r["hex"][0]
    if r["color_type"] != "solid" or h in seen:
        continue
    seen.add(h)
    rgb = tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    hh, ll, ss = colorsys.rgb_to_hls(*[c / 255 for c in rgb])
    sw.append((rgb, hh, ll, ss))
chroma = [s for s in sw if s[3] > 0.18 and 0.12 < s[2] < 0.92]
neutral = [s for s in sw if s not in chroma]
chroma.sort(key=lambda s: (round(s[1] * 12) % 12, -s[2]))
neutral.sort(key=lambda s: -s[2])

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# ---- right side: swatch field (circles like spool ends), hue flows left -> right, bleeds off the right edge
cols, rows = 10, 12
cell = 54 * S
x0 = 735 * S
y0 = (H - rows * cell) // 2
need_c = cols * (rows - 2)
pick = [chroma[int(i * len(chroma) / need_c)] for i in range(need_c)]
need_n = cols * rows - len(pick)
pick += [neutral[int(i * len(neutral) / need_n)] for i in range(need_n)]
# column-major: each column is one hue band, light -> dark going down; neutrals fill the last columns
for i, (rgb, *_) in enumerate(pick):
    c, rr = divmod(i, rows)
    cx = x0 + c * cell + cell // 2 + (cell // 2 if rr % 2 else 0)
    cy = y0 + rr * cell + cell // 2
    rad = int(cell * 0.42)
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=rgb)
    ir = int(rad * 0.30)                                         # spool hole
    d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=tuple(int(v * 0.5 + b * 0.5) for v, b in zip(rgb, BG)))

# soft fade on the left edge of the field only
fade_w = 110 * S
grad = Image.new("L", (fade_w, H))
gd = ImageDraw.Draw(grad)
for i in range(fade_w):
    gd.line([(i, 0), (i, H)], fill=int(255 * (1 - i / fade_w) ** 2))
img.paste(Image.new("RGB", (fade_w, H), BG), (x0 - 10 * S, 0), grad)

# ---- left side: text
L = 72 * S
d.rounded_rectangle([L, 92 * S, L + 236 * S, 128 * S], radius=18 * S, outline=ACCENT, width=2 * S)
d.text((L + 18 * S, 110 * S), "FOR AUTODESK FUSION", font=font("seguisb.ttf", 17), fill=ACCENT, anchor="lm")

d.text((L, 160 * S), "Bambu Lab", font=font("segoeuib.ttf", 76), fill=FG)
d.text((L, 246 * S), "Filament Library", font=font("segoeuib.ttf", 76), fill=FG)
d.text((L, 352 * S), "뱀부랩 필라멘트 색상 · 물성 라이브러리", font=font("malgun.ttf", 27), fill=MUTED)

# stats
y = 430 * S
x = L
for num, label in [(str(n_colors), "colors"), (str(n_lines), "product lines"), ("Auto", "updates")]:
    d.text((x, y), num, font=font("segoeuib.ttf", 40), fill=FG)
    nw = d.textlength(num, font=font("segoeuib.ttf", 40))
    d.text((x + nw + 10 * S, y + 17 * S), label, font=font("segoeui.ttf", 21), fill=MUTED)
    x += nw + 10 * S + d.textlength(label, font=font("segoeui.ttf", 21)) + 40 * S

d.text((L, 548 * S), "Official colors as appearances  ·  Bambu TDS values as physical materials",
       font=font("segoeui.ttf", 19), fill=MUTED)

img = img.resize((1280, 640), Image.LANCZOS)
img.save(out_path, optimize=True)
print(out_path, len(pick), "swatches")
