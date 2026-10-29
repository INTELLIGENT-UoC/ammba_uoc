"""Figures of the AMMBA documentation.

Regenerate from the repository root:

    uv run --no-project --python 3.13 --with matplotlib --with numpy python docs/assets/figures/make_figures.py

Diagrams are drawn on a unit square that fills the whole figure, and nothing is
clipped at its edges. After drawing, every diagram is checked: box texts must
fit inside their boxes with a margin, boxes must not overlap, and free labels
must keep a small clearance from every box. The script fails if a check
fails.

The notation follows Saber et al. (2026), Applied Energy 416, 127957
(https://doi.org/10.1016/j.apenergy.2026.127957), which is also the source of
the evaluation data in ``fig_kpis``.
"""

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.transforms import Bbox

BLUE = "#2B3990"
ORANGE = "#E8622C"
TEAL = "#3A9E8F"
GREY = "#7A7A7A"
INK = "#1A1A1A"
LIGHT_BLUE = "#E8EAF6"
LIGHT_ORANGE = "#FDEBE3"
LIGHT_TEAL = "#E3F2EF"
LIGHT_GREY = "#F2F2F2"
DPI = 220
TEXT_MARGIN_PT = 3.5  # minimum horizontal gap between a box border and its text
LABEL_CLEARANCE_PT = 2.5  # minimum gap between a free label and any box

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8.5,
        "axes.titlesize": 9,
        "axes.labelsize": 8.5,
        "legend.fontsize": 7.5,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "mathtext.default": "it",
    }
)


def _lines(text):
    if not text:
        return []
    return [text] if isinstance(text, str) else list(text)


