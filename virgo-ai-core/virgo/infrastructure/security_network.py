"""Narrow network transport primitive for explicitly authorized security checks."""

from __future__ import annotations

import socket


def localhost_tcp_reachable(target: str, port: int, timeout: float) -> bool:
    """Connect once to an already validated exact localhost endpoint."""
    with socket.create_connection((target, port), timeout=timeout):
        return True
