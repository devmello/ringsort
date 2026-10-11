"""Python port of the dataviz skill's validate_palette.js (same thresholds, Machado 2009 CVD, OKLab ΔE×100)."""
import math, sys
BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}; CHROMA_FLOOR = 0.10
CVD_TARGET, CVD_FLOOR, NORMAL_FLOOR, CONTRAST_MIN = 8.0, 6.0, 15.0, 3.0
M = {"protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
     "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
     "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]}
def srgb(h): h = h.lstrip("#"); return [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
def s2l(c): return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def lin(h): return [s2l(c) for c in srgb(h)]
def lum(h): r, g, b = lin(h); return 0.2126*r + 0.7152*g + 0.0722*b
def contrast(a, b): x, y = sorted([lum(a), lum(b)], reverse=True); return (x + .05) / (y + .05)
def oklab(rgb):
    r, g, b = rgb
    l = (0.4122214708*r + 0.5363325363*g + 0.0514459929*b) ** (1/3); m = (0.2119034982*r + 0.6806995451*g + 0.1073969566*b) ** (1/3); s = (0.0883024619*r + 0.2817188376*g + 0.6299787005*b) ** (1/3)
    return [0.2104542553*l + 0.7936177850*m - 0.0040720468*s, 1.9779984951*l - 2.4285922050*m + 0.4505937099*s, 0.0259040371*l + 0.7827717662*m - 0.8086757660*s]
def sim(h, k): r = lin(h); return [max(0, min(1, sum(M[k][i][j]*r[j] for j in range(3)))) for i in range(3)]
def dE(a, b, k=None): A = oklab(sim(a, k) if k else lin(a)); B = oklab(sim(b, k) if k else lin(b)); return 100 * math.dist(A, B)
def validate(pal, mode, surface):
    lo, hi = BAND[mode]; ok = True
    for c in pal:
        L, a, b = oklab(lin(c)); C = math.hypot(a, b)
        print(f"  {c}: L {L:.3f} {'ok' if lo <= L <= hi else 'OUT OF BAND'} · C {C:.3f} {'ok' if C >= CHROMA_FLOOR else 'GRAY'} · contrast {contrast(c, surface):.2f}:1 {'ok' if contrast(c, surface) >= CONTRAST_MIN else 'RELIEF (needs labels)'}")
        ok &= lo <= L <= hi and C >= CHROMA_FLOOR
    pairs = [(i, j) for i in range(len(pal)) for j in range(i+1, len(pal))]
    cvd = min((dE(pal[i], pal[j], k), k, pal[i], pal[j]) for k in ("protan", "deutan") for i, j in pairs)
    nor = min((dE(pal[i], pal[j]), pal[i], pal[j]) for i, j in pairs)
    print(f"  CVD all-pairs worst ΔE {cvd[0]:.1f} ({cvd[1]} {cvd[2]}↔{cvd[3]}) → {'PASS' if cvd[0] >= CVD_TARGET else 'FLOOR' if cvd[0] >= CVD_FLOOR else 'FAIL'}")
    print(f"  Normal-vision worst ΔE {nor[0]:.1f} ({nor[1]}↔{nor[2]}) → {'PASS' if nor[0] >= NORMAL_FLOOR else 'FAIL'}")
    return ok and cvd[0] >= CVD_FLOOR and nor[0] >= NORMAL_FLOOR
if __name__ == "__main__":
    pal = sys.argv[1].split(","); mode = sys.argv[2]; surface = sys.argv[3]
    print("OVERALL", "PASS" if validate(pal, mode, surface) else "FAIL")
