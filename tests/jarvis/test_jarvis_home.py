"""The one place that names the Jarvis data folder."""

from __future__ import annotations

import os

from openjarvis.tools import jarvis_home, tado_heating, tool_marks


def test_folder_is_dot_openjarvis_in_home():
    assert os.path.basename(jarvis_home.JARVIS_DIR) == ".openjarvis"
    assert os.path.dirname(jarvis_home.JARVIS_DIR) == os.path.expanduser("~")


def test_path_joins_below_the_folder():
    assert jarvis_home.path("voices", "a.wav") == os.path.join(jarvis_home.JARVIS_DIR, "voices", "a.wav")


def test_tools_use_the_shared_folder():
    assert tado_heating.TOKEN_FILE == jarvis_home.path("tado-token.json")
    assert tool_marks.JARVIS_DIR == jarvis_home.JARVIS_DIR
