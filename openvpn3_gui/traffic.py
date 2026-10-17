"""Validated transport counters and bounded, monotonic traffic samples."""

from collections import deque
import json
import math


def parse_counters(output):
    values = json.loads(output)
    if not isinstance(values, dict):
        raise ValueError("Statistics must be a JSON object")
    counters = []
    for name in ("BYTES_IN", "BYTES_OUT"):
        value = values.get(name)
        if type(value) is not int or not 0 <= value <= 2**64 - 1:
            raise ValueError(f"Missing or invalid {name} counter")
        counters.append(value)
    return tuple(counters)


def format_bytes(value, rate=False):
    if value is None:
        return "—"
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")
    value = float(value)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            number = f"{value:.0f}" if unit == "B" else f"{value:.1f}"
            return f"{number} {unit}" + ("/s" if rate else "")
        value /= 1024


class TrafficHistory:
    """One session only. Gaps and counter resets never create invented rates."""

    def __init__(self):
        self.samples = deque(maxlen=90)
        self.previous = None
        self.totals = None
        self.rates = None
        self.updated = None

    def add(self, now, counters):
        if not math.isfinite(now):
            raise ValueError("Invalid sample time")
        rates = None
        if self.previous:
            then, old = self.previous
            elapsed = now - then
            if elapsed <= 0:
                return
            if elapsed <= 10 and all(
                new >= before for new, before in zip(counters, old)
            ):
                rates = tuple(
                    (new - before) / elapsed for new, before in zip(counters, old)
                )
        self.previous = (now, counters)
        self.totals = counters
        self.updated = now
        self.rates = rates
        self.samples.append((now, rates))
        while self.samples and self.samples[0][0] < now - 60:
            self.samples.popleft()

    def interrupt(self):
        self.previous = None
        self.rates = None
