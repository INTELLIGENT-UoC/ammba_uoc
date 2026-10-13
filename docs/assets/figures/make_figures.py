"""Figures of the AMMBA documentation.

Regenerate from the repository root:

    uv run --no-project --with matplotlib --with numpy python docs/assets/figures/make_figures.py
"""

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

BLUE = "#2B3990"
ORANGE = "#E8622C"
TEAL = "#3A9E8F"
GREY = "#7A7A7A"
LIGHT_BLUE = "#E8EAF6"
LIGHT_ORANGE = "#FDEBE3"
LIGHT_TEAL = "#E3F2EF"
LIGHT_GREY = "#F2F2F2"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8.5,
        "axes.titlesize": 9,
        "axes.labelsize": 8.5,
        "legend.fontsize": 7.5,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
    }
)


def box(ax, x, y, w, h, text, edge=BLUE, fill=LIGHT_BLUE, dashed=False, bold_first=True, fs=7.6):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.3,
        edgecolor=edge,
        facecolor=fill,
        linestyle="--" if dashed else "-",
    )
    ax.add_patch(patch)
    lines = text.split("\n")
    n = len(lines)
    for i, line in enumerate(lines):
        yy = y + h / 2 + (n - 1) * 0.5 * 0.042 - i * 0.042
        ax.text(
            x + w / 2,
            yy,
            line,
            ha="center",
            va="center",
            fontsize=fs,
            fontweight="bold" if (bold_first and i == 0) else "normal",
            color="#1A1A1A",
        )
    return (x, y, w, h)


def arrow(
    ax,
    p0,
    p1,
    color=GREY,
    style="-|>",
    dashed=False,
    lw=1.2,
    rad=0.0,
    label=None,
    lpos=0.5,
    loff=(0, 0.025),
):
    a = FancyArrowPatch(
        p0,
        p1,
        arrowstyle=style,
        mutation_scale=10,
        color=color,
        linewidth=lw,
        linestyle="--" if dashed else "-",
        connectionstyle=f"arc3,rad={rad}",
        shrinkA=2,
        shrinkB=2,
    )
    ax.add_patch(a)
    if label:
        mx = p0[0] + (p1[0] - p0[0]) * lpos + loff[0]
        my = p0[1] + (p1[1] - p0[1]) * lpos + loff[1]
        ax.text(
            mx,
            my,
            label,
            ha="center",
            va="center",
            fontsize=6.8,
            color=color,
            style="italic",
            bbox=dict(facecolor="white", edgecolor="none", pad=0.6),
        )


def canvas(w_in, h_in):
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


