"""Accessible live counters and a Cairo graph; no external plotting dependency."""

import time
from gi.repository import Gtk
from .traffic import format_bytes
from .widgets import label


class TrafficPanel(Gtk.Box):
    def __init__(self, appearance):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.appearance = appearance
        self.history = None
        self.pack_start(label("CONNECTION TRAFFIC", "eyebrow"), False, False, 0)
        columns = Gtk.Box(spacing=16, homogeneous=True)
        self.speeds, self.totals = [], []
        for title, style in (
            ("↓ Received", "traffic-received"),
            ("↑ Sent", "traffic-sent"),
        ):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            column.pack_start(label(title, style), False, False, 0)
            speed = label("—", "traffic-value")
            total = label("— total", "muted")
            column.pack_start(speed, False, False, 0)
            column.pack_start(total, False, False, 0)
            columns.pack_start(column, True, True, 0)
            self.speeds.append(speed)
            self.totals.append(total)
        self.pack_start(columns, False, False, 0)
        self.graph_scale = label("Last 60 seconds · waiting for samples", "muted")
        self.pack_start(self.graph_scale, False, False, 0)
        self.graph = Gtk.DrawingArea()
        self.graph.set_size_request(100, 82)
        self.graph.get_accessible().set_name(
            "Received and sent traffic over the last 60 seconds; current values are shown above"
        )
        self.graph.connect("draw", self.draw)
        self.pack_start(self.graph, False, False, 0)
        self.note = label("Connect to see live traffic.", "muted")
        self.pack_start(self.note, False, False, 0)
        self.set_tooltip_text(
            "OpenVPN transport bytes, including VPN overhead. Speeds are averaged between samples, usually two seconds apart. Totals cover the session; the chart covers samples collected while this connection is selected."
        )

    def update(self, history=None, state="Connect to see live traffic.", live=False):
        self.history = history
        rates = history.rates if history and live else None
        for index in range(2):
            self.speeds[index].set_text(
                format_bytes(rates[index] if rates else None, rate=True)
            )
            self.totals[index].set_text(
                format_bytes(
                    history.totals[index] if history and history.totals else None
                )
                + " total"
            )
        self.note.set_text(state)
        peak = (
            max(
                (max(rates) for _, rates in history.samples if rates is not None),
                default=0,
            )
            if history
            else 0
        )
        self.graph_scale.set_text(
            "Last 60 seconds · "
            + (
                "scale " + format_bytes(max(1024, peak * 1.15), rate=True)
                if peak
                else "waiting for traffic"
            )
        )
        self.graph.queue_draw()

    def draw(self, widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        dark = self.appearance.dark
        cr.set_source_rgba(
            *((0.65, 0.72, 0.85, 0.18) if dark else (0.25, 0.35, 0.5, 0.18))
        )
        cr.set_line_width(1)
        for fraction in (0, 0.5, 1):
            y = 3 + fraction * (height - 6)
            cr.move_to(0, y)
            cr.line_to(width, y)
        cr.stroke()
        if not self.history or not self.history.samples:
            return False
        samples = list(self.history.samples)
        end = max(time.monotonic(), samples[-1][0])
        # A disconnected snapshot retains its last minute rather than scrolling away.
        if self.note.get_text().startswith("Last recorded"):
            end = samples[-1][0]
        peak = max(
            1024, max((max(r) for _, r in samples if r is not None), default=0) * 1.15
        )
        colors = (
            ((0.44, 0.87, 0.75), (1, 0.71, 0.45))
            if dark
            else ((0.03, 0.47, 0.37), (0.65, 0.29, 0))
        )
        for index, color in enumerate(colors):
            cr.set_source_rgb(*color)
            cr.set_line_width(2)
            cr.set_dash([] if index == 0 else [5, 3])
            started = False
            for timestamp, rates in samples:
                if rates is None or timestamp < end - 60:
                    started = False
                    continue
                x = (timestamp - end + 60) / 60 * width
                y = height - 3 - rates[index] / peak * (height - 6)
                if started:
                    cr.line_to(x, y)
                else:
                    cr.move_to(x, y)
                started = True
            cr.stroke()
        return False
