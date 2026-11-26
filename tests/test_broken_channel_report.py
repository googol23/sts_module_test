from dataclasses import asdict
from types import SimpleNamespace

import numpy as np

from module_test.module_test import BrokenChannel, parse_broken_channels, parse_broken_channel_details
from module_test.broken_channel_report import BrokenChannelReport


def test_parser_preserves_legacy_ids():
    text = "257 (SENS), 897 (SENS), 994 (ASIC), 1022 (ASIC),"
    assert parse_broken_channels(text) == [257, 897, 994, 1022]
    assert parse_broken_channel_details(text) == [
        BrokenChannel(257, "SENS"), BrokenChannel(897, "SENS"),
        BrokenChannel(994, "ASIC"), BrokenChannel(1022, "ASIC")]
    assert parse_broken_channel_details("0, 1 (), 2 (NEW), ") == [
        BrokenChannel(0), BrokenChannel(1), BrokenChannel(2, "NEW")]
    assert parse_broken_channel_details("") == []


def test_distributions_and_exports(tmp_path):
    report = BrokenChannelReport()
    result = SimpleNamespace(
        module_id="example", no_broken_channels_n_side=4,
        no_broken_channels_p_side=1,
        broken_channels_n_side=parse_broken_channel_details(
            "257 (SENS), 897 (SENS), 994 (ASIC), 1022 (ASIC),"),
        broken_channels_p_side=[BrokenChannel(374, "NAR")])
    report.add_result(1, result)
    report.add_result(1, result)
    report.add_result(2, SimpleNamespace(module_id="clean",
        no_broken_channels_n_side=0, no_broken_channels_p_side=0,
        broken_channels_n_side=[], broken_channels_p_side=[]))
    assert report.get_channel_distribution("N").sum() == 4
    assert report.get_channel_distribution("N", "SENS")[257] == 1
    assert report.get_channel_distribution("P", "NAR")[374] == 1
    np.testing.assert_array_equal(report.get_module_distribution("N"), [4, 0])
    np.testing.assert_array_equal(report.get_module_distribution("P", "ASIC"), [0, 0])
    report.export_summary(tmp_path)
    report.generate_histograms(tmp_path)
    assert (tmp_path / "statistics.csv").exists()
    assert len(list(tmp_path.rglob("*.png"))) == 25


def test_empty_report():
    report = BrokenChannelReport()
    assert report.get_channel_distribution("P").shape == (1024,)
    assert report.get_module_distribution("N").size == 0


def test_paired_thresholds():
    report = BrokenChannelReport()
    report.modules = {1: "a", 2: "b", 3: "c"}
    report.channels = {(1, "N", c, "NAR") for c in range(16)}
    report.channels.update((2, "P", c, "NAR") for c in range(32))
    assert report.threshold_statistics() == {8: (1, 3), 16: (2, 3)}
    assert report.threshold_statistics("SENS") == {8: (3, 3), 16: (3, 3)}


def test_area_distributions(tmp_path):
    from module_test.sensor_area import strip_area_mm2
    report = BrokenChannelReport()
    report.modules = {1: "short", 2: "long", 3: "unknown", 4: "clean"}
    report.sensor_lengths_mm = {1: 22., 2: 124., 4: 42.}
    report.channels = {(1, "N", 2, "SENS"), (2, "N", 2, "SENS"), (2, "P", 3, "NAR")}
    np.testing.assert_allclose(report.get_module_area_distribution("N"), [1.276, 7.192, 0])
    np.testing.assert_allclose(report.get_module_area_distribution("P", "NAR"), [0, strip_area_mm2(124, "P"), 0])
    report.export_summary(tmp_path)
    report.generate_area_histograms(tmp_path)
    assert len(list((tmp_path / "area_distribution").rglob("*.png"))) == 15
    assert (tmp_path / "module_areas.csv").exists()


def test_nominal_geometry():
    import pytest
    pytest.importorskip("sts_geo_layout")
    from module_test.sensor_area import nominal_sensor_length_mm
    for cm in (2.2, 4.2, 6.2, 12.4):
        assert nominal_sensor_length_mm(SimpleNamespace(value=cm, unit="cm")) == pytest.approx(cm * 10)
    with pytest.raises(ValueError):
        nominal_sensor_length_mm(SimpleNamespace(value=3.0, unit="cm"))


