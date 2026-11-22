# New file for the IronMan J.A.R.V.I.S. project (see NOTICE).
"""Where Jarvis keeps its own files: the ``.openjarvis`` folder in the user's home.

Tokens, settings, logs and the saved voice clips all live there. Every module asks
this one for the path, so the folder is named in a single place.
"""

from __future__ import annotations

import os

JARVIS_DIR = os.path.join(os.path.expanduser("~"), ".openjarvis")


def path(*parts: str) -> str:
    """A file or folder inside the Jarvis folder, e.g. path("voices", "a.wav")."""
    return os.path.join(JARVIS_DIR, *parts)
