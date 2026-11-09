from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


def test_run_p_scan_is_valid_python():
    source = (REPOSITORY / "run_p_scan.py").read_text(encoding="utf-8")
    compile(source, "run_p_scan.py", "exec")


def test_pscan_plotting_uses_package_relative_import():
    source = (REPOSITORY / "pscan" / "plotting.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert any(
        isinstance(node, ast.ImportFrom)
        and node.level == 1
        and node.module == "fit_err_fnc"
        for node in ast.walk(tree)
    )


def test_module_test_consumers_use_shared_sts_utils():
    for relative_path in (
        "module_test/collect_results.py",
        "module_test/index_builder.py",
    ):
        source = (REPOSITORY / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.append(node.module)

        assert any(name == "sts_utils" or name.startswith("sts_utils.") for name in imports)
        assert not any(name == "utils" or name.startswith("utils.") for name in imports)
