"""
Non-invasive LLM call metrics for one investigation's 4B window.

Discovery.AI's llm_client.py logs fallback/failure events via raw print()
(backend/questions/llm_client.py:230), not the logging module -- there's no
programmatic hook to attach to without editing its source, which Rules.md
reserves for relation_types.py only. Instead this tees stdout during the 4B
call window: still prints live (nothing about the console output changes),
but also counts the two message patterns Discovery.AI actually emits.

Safe under gather_evidence's asyncio.gather() concurrency: asyncio coroutines
yield cooperatively, never preemptively, so concurrent print() calls from
different coroutines in the same event loop never interleave mid-line.
"""
from __future__ import annotations

import io
import sys
import time
from dataclasses import dataclass


@dataclass
class CallMetrics:
    latency_seconds: float
    fallback_events: int   # "failed, trying next" -- one provider/key attempt failed, moved to next
    full_failures: int     # every provider/key exhausted for one structured_call invocation
    providers_seen: list[str]


class capture_call_metrics:
    def __enter__(self) -> "capture_call_metrics":
        self._start = time.monotonic()
        self._buffer = io.StringIO()
        self._real_stdout = sys.stdout
        sys.stdout = self
        return self

    def write(self, text: str) -> int:
        self._real_stdout.write(text)
        self._buffer.write(text)
        return len(text)

    def flush(self) -> None:
        self._real_stdout.flush()

    def __exit__(self, *exc) -> bool:
        sys.stdout = self._real_stdout
        elapsed = time.monotonic() - self._start
        text = self._buffer.getvalue()
        providers = sorted(set(
            line.split("provider ", 1)[1].split(" ", 1)[0].strip("'")
            for line in text.splitlines() if line.startswith("[questions] provider ")
        ))
        self.metrics = CallMetrics(
            latency_seconds=round(elapsed, 2),
            fallback_events=text.count("failed, trying next"),
            full_failures=text.count("Max retries exceeded") + text.count("API call failed on attempt"),
            providers_seen=providers,
        )
        return False