# ── Figure 1: context ────────────────────────────────────────────────────
def fig_context(path):
    fig, ax = canvas(6.6, 3.4)
    box(
        ax,
        0.00,
        0.64,
        0.27,
        0.28,
        "Community participants\nhouseholds, prosumers,\nenergy management systems",
        fs=7.0,
    )
    box(
        ax,
        0.365,
        0.64,
        0.27,
        0.28,
        "GSY DEX off-chain storage\norders, markets,\nmeasurements (T3.2, D3.2)",
        fs=7.0,
    )
    box(
        ax,
        0.73,
        0.64,
        0.27,
        0.28,
        "Energy Web Digital Spine\nsecure data exchange\n(T3.1, D3.1)",
        edge=TEAL,
        fill=LIGHT_TEAL,
        fs=7.0,
    )
    frame = FancyBboxPatch(
        (0.455, 0.035),
        0.545,
        0.47,
        boxstyle="round,pad=0.008,rounding_size=0.02",
        linewidth=1.0,
        edgecolor=GREY,
        facecolor="white",
        linestyle=":",
    )
    ax.add_patch(frame)
    ax.text(
        0.7275,
        0.475,
        "matching mechanisms, selected per community and market",
        ha="center",
        va="center",
        fontsize=6.6,
        color=GREY,
        style="italic",
    )
    box(
        ax,
        0.475,
        0.07,
        0.24,
        0.34,
        "GSY DEX matching engine\npay-as-bid,\npay-as-clear\n(T5.1, D5.1)",
        fs=6.5,
    )
    box(
        ax,
        0.745,
        0.07,
        0.24,
        0.34,
        "AMMBA\nAMM batch clearing\n(T5.4, this repository)",
        edge=ORANGE,
        fill=LIGHT_ORANGE,
        fs=7.0,
    )
    box(
        ax,
        0.02,
        0.10,
        0.30,
        0.28,
        "Settlement and execution\non-chain verification;\nexecution engine (T5.2)",
        fs=7.0,
    )
    arrow(ax, (0.27, 0.78), (0.365, 0.78), label="orders", loff=(0, 0.055))
    arrow(ax, (0.635, 0.78), (0.73, 0.78), style="<|-|>")
    arrow(ax, (0.865, 0.64), (0.8, 0.505), style="<|-|>")
    arrow(ax, (0.455, 0.24), (0.32, 0.24), label="matches", loff=(0, 0.05))
    arrow(
        ax,
        (0.24, 0.38),
        (0.42, 0.64),
        dashed=True,
        label="settled trades",
        lpos=0.5,
        loff=(-0.085, 0.0),
    )
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ── Figure 2: pricing function and surplus split ────────────────────────
def fig_pricing(path):
    Ku, Kl, theta = 28.5, 8.0, 1.0
    r = np.linspace(0, 3, 600)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.6, 2.7))
    colors = {1.0: TEAL, 2.5: BLUE, 5.0: ORANGE}
    for B, c in colors.items():
        sig = 1 / (1 + np.exp(-B * (r - theta)))
        a1.plot(r, Ku - (Ku - Kl) * sig, color=c, lw=1.6, label=f"β = {B:g}")
        a2.plot(r, 100 * sig, color=c, lw=1.6, label=f"β = {B:g}")
    for a in (a1, a2):
        a.axvline(theta, color=GREY, lw=0.8, ls=":")
        a.grid(alpha=0.25, lw=0.5)
        a.set_xlabel("supply/demand ratio  r = S / D")
        a.set_xlim(0, 3)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
    a1.axhline(Ku, color=GREY, lw=0.8, ls="--")
    a1.axhline(Kl, color=GREY, lw=0.8, ls="--")
    a1.text(2.95, Ku + 0.5, "K_u  retail price", ha="right", va="bottom", fontsize=7, color=GREY)
    a1.text(2.95, Kl - 0.6, "K_l  feed-in tariff", ha="right", va="top", fontsize=7, color=GREY)
    a1.scatter([theta], [(Ku + Kl) / 2], color=BLUE, s=14, zorder=5)
    a1.text(theta + 0.07, (Ku + Kl) / 2 + 0.6, "midpoint at r = θ", fontsize=7, color=BLUE)
    a1.set_ylabel("clearing price p (ct/kWh)")
    a1.set_ylim(5, 31.5)
    a1.set_title("(a) Clearing price", loc="left")
    a1.legend(frameon=False, loc="center right")
    a2.axhline(50, color=GREY, lw=0.8, ls="--")
    a2.set_ylabel("buyers' share of gains from trade (%)")
    a2.set_ylim(-3, 103)
    a2.set_title("(b) Split of the gains from local trade", loc="left")
    a2.text(2.95, 47, "even split", ha="right", va="top", fontsize=7, color=GREY)
    a2.text(0.05, 92, "scarce supply:\nsellers gain more", fontsize=6.8, color=GREY, va="top")
    a2.text(
        2.95,
        12,
        "abundant supply:\nbuyers gain more",
        fontsize=6.8,
        color=GREY,
        ha="right",
        va="bottom",
    )
    fig.tight_layout(w_pad=2.0)
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ── Figure 3: pool-mediated clearing of one slot (worked example) ───────
def fig_pool(path):
    fig, ax = canvas(6.6, 3.2)
    Ku, Kl, B, theta = 28.5, 8.0, 2.5, 1.0
    S, D = 9.0, 10.0
    price = Ku - (Ku - Kl) / (1 + math.exp(-B * (S / D - theta)))
    box(ax, 0.01, 0.66, 0.20, 0.22, "Seller S1\noffers 5.0 kWh", edge=TEAL, fill=LIGHT_TEAL)
    box(ax, 0.01, 0.34, 0.20, 0.22, "Seller S2\noffers 4.0 kWh", edge=TEAL, fill=LIGHT_TEAL)
    box(ax, 0.79, 0.66, 0.20, 0.22, "Buyer B1\nbids 6.0 kWh", edge=BLUE, fill=LIGHT_BLUE)
    box(ax, 0.79, 0.34, 0.20, 0.22, "Buyer B2\nbids 4.0 kWh", edge=BLUE, fill=LIGHT_BLUE)
    box(
        ax,
        0.31,
        0.36,
        0.38,
        0.50,
        f"AMM pool (one slot)\nS = 9.0 kWh,  D = 10.0 kWh\nr = S/D = 0.90\np = {price:.2f} ct/kWh\nQ = min(S, D) = 9.0 kWh\nbudget balance: 175.72 ct in = out",
        edge=ORANGE,
        fill=LIGHT_ORANGE,
        fs=7.1,
    )
    box(
        ax,
        0.25,
        0.02,
        0.48,
        0.17,
        "External grid (fallback)\nimport at K_u = 28.5 ct/kWh,  export at K_l = 8.0 ct/kWh",
        edge=GREY,
        fill=LIGHT_GREY,
        fs=7.2,
    )
    arrow(ax, (0.21, 0.77), (0.31, 0.70), color=TEAL, label="5.0 kWh", loff=(0, 0.045))
    arrow(ax, (0.21, 0.45), (0.31, 0.52), color=TEAL, label="4.0 kWh", loff=(0, -0.045))
    arrow(ax, (0.69, 0.70), (0.79, 0.77), color=BLUE, label="5.4 kWh", loff=(0, 0.045))
    arrow(ax, (0.69, 0.52), (0.79, 0.45), color=BLUE, label="3.6 kWh", loff=(0, -0.045))
    arrow(
        ax,
        (0.70, 0.12),
        (0.89, 0.34),
        color=GREY,
        dashed=True,
        rad=0.2,
        label="residual demand 1.0 kWh\n(0.6 to B1, 0.4 to B2)",
        lpos=0.55,
        loff=(0.09, -0.03),
    )
    ax.text(
        0.5,
        0.94,
        "energy flows shown;  every flow is priced at the uniform clearing price p",
        ha="center",
        fontsize=7,
        color=GREY,
        style="italic",
    )
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ── Figure 4: community-owned parameter cycle ───────────────────────────
def fig_governance(path):
    fig, ax = canvas(6.6, 3.6)
    stages = [
        ("1  Collect", "per-slot aggregates of\ncommunity metering data", BLUE, LIGHT_BLUE),
        ("2  Calibrate", "θ and β for candidate α\n(calibration tool, offline)", BLUE, LIGHT_BLUE),
        ("3  Assess", "back-test prices and the\nsplit of gains from trade", BLUE, LIGHT_BLUE),
        ("4  Decide", "members approve normative\nchoices (α, penalties)", ORANGE, LIGHT_ORANGE),
        ("5  Publish", "versioned parameter set,\neffective from a future slot", BLUE, LIGHT_BLUE),
        ("6  Operate", "clearing applies only the\npublished parameters", TEAL, LIGHT_TEAL),
    ]
    cx, cy, rx, ry = 0.5, 0.50, 0.36, 0.33
    w, h = 0.25, 0.20
    centers = []
    for k in range(6):
        ang = math.pi / 2 - k * 2 * math.pi / 6
        x, y = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
        centers.append((x, y))
    for (x, y), (title, body, e, f) in zip(centers, stages, strict=False):
        box(ax, x - w / 2, y - h / 2, w, h, f"{title}\n{body}", edge=e, fill=f, fs=7.0)

    def edge_point(cxy, ux, uy, gap=0.012):
        tx = (w / 2) / abs(ux) if abs(ux) > 1e-9 else float("inf")
        ty = (h / 2) / abs(uy) if abs(uy) > 1e-9 else float("inf")
        t = min(tx, ty) + gap
        return (cxy[0] + ux * t, cxy[1] + uy * t)

    for k in range(6):
        x0, y0 = centers[k]
        x1, y1 = centers[(k + 1) % 6]
        d = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / d, (y1 - y0) / d
        arrow(ax, edge_point((x0, y0), ux, uy), edge_point((x1, y1), -ux, -uy), rad=-0.12)
    ax.text(
        cx,
        cy + 0.03,
        "Community-owned\nparameter cycle",
        ha="center",
        va="center",
        fontsize=8.6,
        fontweight="bold",
        color=BLUE,
    )
    ax.text(
        cx,
        cy - 0.07,
        "e.g. seasonal, or after major\nchanges in members or assets",
        ha="center",
        va="center",
        fontsize=6.8,
        color=GREY,
        style="italic",
    )
    handles = [
        plt.Line2D([], [], marker="s", ls="", color=BLUE, label="community manager"),
        plt.Line2D([], [], marker="s", ls="", color=ORANGE, label="community members"),
        plt.Line2D([], [], marker="s", ls="", color=TEAL, label="platform (no discretion)"),
    ]
    ax.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=3,
        frameon=False,
        fontsize=7,
    )
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ── Figure 5: software components ───────────────────────────────────────
def fig_components(path):
    fig, ax = canvas(6.6, 3.4)
    box(
        ax,
        0.00,
        0.66,
        0.25,
        0.26,
        "Metering history\nper-slot energy records\nof the community",
        edge=GREY,
        fill=LIGHT_GREY,
        fs=7.0,
    )
    box(
        ax,
        0.36,
        0.66,
        0.28,
        0.26,
        "Calibration tool\namm-calibration\noffline, run by the community",
        edge=ORANGE,
        fill=LIGHT_ORANGE,
        fs=7.0,
    )
    box(
        ax,
        0.36,
        0.18,
        0.28,
        0.28,
        "Clearing engine\namm-clearing-node\npricing, allocation, trades",
        edge=ORANGE,
        fill=LIGHT_ORANGE,
        fs=7.0,
    )
    box(
        ax,
        0.75,
        0.18,
        0.25,
        0.28,
        "Off-chain storage\nlocal simulator in D1\norders, trades, results",
        edge=ORANGE,
        fill=LIGHT_ORANGE,
        fs=7.0,
    )
    box(
        ax,
        0.75,
        0.66,
        0.25,
        0.22,
        "Audit anchor\namm-smart-contract\n(optional)",
        edge=BLUE,
        fill=LIGHT_BLUE,
        fs=7.0,
    )
    box(
        ax,
        0.00,
        0.18,
        0.25,
        0.28,
        "Settlement engine (v2)\nand EWDS transport",
        edge=GREY,
        fill="white",
        dashed=True,
        fs=7.0,
    )
    arrow(ax, (0.25, 0.79), (0.36, 0.79))
    arrow(ax, (0.50, 0.66), (0.50, 0.46), label="parameters θ, β", lpos=0.5, loff=(0.085, 0.0))
    arrow(ax, (0.75, 0.38), (0.64, 0.38), label="orders", loff=(0, 0.04))
    arrow(ax, (0.64, 0.26), (0.75, 0.26), label="trades, result", loff=(0, -0.045))
    arrow(ax, (0.62, 0.46), (0.78, 0.66), dashed=True, color=BLUE)
    arrow(ax, (0.36, 0.32), (0.25, 0.32), dashed=True, color="#AAAAAA")
    handles = [
        plt.Line2D([], [], marker="s", ls="", color=ORANGE, label="core (V1)"),
        plt.Line2D([], [], marker="s", ls="", color=BLUE, label="optional"),
        plt.Line2D([], [], marker="s", ls="", color="#AAAAAA", label="integration and v2"),
    ]
    ax.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=3,
        frameon=False,
        fontsize=7,
    )
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    out = Path(__file__).parent
    fig_context(out / "context.png")
    fig_pricing(out / "pricing.png")
    fig_pool(out / "pool.png")
    fig_governance(out / "governance.png")
    fig_components(out / "components.png")
    print(f"figures written to {out}")
