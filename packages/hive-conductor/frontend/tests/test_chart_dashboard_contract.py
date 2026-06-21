"""Regression tests for the Hive Conductor dashboard chart contract.

These tests intentionally inspect the TypeScript source instead of importing it so
we can validate the frontend contract from root pytest without requiring a browser
or npm install in CI shards that only run Python tests.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FRONTEND = ROOT / "packages" / "hive-conductor" / "frontend"
CHARTS = FRONTEND / "src" / "components" / "Charts.tsx"
DASHBOARD = FRONTEND / "src" / "pages" / "Dashboard.tsx"
PACKAGE_JSON = FRONTEND / "package.json"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_chartjs_runtime_dependencies_are_declared() -> None:
    """The dashboard charts must have both the Chart.js runtime and React bridge."""
    package = json.loads(read(PACKAGE_JSON))

    assert package["dependencies"]["chart.js"].startswith("^4.")
    assert package["dependencies"]["react-chartjs-2"].startswith("^5.")


def test_chart_components_register_chartjs_once_and_export_supported_views() -> None:
    """All supported dashboard chart views should be exported from one component module."""
    source = read(CHARTS)

    assert 'import { Chart, registerables } from "chart.js";' in source
    assert "Chart.register(...registerables);" in source

    exports = set(re.findall(r"export function (\w+)", source))
    assert {
        "DonutChart",
        "ColumnChart",
        "LineChart",
        "StackedBarChart",
        "FunnelChart",
    }.issubset(exports)


def test_each_chart_destroys_previous_chart_and_cleans_up_on_unmount() -> None:
    """Chart.js canvases leak if previous instances are not destroyed."""
    source = read(CHARTS)
    exported_functions = re.findall(r"export function \w+", source)

    # Each exported chart creates a Chart.js instance, destroys any previous one
    # before replacing it, and returns a React effect cleanup that destroys it on
    # unmount. This prevents duplicate canvas renderers during dashboard updates.
    assert source.count("chartRef.current = new Chart") == len(exported_functions)
    assert source.count("chartRef.current?.destroy();") >= len(exported_functions) * 2
    assert source.count("return () => { chartRef.current?.destroy(); };") == len(exported_functions)


def test_dashboard_imports_and_routes_display_modes_to_chart_components() -> None:
    """Dashboard display-mode strings are the public contract from saved widgets."""
    source = read(DASHBOARD)

    assert 'import { DonutChart, ColumnChart, LineChart, FunnelChart, StackedBarChart } from "../components/Charts";' in source

    expected_routes = {
        'cfg.display === "donut"': "<DonutChart",
        'cfg.display === "line"': "<LineChart",
        'cfg.display === "column"': "<ColumnChart",
        'cfg.display === "funnel"': "<FunnelChart",
    }
    for display_guard, component in expected_routes.items():
        assert display_guard in source
        assert component in source

    assert 'cfg.display === "stacked" || cfg.display === "proportional"' in source


def test_dashboard_builder_prompt_documents_available_chart_displays() -> None:
    """The LLM-facing builder prompt must not lag behind supported display modes."""
    source = read(DASHBOARD)

    for display in ("bar", "donut", "stacked", "progress", "ranked", "list", "table"):
        assert f'"{display}"' in source or f"- \"{display}\"" in source

    assert "CHART SELECTION GUIDE" in source
    assert "WORKFLOW:" in source
    assert "Do NOT create widgets without querying the data first." in source
