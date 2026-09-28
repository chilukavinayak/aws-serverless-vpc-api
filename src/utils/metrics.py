"""CloudWatch EMF helper. Off unless CUSTOM_METRICS_ENABLED=true (custom metrics bill)."""

from __future__ import annotations

import json
import os
import sys
import time
from types import TracebackType
from typing import Any


class Metrics:
    def __init__(self, operation: str, namespace: str | None = None) -> None:
        self._metrics: list[dict[str, str]] = []
        self._values: dict[str, float | int] = {}
        self._dimensions: dict[str, str] = {"Operation": operation}
        self._properties: dict[str, Any] = {}
        self._enabled = os.environ["CUSTOM_METRICS_ENABLED"].lower() == "true"
        self._namespace = namespace or (
            os.environ["POWERTOOLS_METRICS_NAMESPACE"] if self._enabled else ""
        )

    def count(self, name: str, value: int = 1) -> None:
        self._add(name, value, "Count")

    def duration_ms(self, name: str, value: float) -> None:
        self._add(name, value, "Milliseconds")

    def dimension(self, key: str, value: str) -> None:
        self._dimensions[key] = value

    def prop(self, key: str, value: Any) -> None:
        self._properties[key] = value

    def _add(self, name: str, value: float | int, unit: str) -> None:
        self._metrics.append({"Name": name, "Unit": unit})
        self._values[name] = value

    def _flush(self) -> None:
        if not self._enabled or not self._metrics:
            return
        payload: dict[str, Any] = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": self._namespace,
                        "Dimensions": [list(self._dimensions.keys())],
                        "Metrics": self._metrics,
                    }
                ],
            },
            **self._dimensions,
            **self._values,
            **self._properties,
        }
        sys.stdout.write(json.dumps(payload, default=str) + "\n")
        sys.stdout.flush()

    def __enter__(self) -> Metrics:
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        elapsed = (time.perf_counter() - self._start) * 1000
        self.duration_ms("HandlerDurationMs", elapsed)
        if exc_type is not None:
            self.count("HandlerErrors", 1)
        self._flush()
