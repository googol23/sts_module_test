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
