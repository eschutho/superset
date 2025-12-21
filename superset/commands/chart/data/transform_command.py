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
"""Command for transforming cached raw chart data with new post-processing operations."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from flask_babel import gettext as _

from superset.commands.base import BaseCommand
from superset.commands.chart.exceptions import (
    ChartDataCacheLoadError,
    ChartDataQueryFailedError,
)
from superset.constants import CacheRegion
from superset.exceptions import InvalidPostProcessingError
from superset.extensions import cache_manager
from superset.utils import pandas_postprocessing
from superset.utils.core import GenericDataType

logger = logging.getLogger(__name__)


class ChartDataTransformCommand(BaseCommand):
    """
    Command to transform cached raw data with new post-processing operations.

    This enables instant chart type switching by reusing cached query results
    and applying different post-processing without re-querying the database.
    """

    def __init__(
        self,
        raw_cache_key: str,
        post_processing: list[dict[str, Any]],
        result_format: str = "json",
    ):
        self._raw_cache_key = raw_cache_key
        self._post_processing = post_processing or []
        self._result_format = result_format

    def run(self) -> dict[str, Any]:
        self.validate()
        return self._transform()

    def validate(self) -> None:
        """Validate that the post-processing operations exist."""
        for post_process in self._post_processing:
            operation = post_process.get("operation")
            if not operation:
                raise InvalidPostProcessingError(
                    _("`operation` property of post processing object undefined")
                )
            if not hasattr(pandas_postprocessing, operation):
                raise InvalidPostProcessingError(
                    _(
                        "Unsupported post processing operation: %(operation)s",
                        operation=operation,
                    )
                )

    def _transform(self) -> dict[str, Any]:
        """Retrieve cached raw data and apply new post-processing."""
        cache = cache_manager.data_cache
        cached = cache.get(self._raw_cache_key)

        if cached is None:
            raise ChartDataCacheLoadError(
                _("Cache key not found or expired: %(key)s", key=self._raw_cache_key)
            )

        df = cached.get("df")
        if df is None or not isinstance(df, pd.DataFrame):
            raise ChartDataCacheLoadError(_("Cached data is invalid or missing"))

        # Make a copy to avoid mutating cached data
        df = df.copy()

        # Apply new post-processing operations
        try:
            for post_process in self._post_processing:
                operation = post_process.get("operation")
                options = post_process.get("options", {})
                df = getattr(pandas_postprocessing, operation)(df, **options)
        except Exception as ex:
            logger.exception("Post-processing failed: %s", ex)
            raise ChartDataQueryFailedError(
                _("Post-processing failed: %(error)s", error=str(ex))
            ) from ex

        # Build response matching standard chart data format
        return {
            "queries": [
                {
                    "data": df.to_dict(orient="records"),
                    "colnames": list(df.columns),
                    "coltypes": [self._get_col_type(df[col]) for col in df.columns],
                    "rowcount": len(df),
                    "is_cached": True,
                    "cached_dttm": cached.get("dttm"),
                    "from_cache": True,
                    # Preserve original query metadata
                    "query": cached.get("query", ""),
                    "applied_template_filters": cached.get(
                        "applied_template_filters", []
                    ),
                    "applied_filter_columns": cached.get("applied_filter_columns", []),
                    "rejected_filter_columns": cached.get(
                        "rejected_filter_columns", []
                    ),
                }
            ],
        }

    @staticmethod
    def _get_col_type(series: pd.Series) -> int:
        """Map pandas dtype to Superset GenericDataType."""
        if series.dtype.kind in ("i", "u"):
            return GenericDataType.NUMERIC
        elif series.dtype.kind == "f":
            return GenericDataType.NUMERIC
        elif series.dtype.kind == "b":
            return GenericDataType.BOOLEAN
        elif series.dtype.kind in ("M", "m"):
            return GenericDataType.TEMPORAL
        return GenericDataType.STRING
