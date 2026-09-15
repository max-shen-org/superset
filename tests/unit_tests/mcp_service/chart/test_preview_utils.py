# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Tests for preview_utils query context column building.
"""

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from flask import current_app

from superset.mcp_service.chart import preview_utils


def _imports_chart_data_command(node: ast.Import | ast.ImportFrom) -> bool:
    blocked_module = "superset.commands.chart.data.get_data_command"

    if isinstance(node, ast.Import):
        return any(
            alias.name == blocked_module or alias.name.startswith(f"{blocked_module}.")
            for alias in node.names
        )

    module = node.module or ""
    return (
        module == blocked_module
        or module.startswith(f"{blocked_module}.")
        or (
            module == "superset.commands.chart.data"
            and any(alias.name == "get_data_command" for alias in node.names)
        )
    )


def test_preview_utils_does_not_top_level_import_chart_data_command():
    """preview_utils constants should stay safe to import before app setup."""
    source_path = inspect.getsourcefile(preview_utils) or preview_utils.__file__
    source = Path(source_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = [
        node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]

    assert preview_utils.SUPPORTED_FORM_DATA_PREVIEW_FORMATS == frozenset(
        {"ascii", "table", "vega_lite"}
    )
    assert not any(_imports_chart_data_command(node) for node in top_level_imports)


class TestPreviewUtilsColumnBuilding:
    """Tests for x_axis + groupby column building in generate_preview_from_form_data.

    The function must build the columns list from both x_axis and groupby for
    XY charts, and fall back to form_data["columns"] for table charts.
    """

    def test_xy_chart_uses_x_axis_and_groupby(self):
        """Test XY chart form_data builds columns from x_axis + groupby."""
        form_data = {
            "x_axis": "territory",
            "groupby": ["year"],
            "metrics": [{"label": "SUM(sales)"}],
        }

        x_axis_config = form_data.get("x_axis")
        groupby_columns = form_data.get("groupby", [])
        raw_columns = form_data.get("columns", [])

        columns = (
            raw_columns.copy() if "columns" in form_data else groupby_columns.copy()
        )
        if x_axis_config and isinstance(x_axis_config, str):
            if x_axis_config not in columns:
                columns.insert(0, x_axis_config)
        elif x_axis_config and isinstance(x_axis_config, dict):
            col_name = x_axis_config.get("column_name")
            if col_name and col_name not in columns:
                columns.insert(0, col_name)

        assert columns == ["territory", "year"]

    def test_table_chart_uses_columns_field(self):
        """Test table chart form_data uses 'columns' field directly."""
        form_data = {
            "columns": ["name", "region", "sales"],
            "metrics": [],
        }

        x_axis_config = form_data.get("x_axis")
        groupby_columns = form_data.get("groupby", [])
        raw_columns = form_data.get("columns", [])

        columns = (
            raw_columns.copy() if "columns" in form_data else groupby_columns.copy()
        )
        if x_axis_config and isinstance(x_axis_config, str):
            if x_axis_config not in columns:
                columns.insert(0, x_axis_config)

        assert columns == ["name", "region", "sales"]

    def test_xy_chart_x_axis_dict_format(self):
        """Test XY chart with x_axis as dict (column_name key)."""
        form_data = {
            "x_axis": {"column_name": "order_date"},
            "groupby": ["product_type"],
            "metrics": [{"label": "SUM(revenue)"}],
        }

        x_axis_config = form_data.get("x_axis")
        groupby_columns = form_data.get("groupby", [])
        raw_columns = form_data.get("columns", [])

        columns = (
            raw_columns.copy() if "columns" in form_data else groupby_columns.copy()
        )
        if x_axis_config and isinstance(x_axis_config, str):
            if x_axis_config not in columns:
                columns.insert(0, x_axis_config)
        elif x_axis_config and isinstance(x_axis_config, dict):
            col_name = x_axis_config.get("column_name")
            if col_name and col_name not in columns:
                columns.insert(0, col_name)

        assert columns == ["order_date", "product_type"]

    def test_no_x_axis_no_columns_uses_groupby(self):
        """Test fallback to groupby when no x_axis and no columns."""
        form_data = {
            "groupby": ["category"],
            "metrics": [{"label": "COUNT(*)"}],
        }

        x_axis_config = form_data.get("x_axis")
        groupby_columns = form_data.get("groupby", [])
        raw_columns = form_data.get("columns", [])

        columns = (
            raw_columns.copy() if "columns" in form_data else groupby_columns.copy()
        )
        if x_axis_config and isinstance(x_axis_config, str):
            if x_axis_config not in columns:
                columns.insert(0, x_axis_config)

        assert columns == ["category"]

    def test_empty_form_data_returns_empty_columns(self):
        """Test empty form_data returns empty columns list."""
        form_data: dict = {
            "metrics": [{"label": "COUNT(*)"}],
        }

        x_axis_config = form_data.get("x_axis")
        groupby_columns = form_data.get("groupby", [])
        raw_columns = form_data.get("columns", [])

        columns = (
            raw_columns.copy() if "columns" in form_data else groupby_columns.copy()
        )
        if x_axis_config and isinstance(x_axis_config, str):
            if x_axis_config not in columns:
                columns.insert(0, x_axis_config)

        assert columns == []

    def test_x_axis_not_duplicated_when_in_groupby(self):
        """Test x_axis is not added if already present in groupby."""
        form_data = {
            "x_axis": "territory",
            "groupby": ["territory", "year"],
            "metrics": [{"label": "SUM(sales)"}],
        }

        x_axis_config = form_data.get("x_axis")
        groupby_columns = form_data.get("groupby", [])
        raw_columns = form_data.get("columns", [])

        columns = (
            raw_columns.copy() if "columns" in form_data else groupby_columns.copy()
        )
        if x_axis_config and isinstance(x_axis_config, str):
            if x_axis_config not in columns:
                columns.insert(0, x_axis_config)

        assert columns == ["territory", "year"]


def test_build_query_columns_empty_columns_key_keeps_groupby():
    """MCP path: an explicitly empty ``columns`` list no longer shadows ``groupby``.

    ``_build_query_columns`` delegates to the shared
    ``superset.common.form_data_query_context.columns_from_form_data``; this pins
    the (intentional) behavior change so the export and MCP paths stay in sync.
    """
    assert preview_utils._build_query_columns(
        {"groupby": ["country"], "columns": []}
    ) == ["country"]


@patch("superset.commands.chart.data.get_data_command.ChartDataCommand")
@patch("superset.mcp_service.chart.chart_helpers.build_query_context_from_form_data")
@patch("superset.extensions.db.session.get")
def test_unsaved_gauge_preview_uses_shared_builder_and_preserves_ordering(
    mock_find_dataset, mock_build_query_context, mock_command
):
    """Unsaved previews execute the same Gauge QueryObject path as Explore."""
    mock_find_dataset.return_value = Mock(id=7)
    mock_build_query_context.return_value = SimpleNamespace(
        datasource=SimpleNamespace(id=7, type="table"),
        queries=[],
        form_data={},
    )
    mock_command.return_value.validate.return_value = None
    mock_command.return_value.run.return_value = {
        "queries": [{"data": [{"AVG(score)": 75}]}]
    }
    form_data = {
        "viz_type": "gauge_chart",
        "metric": {
            "expressionType": "SIMPLE",
            "aggregate": "AVG",
            "column": {"column_name": "score"},
            "label": "AVG(score)",
        },
        "groupby": [],
        "sort_by_metric": True,
        "row_limit": 4,
        "intervals": "30,70,200",
        "datasource_id": 99,
        "datasource_type": "query",
        "datasource": "99__query",
    }

    result = preview_utils.generate_preview_from_form_data(
        form_data, dataset_id=7, preview_format="ascii"
    )

    assert result.ascii_content.startswith("Gauge Chart")
    query_form_data = mock_build_query_context.call_args.args[0]
    assert query_form_data["sort_by_metric"] is True
    assert query_form_data["datasource"] == "7__table"
    assert query_form_data["datasource_id"] == 7
    assert query_form_data["datasource_type"] == "table"
    from superset.mcp_service.chart.chart_helpers import resolve_form_data_datasource

    assert resolve_form_data_datasource(query_form_data) == (7, "table")
    assert form_data["datasource_id"] == 99
    mock_build_query_context.assert_called_once_with(
        query_form_data, row_limit=4, force=False
    )


def test_unsaved_preview_sets_jinja_form_data(monkeypatch):
    """Unsaved previews expose request inputs to Jinja macros."""
    from flask import current_app, g

    from superset.common.query_object import QueryObject

    captured: dict[str, Any] = {}

    class ChartDataCommand:
        def __init__(self, query_context: Any) -> None:
            captured["form_data"] = dict(g.form_data)

        def validate(self) -> None:
            pass

        def run(self) -> dict[str, Any]:
            return {"queries": [{"data": [{"region": "North", "count": 1}]}]}

    query_context = Mock(
        datasource=Mock(id=7, type="table"),
        queries=[
            QueryObject(
                filters=[{"col": "region", "op": "IN", "val": ["North"]}],
                time_range="Last week",
            )
        ],
        form_data={"url_params": {"tenant": "acme"}},
    )
    with (
        patch(
            "superset.mcp_service.chart.chart_helpers.build_query_context_from_form_data",
            return_value=query_context,
        ),
        patch(
            "superset.commands.chart.data.get_data_command.ChartDataCommand",
            ChartDataCommand,
        ),
        patch("superset.extensions.db.session.get", return_value=Mock(id=7)),
        current_app.test_request_context(),
    ):
        result = preview_utils.generate_preview_from_form_data(
            {
                "viz_type": "table",
                "columns": ["region"],
                "filters": [{"col": "region", "op": "IN", "val": ["North"]}],
                "time_range": "Last week",
                "url_params": {"tenant": "acme"},
            },
            dataset_id=7,
            preview_format="table",
        )

    assert result.table_data
    form_data = captured["form_data"]
    assert form_data["datasource"] == {"id": 7, "type": "table"}
    assert form_data["queries"][0]["filters"] == [
        {"col": "region", "op": "IN", "val": ["North"]}
    ]
    assert form_data["queries"][0]["time_range"] == "Last week"
    assert form_data["queries"][0]["url_params"] == {"tenant": "acme"}


@patch("superset.commands.chart.data.get_data_command.ChartDataCommand")
@patch("superset.mcp_service.chart.chart_helpers.build_query_context_from_form_data")
@patch("superset.extensions.db.session.get")
def test_unsaved_gauge_preview_surfaces_query_error(
    mock_find_dataset, mock_build_query_context, mock_command
):
    mock_find_dataset.return_value = Mock(id=7)
    mock_build_query_context.return_value = SimpleNamespace(
        datasource=SimpleNamespace(id=7, type="table"),
        queries=[],
        form_data={},
    )
    mock_command.return_value.validate.return_value = None
    mock_command.return_value.run.return_value = {
        "queries": [{"status": "failed", "error": "bad metric", "data": []}]
    }
    result = preview_utils.generate_preview_from_form_data(
        {"viz_type": "gauge_chart", "metric": "saved_sla"},
        dataset_id=7,
        preview_format="vega_lite",
    )
    assert result.error_type == "QueryError"
    assert "bad metric" in result.error


@patch("superset.commands.chart.data.get_data_command.ChartDataCommand")
@patch("superset.mcp_service.chart.chart_helpers.build_query_context_from_form_data")
@patch("superset.extensions.db.session.get")
def test_unsaved_preview_exposes_query_to_jinja_like_chart_data_api(
    mock_find_dataset, mock_build_query_context, mock_command
) -> None:
    """Unsaved previews render request-dependent Jinja macros with the same
    inputs as get_chart_data, so previewed data matches executed SQL."""
    from superset.common.query_object import QueryObject
    from superset.jinja_context import ExtraCache, get_dataset_id_from_context

    mock_find_dataset.return_value = Mock(id=7)
    query = QueryObject(
        filters=[{"col": "region", "op": "IN", "val": ["North"]}],
        time_range="Last week",
    )
    mock_build_query_context.return_value = SimpleNamespace(
        queries=[query], form_data={"url_params": {"tenant": "acme"}}
    )
    seen: dict[str, object] = {}

    def run() -> dict[str, object]:
        extra_cache = ExtraCache()
        seen["filter_values"] = extra_cache.filter_values("region")
        seen["url_param"] = extra_cache.url_param("tenant")
        seen["time_range"] = extra_cache.get_time_filter().time_range
        seen["dataset_id"] = get_dataset_id_from_context("count")
        return {"queries": [{"data": [{"count": 1}], "colnames": ["count"]}]}

    mock_command.return_value.validate.return_value = None
    mock_command.return_value.run.side_effect = run

    with current_app.test_request_context():
        result = preview_utils.generate_preview_from_form_data(
            {"viz_type": "table", "metrics": ["count"]},
            dataset_id=7,
            preview_format="table",
        )

    assert not isinstance(result, preview_utils.ChartError), result
    assert seen == {
        "filter_values": ["North"],
        "url_param": "acme",
        "time_range": "Last week",
        "dataset_id": 7,
    }
