"""Dependency-free, low-cardinality operational metrics."""

from collections import Counter
from threading import Lock


class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: Counter[str] = Counter()
        self._latency_ms = 0.0

    def record_http(self, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._requests["total"] += 1
            self._requests[f"status_{status_code // 100}xx"] += 1
            self._latency_ms += duration_ms

    def render(self) -> str:
        with self._lock:
            return "\n".join(
                [
                    "# TYPE enterprise_http_requests_total counter",
                    f"enterprise_http_requests_total {self._requests['total']}",
                    "# TYPE enterprise_http_request_latency_ms_total counter",
                    f"enterprise_http_request_latency_ms_total {self._latency_ms:.3f}",
                    *(
                        f"enterprise_http_requests_{key}_total {value}"
                        for key, value in sorted(self._requests.items())
                        if key != "total"
                    ),
                    "",
                ]
            )


metrics = Metrics()