def test_full_asic_area_values():
    from module_test.sensor_area import strip_area_mm2
    report = BrokenChannelReport()
    report.sensor_lengths_mm = {1: 22., 2: 124., 3: 22.}
    assert dict(report.full_asic_area_values("N")) == {
        22.: 128 * strip_area_mm2(22., "N"),
        124.: 128 * strip_area_mm2(124., "N")}
    assert dict(report.full_asic_area_values("P"))[124.] > 128 * strip_area_mm2(124., "N")


def test_area_plot_axes_and_markers(tmp_path, monkeypatch):
    from matplotlib.figure import Figure
    report = BrokenChannelReport()
    report.modules = {1: "long", 2: "short"}
    report.sensor_lengths_mm = {1: 124., 2: 22.}
    report.channels = {(1, "N", c, "ASIC") for c in range(256)}
    captured = []
    def inspect(fig, path, **kwargs):
        ax = fig.axes[0]
        captured.append((path, ax.get_yscale(), ax.get_xlim(),
                         [float(line.get_xdata()[0]) for line in ax.lines]))
    monkeypatch.setattr(Figure, "savefig", inspect)
    report.generate_area_histograms(tmp_path)
    assert len(captured) == 15
    for path, scale, limits, markers in captured:
        assert scale == "log"
        assert limits[1] >= max(markers)
        if path.name == "all_reasons.png":
            assert limits[1] >= report.get_module_area_distribution("N").max()
        assert len(markers) == (4 if path.parent.name == "combined" else 2)


def test_area_percent_distribution(tmp_path, monkeypatch):
    from matplotlib.figure import Figure
    from module_test.sensor_area import inactive_area_percent
    report = BrokenChannelReport()
    report.modules = {1: "short", 2: "long", 3: "clean", 4: "unknown"}
    report.sensor_lengths_mm = {1: 22., 2: 124., 3: 42.}
    report.channels = {(a, s, c, "ASIC") for a in (1, 2) for s in ("N", "P")
                       for c in range(256)}
    for side in ("N", "P"):
        expected = inactive_area_percent(256, 22., side)
        np.testing.assert_allclose(report.get_module_area_percent_distribution(side),
                                   [expected, expected, 0.])
        np.testing.assert_allclose(report.full_asic_area_percent(side), expected / 2)
    assert report.full_asic_area_percent("P") > report.full_asic_area_percent("N")
    captured = []
    def inspect(fig, path, **kwargs):
        ax = fig.axes[0]
        captured.append((path, ax.get_yscale(), ax.get_xlim(), len(ax.lines)))
    monkeypatch.setattr(Figure, "savefig", inspect)
    report.generate_area_percent_histograms(tmp_path)
    assert len(captured) == 15
    for path, scale, limits, markers in captured:
        assert scale == "log"
        assert markers == (2 if path.parent.name == "combined" else 1)
        if path.name == "all_reasons.png":
            assert limits[1] >= report.get_module_area_percent_distribution("P").max()


def test_area_y_scale_configuration(tmp_path, monkeypatch):
    from matplotlib.figure import Figure
    from module_test import plot_style
    report = BrokenChannelReport()
    report.modules = {1: "module"}
    report.sensor_lengths_mm = {1: 22.}
    report.channels = {(1, "N", 0, "ASIC")}
    captured = []

    def inspect(fig, path, **kwargs):
        ax = fig.axes[0]
        captured.append((ax.get_yscale(), ax.get_ylim()[0],
                         ax.patches[0].get_data().values))

    monkeypatch.setattr(Figure, "savefig", inspect)
    for scale in ("linear", "log"):
        captured.clear()
        monkeypatch.setattr(plot_style, "AREA_Y_SCALE", scale)
        report.generate_area_histograms(tmp_path)
        report.generate_area_percent_histograms(tmp_path)
        assert len(captured) == 30
        for actual, ymin, values in captured:
            assert actual == scale
            if scale == "linear":
                assert ymin == 0
                assert np.all(np.isfinite(values))
                assert np.any(values == 0)
            else:
                assert ymin == plot_style.AREA_LOG_YMIN
                assert np.any(np.isnan(values))
