"""The web_search links file: written by the tool executor, read by the helper."""

from __future__ import annotations

import sys
from pathlib import Path

from openjarvis.tools import tool_marks

TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
if TOOLS not in sys.path:
    sys.path.append(TOOLS)

import helper_stats  # noqa: E402

RESULT = """1. London weather - https://www.metoffice.gov.uk/weather/forecast/gcpvj0v07.
2. BBC (https://www.bbc.com/weather/2643743) and again https://www.metoffice.gov.uk/weather/forecast/gcpvj0v07
3. https://weather.com/a 4. https://example.org/b"""


def test_result_links_first_three_different_addresses():
    assert tool_marks.result_links(RESULT) == [
        "https://www.metoffice.gov.uk/weather/forecast/gcpvj0v07",
        "https://www.bbc.com/weather/2643743",
        "https://weather.com/a",
    ]
    assert tool_marks.result_links("no links here") == []


def test_links_file_round_trip(tmp_path, monkeypatch):
    links = tmp_path / "tool-web_search-links.txt"
    monkeypatch.setattr(tool_marks, "WEB_LINKS_FILE", str(links))
    monkeypatch.setattr(helper_stats, "JARVIS_DIR", str(tmp_path))
    assert helper_stats.read_web_links() is None  # no search yet
    assert tool_marks.save_web_links(RESULT)
    got = helper_stats.read_web_links()
    assert got["at"] > 0 and len(got["urls"]) == 3
    links.write_text("not-a-time\n", encoding="utf-8")
    assert helper_stats.read_web_links() is None