class Diagram:
    """Box-and-arrow diagram on a unit square that fills the whole figure."""

    def __init__(self, width_in, height_in):
        self.fig = plt.figure(figsize=(width_in, height_in))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(0, 1)
        self.ax.axis("off")
        self.boxes = []  # (patch, texts, name)
        self.frames = []  # (patch, caption)
        self.labels = []  # free texts that must not overlap any box

    def _text(self, xy, text, offset=(0, 0), **kw):
        return self.ax.annotate(
            text,
            xy=xy,
            xytext=offset,
            textcoords="offset points",
            ha=kw.pop("ha", "center"),
            va=kw.pop("va", "center"),
            annotation_clip=False,
            **kw,
        )

    def box(self, x, y, w, h, title, body=(), edge=BLUE, fill=LIGHT_BLUE, dashed=False, fs=7.0):
        patch = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.015",
            linewidth=1.3,
            edgecolor=edge,
            facecolor=fill,
            linestyle="--" if dashed else "-",
            clip_on=False,
            zorder=2,
        )
        self.ax.add_patch(patch)
        lines = [(t, "bold") for t in _lines(title)] + [(t, "normal") for t in _lines(body)]
        step = fs * 1.3
        texts = []
        for i, (line, weight) in enumerate(lines):
            offset = (0, ((len(lines) - 1) / 2 - i) * step)
            texts.append(
                self._text(
                    (x + w / 2, y + h / 2),
                    line,
                    offset,
                    fontsize=fs,
                    fontweight=weight,
                    color=INK,
                    zorder=3,
                )
            )
        self.boxes.append((patch, texts, lines[0][0]))
        return (x, y, w, h)

    def frame(self, x, y, w, h, caption, fs=6.6):
        patch = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.015",
            linewidth=1.0,
            edgecolor=GREY,
            facecolor="white",
            linestyle=":",
            clip_on=False,
            zorder=1,
        )
        self.ax.add_patch(patch)
        caption = self._text(
            (x + w / 2, y + h), caption, (0, -1.4 * fs), fontsize=fs, color=GREY, style="italic"
        )
        self.frames.append((patch, caption))

    def arrow(
        self,
        p0,
        p1,
        color=GREY,
        style="-|>",
        dashed=False,
        rad=0.0,
        label=None,
        lpos=0.5,
        offset=(0, 8),
        fs=6.8,
    ):
        self.ax.add_patch(
            FancyArrowPatch(
                p0,
                p1,
                arrowstyle=style,
                mutation_scale=10,
                color=color,
                linewidth=1.2,
                linestyle="--" if dashed else "-",
                connectionstyle=f"arc3,rad={rad}",
                shrinkA=1,
                shrinkB=1,
                clip_on=False,
                zorder=1.5,
            )
        )
        if label:
            xy = (p0[0] + (p1[0] - p0[0]) * lpos, p0[1] + (p1[1] - p0[1]) * lpos)
            self.note(xy, label, offset, color=color, fs=fs, background=True)

    def note(self, xy, text, offset=(0, 0), color=GREY, fs=6.8, background=False, **kw):
        bbox = dict(facecolor="white", edgecolor="none", pad=0.8) if background else None
        t = self._text(
            xy, text, offset, fontsize=fs, color=color, style="italic", bbox=bbox, zorder=4, **kw
        )
        self.labels.append(t)
        return t

    def check(self, name):
        """Fail if any text leaves its box or any label covers a box."""
        self.fig.canvas.draw()
        renderer = self.fig.canvas.get_renderer()
        px = self.fig.dpi / 72
        errors = []

        def extent(artist):
            patch = artist.get_bbox_patch() if hasattr(artist, "get_bbox_patch") else None
            return (patch or artist).get_window_extent(renderer)

        boxes = [(p.get_window_extent(renderer), texts, n) for p, texts, n in self.boxes]
        for bb, texts, box_name in boxes:
            for t in texts:
                tb = t.get_window_extent(renderer)
                inside_x = (
                    tb.x0 >= bb.x0 + TEXT_MARGIN_PT * px and tb.x1 <= bb.x1 - TEXT_MARGIN_PT * px
                )
                inside_y = tb.y0 >= bb.y0 + px and tb.y1 <= bb.y1 - px
                if not (inside_x and inside_y):
                    errors.append(f"text {t.get_text()!r} does not fit into box {box_name!r}")
        for i, (a, _, na) in enumerate(boxes):
            for b, _, nb in boxes[i + 1 :]:
                if a.overlaps(b):
                    errors.append(f"boxes {na!r} and {nb!r} overlap")
        clearance = LABEL_CLEARANCE_PT * px
        for label in self.labels:
            e = extent(label)
            lb = Bbox.from_extents(
                e.x0 - clearance, e.y0 - clearance, e.x1 + clearance, e.y1 + clearance
            )
            for bb, _, box_name in boxes:
                if lb.overlaps(bb):
                    errors.append(f"label {label.get_text()!r} overlaps box {box_name!r}")
        for patch, caption in self.frames:
            fb, cb = patch.get_window_extent(renderer), extent(caption)
            if not (fb.x0 < cb.x0 and cb.x1 < fb.x1 and fb.y0 < cb.y0 and cb.y1 < fb.y1):
                errors.append(f"frame caption {caption.get_text()!r} leaves its frame")
            for bb, _, box_name in boxes:
                if cb.overlaps(bb):
                    errors.append(f"frame caption {caption.get_text()!r} overlaps {box_name!r}")
        if errors:
            raise SystemExit(f"layout check failed for {name}:\n  " + "\n  ".join(errors))

    def save(self, path):
        self.check(Path(path).name)
        self.fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.06, facecolor="white")
        plt.close(self.fig)


def legend(ax, entries, y=-0.02):
    handles = [
        plt.Line2D([], [], marker="s", ls="", markersize=7, color=c, label=t) for t, c in entries
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, y),
        ncol=len(entries),
        frameon=False,
        fontsize=7,
        handletextpad=0.4,
        columnspacing=1.6,
    )


