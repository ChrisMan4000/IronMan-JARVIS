"""Change logs: one timestamped line per change; a broken log never blocks a change."""

from __future__ import annotations

import re

from openjarvis.tools import device_log


def test_append_change(tmp_path):
    log = tmp_path / "tado-set-log.txt"
    device_log.append_change(str(log), "set | Kitchen | set to 21.0 C until resumed")
    device_log.append_change(str(log), "resume | Kitchen | back to schedule")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert re.fullmatch(
        r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d set \| Kitchen \| set to 21.0 C until resumed",
        lines[0],
    )


def test_unwritable_log_is_ignored(tmp_path):
    device_log.append_change(
        str(tmp_path / "missing-dir" / "log.txt"), "on"
    )  # no exception
