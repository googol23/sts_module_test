"""Discrete broken-channel reporting, independent of parameter generation."""
from __future__ import annotations

import csv
import hashlib
import logging
import re
from pathlib import Path

import numpy as np

from .module_test import ModuleTestResult
from . import plot_style as style
from .sensor_area import CHANNELS_PER_ASIC, nominal_sensor_length_mm, strip_area_mm2

logger = logging.getLogger(__name__)
CHANNELS = 1024
SIDES = ("P", "N")
DESCRIPTIONS = {
    "NAR": "No analog response",
    "ASIC": "Broken bond between ASIC and microcable",
    "SENS": "Sensor strip is not connected",
    "UNKNOWN": "Missing classification",
}


class BrokenChannelReport:
    """One module per address; first result wins on duplicate addresses."""

    def __init__(self):
        self.modules: dict[int, str] = {}
        self.sensor_lengths_mm: dict[int, float] = {}
        self._geometry_unavailable = False
        self.channels: set[tuple[int, str, int, str]] = set()

    def add_result(self, address: int, result: ModuleTestResult) -> None:
        if address in self.modules:
            logger.warning("Duplicate module address %s; ignoring later report result", address)
            return
        self.modules[address] = result.module_id
        if not self._geometry_unavailable and getattr(result, "sensor_size", None) is not None:
            try:
                self.sensor_lengths_mm[address] = nominal_sensor_length_mm(result.sensor_size)
            except ImportError:
                logger.warning("Area plots require sts-geo-layout; install the optional area dependency")
                self._geometry_unavailable = True
            except (ValueError, TypeError, AttributeError) as exc:
                logger.warning("%s: invalid sensor size; excluded from area report: %s",
                               result.module_id, exc)
        for side in SIDES:
            entries = getattr(result, f"broken_channels_{side.lower()}_side")
            declared = getattr(result, f"no_broken_channels_{side.lower()}_side")
            if declared != len({entry.channel for entry in entries}):
                logger.warning("%s %s: declared %s broken channels differs from parsed unique count",
                               result.module_id, side, declared)
            for entry in entries:
                if not 0 <= entry.channel < CHANNELS:
                    logger.warning("%s %s: channel %s outside report range; excluded",
                                   result.module_id, side, entry.channel)
                    continue
                self.channels.add((address, side, entry.channel, entry.reason or "UNKNOWN"))

    @property
    def reasons(self) -> list[str]:
        return sorted(set(DESCRIPTIONS) | {row[3] for row in self.channels})

    def _selected(self, side, reason):
        if side not in SIDES:
            raise ValueError(f"Invalid side: {side}")
        return {(address, channel) for address, s, channel, r in self.channels
                if s == side and (reason is None or reason == r)}

    def get_channel_distribution(self, side: str, reason: str | None = None) -> np.ndarray:
        """Return 1024 bins, each counting distinct affected modules."""
        return np.bincount([c for _, c in self._selected(side, reason)], minlength=CHANNELS)

    def get_module_distribution(self, side: str, reason: str | None = None) -> np.ndarray:
        """Return one broken-channel count per module, including zeros."""
        counts = dict.fromkeys(sorted(self.modules), 0)
        for address, _ in self._selected(side, reason):
            counts[address] += 1
        return np.array(list(counts.values()), dtype=int)

    def _groups(self):
        for side in SIDES:
            for reason in [None, *self.reasons]:
                yield side, reason

    @staticmethod
    def _filename(reason):
        if reason is None:
            return "all_reasons"
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", reason).strip("_").lower() or "reason"
        # Stable collision-resistant names for arbitrary source labels.
        if reason in DESCRIPTIONS:
            return slug
        return slug[:60] + "_" + hashlib.sha256(reason.encode()).hexdigest()[:12]

    @style.styled
    def generate_histograms(self, output_dir: Path, histogram_type="both", image_format="png"):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        for side, reason in self._groups():
            label = "All reasons" if reason is None else (
                f"{reason}: {DESCRIPTIONS[reason]}" if reason in DESCRIPTIONS else reason)
            for kind in ("channel", "module"):
                if histogram_type not in ("both", kind):
                    continue
                folder = Path(output_dir) / f"{kind}_distribution" / f"{side.lower()}_side"
                folder.mkdir(parents=True, exist_ok=True)
                fig = Figure(constrained_layout=True)
                FigureCanvasAgg(fig)
                ax = fig.subplots()
                if kind == "channel":
                    counts = self.get_channel_distribution(side, reason)
                    ax.stairs(counts, np.arange(CHANNELS + 1) - .5, color=style.SIDE_COLORS[side], **style.HISTOGRAM_STYLE)
                    for boundary in range(128, CHANNELS, 128):
                        ax.axvline(boundary - .5, **style.ASIC_BOUNDARY)
                    ax.set_xlim(-.5, CHANNELS - .5)
                    ax.set_xlabel("Source channel ID")
                else:
                    values = self.get_module_distribution(side, reason)
                    counts = np.bincount(values, minlength=1)
                    ax.stairs(counts, np.arange(len(counts) + 1) - .5, color=style.SIDE_COLORS[side], **style.HISTOGRAM_STYLE)
                    ax.set_xlim(-.5, len(counts) - .5)
                    ax.set_xlabel("Broken channels per module")
                ax.set_ylabel("Number of modules")
                ax.set_ylim(bottom=0)
                ax.set_title(f"{side}-side | {label} | Modules: {len(self.modules)}")
                fig.savefig(folder / f"{self._filename(reason)}.{image_format}", dpi=None)
                fig.clear()

        if histogram_type in ("both", "module"):
            for reason in [None, *self.reasons]:
                self.plot_combined_module_distribution(output_dir, reason, image_format)
            if self.sensor_lengths_mm:
                self.generate_area_histograms(output_dir, image_format)

    def threshold_statistics(self, reason: str | None = None):
        """Paired module counts; strict average-side thresholds."""
        total = self.get_module_distribution("N", reason) + self.get_module_distribution("P", reason)
        return {limit: (int(np.count_nonzero(total < 2 * limit)), len(total))
                for limit in style.THRESHOLD_STYLES}

    @style.styled
    def plot_combined_module_distribution(self, output_dir: Path,
                                          reason: str | None = None,
                                          image_format: str = "png"):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.ticker import MaxNLocator

        values = {side: self.get_module_distribution(side, reason) for side in SIDES}
        maximum = max([style.PRODUCTION_TARGET, *style.THRESHOLD_STYLES,
                       *(int(v.max()) for v in values.values() if v.size)])
        edges = np.arange(maximum + 2) - .5
        fig = Figure(constrained_layout=True)
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        for side in ("N", "P"):
            counts = np.histogram(values[side], bins=edges)[0]
            ax.stairs(counts, edges, color=style.SIDE_COLORS[side],
                      label=f"{side.lower()}-side", **style.HISTOGRAM_STYLE)
        for limit, (passed, n) in self.threshold_statistics(reason).items():
            fraction = f"{100 * passed / n:.1f}%" if n else "n/a"
            ax.axvline(limit, label=f"Total broken / 2 < {limit}: {fraction} ({passed}/{n} modules)",
                       **style.THRESHOLD_STYLES[limit])
        if reason is None:
            ax.text(style.PRODUCTION_TARGET + 0.5, .90,
                    f"Production target ({style.PRODUCTION_TARGET} channels, ~{100 * style.PRODUCTION_TARGET / CHANNELS:.1f}%)",
                    transform=ax.get_xaxis_transform(), rotation=90, va="top")
        title = "Distribution of broken channels per module side"
        if reason is not None:
            title += f" — {reason}"
        ax.set_title(title)
        ax.set_xlabel("Number of broken channels per module side")
        ax.set_ylabel("Number of modules")
        ax.set_xlim(-.5, maximum + .5)
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.legend(loc="upper right")
        folder = Path(output_dir) / "module_distribution" / "combined"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self._filename(reason)}.{image_format}"
        fig.savefig(path)
        fig.clear()
        return path

    def get_module_area_distribution(self, side: str, reason: str | None = None) -> np.ndarray:
        """Area in mm² for each module with resolved geometry, sorted by address."""
        counts = self.get_module_distribution(side, reason)
        return np.array([count * strip_area_mm2(self.sensor_lengths_mm[address], side)
                         for address, count in zip(sorted(self.modules), counts)
                         if address in self.sensor_lengths_mm], dtype=float)

    def full_asic_area_values(self, side: str) -> list[tuple[float, float]]:
        """Nominal area of 128 inactive strips for each represented sensor length."""
        return [(length, CHANNELS_PER_ASIC * strip_area_mm2(length, side))
                for length in sorted(set(self.sensor_lengths_mm.values()))]

    @style.styled
    def generate_area_histograms(self, output_dir: Path, image_format="png"):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        for reason in [None, *self.reasons]:
            values = {side: self.get_module_area_distribution(side, reason) for side in SIDES}
            width = style.AREA_BIN_WIDTH_MM2
            references = {side: self.full_asic_area_values(side) for side in SIDES}
            maximum = max([0.0, *(float(v.max()) for v in values.values() if v.size),
                           *(area for refs in references.values() for _, area in refs)])
            # Shared range across P, N and combined; include the full final bin.
            bins = np.arange(max(2, int(np.ceil(maximum / width)) + 2)) * width - width / 2
            for group, sides in (("n_side", ("N",)), ("p_side", ("P",)),
                                 ("combined", ("N", "P"))):
                fig = Figure(constrained_layout=True)
                FigureCanvasAgg(fig)
                ax = fig.subplots()
                peak = 1
                ax.set_yscale("log")
                for side in sides:
                    counts = np.histogram(values[side], bins=bins)[0]
                    peak = max(peak, int(counts.max()))
                    # NaN gaps suppress empty bins without inventing positive counts.
                    visible = np.where(counts > 0, counts.astype(float), np.nan)
                    ax.stairs(visible, bins, baseline=None, color=style.SIDE_COLORS[side],
                              label=f"{side.lower()}-side", **style.HISTOGRAM_STYLE)
                    for length, area in references[side]:
                        ax.axvline(area, color=style.SIDE_COLORS[side],
                                   **style.AREA_ASIC_LINE_STYLE)
                        ax.text(area, .97 if side == "N" else .77,
                                f"{length:g} mm ({side})",
                                transform=ax.get_xaxis_transform(), rotation=90,
                                va="top", ha="right", color=style.SIDE_COLORS[side],
                                fontsize=style.AREA_ASIC_LABEL_SIZE)
                label = "All reasons" if reason is None else reason
                ax.set_title(f"Estimated inactive strip area | {label}")
                ax.set_xlabel("Inactive strip area per module side [mm²]")
                ax.set_ylabel("Number of modules")
                ax.set_xlim(bins[0], bins[-1])
                ax.set_ylim(style.AREA_LOG_YMIN, max(2, peak * 1.5))
                ax.legend(title=f"Geometry available: {len(self.sensor_lengths_mm)}/{len(self.modules)}\n"
                                "Dotted: full ASIC (128 strips)")
                folder = Path(output_dir) / "area_distribution" / group
                folder.mkdir(parents=True, exist_ok=True)
                fig.savefig(folder / f"{self._filename(reason)}.{image_format}")
                fig.clear()

    def export_summary(self, output_dir: Path):
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)

        def write(name, header, rows):
            with (folder / name).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(rows)

        write("modules.csv", ("address", "module_id"),
              sorted(self.modules.items()))
        write("broken_channels.csv", ("address", "module_id", "side", "channel", "reason"),
              ((a, self.modules[a], s, c, r) for a, s, c, r in sorted(self.channels)))
        counts, stats = [], []
        for side, reason in self._groups():
            values = self.get_module_distribution(side, reason)
            label = reason if reason is not None else ""
            counts.extend((a, self.modules[a], side, label, int(v))
                          for a, v in zip(sorted(self.modules), values))
            n = len(values)
            affected = int(np.count_nonzero(values))
            stats.append((side, label, n, affected, int(values.sum()),
                          float(values.mean()) if n else "",
                          float(values.std()) if n else "",
                          float(np.median(values)) if n else "",
                          int(values.max()) if n else "",
                          affected / n if n else "", 1 - affected / n if n else ""))
        write("module_counts.csv", ("address", "module_id", "side", "reason", "count"), counts)
        area_rows = []
        for side, reason in self._groups():
            values = self.get_module_distribution(side, reason)
            for address, count in zip(sorted(self.modules), values):
                length = self.sensor_lengths_mm.get(address)
                area_rows.append((address, self.modules[address], side, reason or "",
                                  int(count), length if length is not None else "",
                                  count * strip_area_mm2(length, side) if length is not None else ""))
        write("module_areas.csv", ("address", "module_id", "side", "reason", "count",
                                  "sensor_length_mm", "estimated_inactive_area_mm2"), area_rows)
        write("statistics.csv", ("side", "reason", "modules", "affected_modules", "broken_channels",
                                "mean", "std", "median", "max", "affected_fraction", "zero_fraction"), stats)