# ── Architecture: AMMBA in the GSY DEX, with the EWDS as the interface ───
def fig_architecture(path, ammba_note="(this repository)"):
    d = Diagram(6.8, 5.0)
    # Services and actors above the data spine.
    d.box(0.01, 0.81, 0.19, 0.15, "Community members", ["households,", "prosumers"])
    d.box(
        0.25,
        0.81,
        0.19,
        0.15,
        "Forecasting service",
        ["forecasts and", "trading preferences"],
        edge=GREY,
        fill=LIGHT_GREY,
    )
    d.box(0.49, 0.81, 0.19, 0.15, "Grid operator", ["retail price, feed-in", "tariff, grid fees"])
    d.box(
        0.74,
        0.81,
        0.25,
        0.15,
        "Post-trade services",
        ["billing and payment,", "analytics, user interfaces"],
    )
    d.box(
        0.01,
        0.645,
        0.98,
        0.095,
        "Energy Web Digital Spine (EWDS)",
        "authenticated exchange of orders, tariffs, trades and clearing results between the services",
        edge=TEAL,
        fill=LIGHT_TEAL,
        fs=6.8,
    )
    # GSY DEX spot market below the spine.
    d.frame(0.01, 0.185, 0.98, 0.395, " ")
    d.note((0.02, 0.555), "GSY DEX spot market", ha="left", fs=6.8)
    d.box(
        0.03,
        0.25,
        0.53,
        0.24,
        ["AMMBA: AMM-based batch auction", ammba_note],
        [
            "collects the orders of each 15-minute slot in one batch,",
            "prices the batch from its supply-to-demand ratio,",
            "allocates the traded energy pro rata through the pool",
        ],
        edge=ORANGE,
        fill=LIGHT_ORANGE,
        fs=7.0,
    )
    d.box(
        0.68,
        0.36,
        0.29,
        0.15,
        ["GSY DEX", "Execution Engine"],
        ["verifies delivery,", "settles on-chain"],
    )
    d.box(
        0.68,
        0.21,
        0.29,
        0.10,
        "GSY DEX matching engine",
        ["pay-as-bid, pay-as-clear"],
        edge=GREY,
        fill="white",
        dashed=True,
        fs=6.6,
    )
    # Calibration below the market.
    d.box(0.03, 0.015, 0.20, 0.12, "Community manager", ["or another designated", "administrator"])
    d.box(
        0.33,
        0.015,
        0.23,
        0.12,
        "Calibration tool",
        [r"$\Theta$ and $B$ from the", "metering history"],
        edge=ORANGE,
        fill=LIGHT_ORANGE,
    )
    # Flows.
    d.arrow((0.20, 0.885), (0.25, 0.885), label="data", offset=(0, 8))
    d.arrow((0.345, 0.81), (0.345, 0.74), label="orders", offset=(20, 0))
    d.arrow((0.345, 0.645), (0.345, 0.49), label="orders", offset=(20, 0))
    d.arrow((0.585, 0.81), (0.585, 0.74), label="tariffs", offset=(20, 0))
    d.arrow((0.50, 0.645), (0.50, 0.49), label="price band", offset=(28, 0))
    d.arrow((0.56, 0.435), (0.68, 0.435), label="trades,", offset=(0, 16))
    d.note((0.62, 0.435), "clearing result", offset=(0, 8), fs=6.8, background=True)
    d.arrow((0.825, 0.31), (0.825, 0.36), dashed=True, color="#9A9A9A")
    d.arrow((0.865, 0.51), (0.865, 0.645), label="settled trades", lpos=0.78, offset=(-36, 0))
    d.arrow((0.865, 0.74), (0.865, 0.81))
    d.arrow((0.23, 0.075), (0.33, 0.075), label="runs", offset=(0, 8))
    d.arrow((0.445, 0.135), (0.445, 0.25), label=r"$\Theta$, $B$", offset=(14, 0))
    d.save(path)


