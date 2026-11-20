import math, sys
from PIL import Image, ImageDraw

out_dir = sys.argv[1]
S = 1024           # supersampled canvas
k = S / 256        # design units are 256px

def P(x, y): return (x * k, y * k)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# --- base: same look as the overlay icon (cyan ring, dark disc, green bolt) ---
cx, cy = 128, 128
d.ellipse([P(cx-118, cy-118), P(cx+118, cy+118)], fill=(0, 240, 255, 255))
d.ellipse([P(cx-107, cy-107), P(cx+107, cy+107)], fill=(220, 235, 245, 255))
d.ellipse([P(cx-105, cy-105), P(cx+105, cy+105)], fill=(17, 21, 31, 255))

bolt = [(150, 52), (95, 138), (127, 138), (112, 202), (168, 113), (136, 113)]
dx, dy = -16, -14   # nudge the bolt up-left to make room for the brush
d.polygon([P(x+dx, y+dy) for x, y in bolt], fill=(57, 255, 20, 255))

# --- paintbrush badge (bottom-right) ---
bx, by, br = 186, 186, 62
d.ellipse([P(bx-br, by-br), P(bx+br, by+br)], fill=(0, 240, 255, 255))
d.ellipse([P(bx-br+7, by-br+7), P(bx+br-7, by+br-7)], fill=(11, 14, 22, 255))

def segment(a, b, w0, w1, color):
    """Quad from point a to b with widths w0 (at a) and w1 (at b)."""
    ax, ay = a; bx_, by_ = b
    vx, vy = bx_-ax, by_-ay
    L = math.hypot(vx, vy); nx, ny = -vy/L, vx/L
    pts = [(ax+nx*w0/2, ay+ny*w0/2), (bx_+nx*w1/2, by_+ny*w1/2),
           (bx_-nx*w1/2, by_-ny*w1/2), (ax-nx*w0/2, ay-ny*w0/2)]
    d.polygon([P(*p) for p in pts], fill=color)

def lerp(a, b, t): return (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t)

start = (222, 150)   # handle end (top-right)
tip = (152, 222)     # bristle tip (bottom-left)
h_end = lerp(start, tip, 0.50)
f_end = lerp(start, tip, 0.64)

# handle (purple, rounded end)
segment(start, h_end, 13, 17, (176, 38, 255, 255))
r = 6.5
d.ellipse([P(start[0]-r, start[1]-r), P(start[0]+r, start[1]+r)], fill=(176, 38, 255, 255))
# ferrule (silver)
segment(h_end, f_end, 21, 21, (200, 211, 230, 255))
segment(lerp(h_end, f_end, 0.45), lerp(h_end, f_end, 0.6), 21.5, 21.5, (120, 132, 156, 255))
# bristles (cyan paint, tapering to a point)
b_mid = lerp(f_end, tip, 0.55)
segment(f_end, b_mid, 21, 18, (0, 240, 255, 255))
segment(b_mid, tip, 18, 2, (0, 240, 255, 255))
# paint highlight
segment(lerp(f_end, tip, 0.1), lerp(f_end, tip, 0.7), 4, 2, (180, 252, 255, 255))

big = img.resize((256, 256), Image.LANCZOS)
big.save(f"{out_dir}/icon.png")
big.save(f"{out_dir}/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ok")
