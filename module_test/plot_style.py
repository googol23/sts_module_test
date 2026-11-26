"""Central cosmetic settings for all STS module-test and pulse-scan plots."""
from matplotlib import rcParams, rc_context
from matplotlib import style as mpl_style
from functools import wraps

RC = {
    "font.size": 14,
    "axes.titlesize": 18,
    "axes.labelsize": 16,
    "legend.fontsize": 13,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "figure.figsize": (12, 7),
    "figure.dpi": 100,
    "savefig.dpi": 200,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.30,
    "axes.axisbelow": True,
    "lines.linewidth": 2.0,
    "legend.frameon": True,
    "legend.loc": "best",
}
SIDE_COLORS = {"N": "red", "P": "blue"}
THRESHOLD_STYLES = {
    8: {"color": "darkgreen", "linestyle": "-."},
    16: {"color": "purple", "linestyle": ":"},
}
ASIC_BOUNDARY = {"color": "gray", "linestyle": "--", "alpha": 0.5}
FIT_COLOR = "tab:red"
DATA_COLOR = "tab:blue"
ANNOTATION_COLOR = "gray"
ANNOTATION_SIZE = 8
ANNOTATION_ALPHA = 0.7
HISTOGRAM_STYLE = {"fill": False, "linewidth": 2.0}
PRODUCTION_TARGET = 16
AREA_BIN_WIDTH_MM2 = 1.0
AREA_PERCENT_BIN_WIDTH = 0.1
AREA_LOG_YMIN = 0.8
AREA_ASIC_LINE_STYLE = {"linestyle": ":", "linewidth": 1.5, "alpha": 0.8}
AREA_ASIC_LABEL_SIZE = 10


def apply_style():
    """Apply the common style to pyplot-based callers."""
    mpl_style.use("default")
    rcParams.update(RC)


def styled(func):
    """Apply cosmetics locally without leaking rcParams to callers."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with rc_context():
            apply_style()
            return func(*args, **kwargs)
    return wrapper