# ── Pricing function and split of the gains from trade ──────────────────
def fig_pricing(path):
    k_up, k_lo, midpoint = 28.5, 8.0, 1.0
    r = np.linspace(0, 3, 600)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.8, 2.75))
    for steepness, colour in {1.0: TEAL, 2.5: BLUE, 5.0: ORANGE}.items():
        share = 1 / (1 + np.exp(-steepness * (r - midpoint)))
        a1.plot(r, k_up - (k_up - k_lo) * share, color=colour, lw=1.6, label=f"$B$ = {steepness:g}")
        a2.plot(r, 100 * share, color=colour, lw=1.6, label=f"$B$ = {steepness:g}")
    for a in (a1, a2):
        a.axvline(midpoint, color=GREY, lw=0.8, ls=":")
        a.grid(alpha=0.25, lw=0.5)
        a.set_xlabel("supply-to-demand ratio $r$")
        a.set_xlim(0, 3)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
    a1.axhline(k_up, color=GREY, lw=0.8, ls="--")
    a1.axhline(k_lo, color=GREY, lw=0.8, ls="--")
    a1.text(
        2.95,
        k_up + 0.5,
        r"$K_{\mathrm{up}}$  retail price",
        ha="right",
        va="bottom",
        fontsize=7,
        color=GREY,
    )
    a1.text(
        2.95,
        k_lo - 0.6,
        r"$K_{\mathrm{lo}}$  feed-in tariff",
        ha="right",
        va="top",
        fontsize=7,
        color=GREY,
    )
    a1.scatter([midpoint], [(k_up + k_lo) / 2], color=BLUE, s=14, zorder=5)
    a1.text(
        midpoint + 0.07,
        (k_up + k_lo) / 2 + 0.6,
        r"midpoint at $r = \Theta$",
        fontsize=7,
        color=BLUE,
    )
    a1.set_ylabel(r"clearing price $\pi$ (ct/kWh)")
    a1.set_ylim(5, 31.5)
    a1.set_title("(a) Clearing price", loc="left")
    a1.legend(frameon=False, loc="center right")
    a2.axhline(50, color=GREY, lw=0.8, ls="--")
    a2.set_ylabel("buyers' share of the gains (%)")
    a2.set_ylim(-3, 103)
    a2.set_title("(b) Split of the gains from local trade", loc="left")
    a2.text(2.95, 47, "even split", ha="right", va="top", fontsize=7, color=GREY)
    a2.text(0.03, 95, "scarce supply:\nsellers gain more", fontsize=6.4, color=GREY, va="top")
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
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.06, facecolor="white")
    plt.close(fig)


# ── Pool-mediated clearing of one slot (worked example) ─────────────────
def fig_pool(path):
    k_up, k_lo, steepness, midpoint = 28.5, 8.0, 2.5, 1.0
    supply, demand = 9.0, 10.0
    price = k_up - (k_up - k_lo) / (1 + math.exp(-steepness * (supply / demand - midpoint)))
    paid = price * min(supply, demand)
    d = Diagram(6.8, 3.4)
    d.note(
        (0.5, 0.965),
        r"energy flows of one slot; every flow is priced at the uniform clearing price $\pi$",
        fs=7.0,
    )
    d.box(0.01, 0.64, 0.19, 0.22, "Seller S1", "offers 5.0 kWh", edge=TEAL, fill=LIGHT_TEAL)
    d.box(0.01, 0.31, 0.19, 0.22, "Seller S2", "offers 4.0 kWh", edge=TEAL, fill=LIGHT_TEAL)
    d.box(0.80, 0.64, 0.19, 0.22, "Buyer B1", "bids 6.0 kWh")
    d.box(0.80, 0.31, 0.19, 0.22, "Buyer B2", "bids 4.0 kWh")
    d.box(
        0.31,
        0.29,
        0.38,
        0.59,
        "AMM pool (one slot)",
        [
            r"$E$ = 9.0 kWh,  $D$ = 10.0 kWh",
            r"$r$ = $E / D$ = 0.90",
            rf"$\pi$ = {price:.2f} ct/kWh",
            r"$Q$ = min($E$, $D$) = 9.0 kWh",
            f"buyers pay {paid:.2f} ct,",
            f"sellers receive {paid:.2f} ct",
        ],
        edge=ORANGE,
        fill=LIGHT_ORANGE,
        fs=7.2,
    )
    d.box(
        0.40,
        0.02,
        0.59,
        0.15,
        "External grid (fallback)",
        r"import at $K_{\mathrm{up}}$ = 28.5 ct/kWh,  export at $K_{\mathrm{lo}}$ = 8.0 ct/kWh",
        edge=GREY,
        fill=LIGHT_GREY,
    )
    d.arrow((0.20, 0.75), (0.31, 0.68), color=TEAL, label="5.0 kWh", offset=(0, 10))
    d.arrow((0.20, 0.42), (0.31, 0.49), color=TEAL, label="4.0 kWh", offset=(0, -10))
    d.arrow((0.69, 0.68), (0.80, 0.75), color=BLUE, label="5.4 kWh", offset=(0, 10))
    d.arrow((0.69, 0.49), (0.80, 0.42), color=BLUE, label="3.6 kWh", offset=(0, -10))
    d.arrow((0.895, 0.17), (0.895, 0.31), dashed=True)
    d.note((0.79, 0.235), "residual demand 1.0 kWh\n(0.6 to B1, 0.4 to B2)", fs=6.8)
    d.save(path)


# ── Community-owned parameter cycle ──────────────────────────────────────
def fig_governance(path):
    stages = [
        ("1  Collect", ["per-slot aggregates of", "community metering data"], BLUE, LIGHT_BLUE),
        (
            "2  Calibrate",
            [r"$\Theta$ and $B$ for candidate $\alpha$", "(calibration tool, offline)"],
            BLUE,
            LIGHT_BLUE,
        ),
        (
            "3  Assess",
            ["back-test prices and the", "split of the gains from trade"],
            BLUE,
            LIGHT_BLUE,
        ),
        (
            "4  Decide",
            ["members approve the", r"normative choices ($\alpha$, penalties)"],
            ORANGE,
            LIGHT_ORANGE,
        ),
        (
            "5  Publish",
            ["versioned parameter set,", "effective from a future slot"],
            BLUE,
            LIGHT_BLUE,
        ),
        ("6  Operate", ["clearing applies only the", "published parameters"], TEAL, LIGHT_TEAL),
    ]
    d = Diagram(6.8, 3.6)
    w, h = 0.27, 0.25
    xs = (0.02, 0.365, 0.71)
    top, bottom = 0.68, 0.10
    # Clockwise loop: 1-2-3 along the top row, 4-5-6 back along the bottom row.
    slots = [
        (xs[0], top),
        (xs[1], top),
        (xs[2], top),
        (xs[2], bottom),
        (xs[1], bottom),
        (xs[0], bottom),
    ]
    for (x, y), (title, body, edge, fill) in zip(slots, stages, strict=True):
        d.box(x, y, w, h, title, body, edge=edge, fill=fill)
    for k in (0, 1):
        d.arrow((xs[k] + w, top + h / 2), (xs[k + 1], top + h / 2))
        d.arrow((xs[k + 1], bottom + h / 2), (xs[k] + w, bottom + h / 2))
    d.arrow((xs[2] + w / 2, top), (xs[2] + w / 2, bottom + h))
    d.arrow((xs[0] + w / 2, bottom + h), (xs[0] + w / 2, top))
    d.note((0.5, 0.555), "Community-owned parameter cycle", color=BLUE, fs=8.6, fontweight="bold")
    d.labels[-1].set_style("normal")
    d.note((0.5, 0.455), "e.g. seasonal, or after major changes in members or assets", fs=6.8)
    legend(
        d.ax,
        [
            ("community manager or other administrator", BLUE),
            ("community members, through their governance system", ORANGE),
            ("platform (no discretion)", TEAL),
        ],
    )
    d.save(path)


# ── Software components ──────────────────────────────────────────────────
COMPONENT_TEXT = {
    "storage": ["GSY DEX via EWDS,", "or local simulator"],
    "settlement": ["amm-execution-node", "(in development)"],
    "matches": "trades",
    "legend": ("core components", "optional", "in development"),
}


def fig_components(path, text=None):
    text = {**COMPONENT_TEXT, **(text or {})}
    d = Diagram(6.8, 3.4)
    d.box(
        0.01,
        0.64,
        0.24,
        0.28,
        "Administrator",
        ["e.g. the community", "manager"],
        edge=GREY,
        fill=LIGHT_GREY,
    )
    d.box(
        0.35,
        0.64,
        0.28,
        0.28,
        "Calibration tool",
        ["amm-calibration", "offline, on a", "measurement snapshot"],
        edge=ORANGE,
        fill=LIGHT_ORANGE,
    )
    d.box(
        0.75,
        0.66,
        0.24,
        0.24,
        "Audit anchor",
        ["amm-smart-contract", "(optional)"],
        edge=BLUE,
        fill=LIGHT_BLUE,
    )
    d.box(
        0.35,
        0.14,
        0.28,
        0.30,
        "Clearing engine",
        ["amm-clearing-node", "pricing, allocation, trades;", "measurement fetch"],
        edge=ORANGE,
        fill=LIGHT_ORANGE,
    )
    d.box(
        0.75,
        0.14,
        0.24,
        0.30,
        "Off-chain storage",
        text["storage"],
        edge=ORANGE,
        fill=LIGHT_ORANGE,
    )
    d.box(
        0.01,
        0.14,
        0.24,
        0.30,
        "Settlement engine",
        text["settlement"],
        edge=GREY,
        fill="white",
        dashed=True,
    )
    d.arrow((0.25, 0.78), (0.35, 0.78), label="runs", offset=(0, 8))
    d.arrow((0.42, 0.44), (0.42, 0.64), label="snapshot", offset=(-24, 0))
    d.arrow((0.53, 0.64), (0.53, 0.44), label=r"$\Theta$, $B$", offset=(14, 0))
    d.arrow((0.75, 0.36), (0.63, 0.36), label="orders,", offset=(0, 16))
    d.note((0.69, 0.36), "measurements", offset=(0, 8), fs=6.8, background=True)
    d.arrow((0.63, 0.22), (0.75, 0.22), label="trades, results", offset=(0, -8))
    d.arrow((0.60, 0.44), (0.80, 0.66), dashed=True, color=BLUE)
    d.arrow((0.35, 0.29), (0.25, 0.29), dashed=True, color="#9A9A9A", label=text["matches"])
    core, optional, later = text["legend"]
    legend(d.ax, [(core, ORANGE), (optional, BLUE), (later, "#AAAAAA")])
    d.save(path)


# ── Evaluation results (Saber et al., 2026, Table 3) ─────────────────────
SCENARIOS = ("Low", "Medium", "High")
MECHANISMS = (("AMMBA", ORANGE), ("UPA", BLUE), ("DA", TEAL))
KPIS = {  # per scenario: AMMBA, UPA, DA (%)
    "CSC": ((90.9, 75.6, 76.1), (67.2, 54.7, 55.0), (54.6, 44.2, 44.3)),
    "VTI": ((67.0, 50.1, 50.6), (55.7, 38.2, 38.5), (45.7, 28.0, 28.3)),
    "EI": ((39.4, 33.4, 36.7), (47.8, 47.9, 44.1), (54.7, 56.4, 49.8)),
    "PWI": ((100.0, 97.6, 89.4), (100.0, 96.5, 96.5), (100.0, 100.0, 100.0)),
}


def fig_kpis(path):
    fig, axes = plt.subplots(1, 4, figsize=(6.8, 2.35), sharey=True)
    x = np.arange(len(SCENARIOS))
    width = 0.26
    for ax, (kpi, values) in zip(axes, KPIS.items(), strict=True):
        for k, (name, colour) in enumerate(MECHANISMS):
            ax.bar(x + (k - 1) * width, [v[k] for v in values], width, color=colour, label=name)
        ax.set_title(f"{kpi} (%)")
        ax.set_xticks(x, SCENARIOS)
        ax.set_ylim(0, 105)
        ax.grid(axis="y", alpha=0.25, lw=0.5)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("index value (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.07)
    )
    fig.tight_layout(w_pad=1.0)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.06, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    out = Path(__file__).parent
    fig_architecture(out / "architecture.png")
    fig_pricing(out / "pricing.png")
    fig_pool(out / "pool.png")
    fig_governance(out / "governance.png")
    fig_components(out / "components.png")
    fig_kpis(out / "kpis.png")
    print(f"figures written to {out}")
