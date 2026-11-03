"""Log Jarvis in to Tado once (device login in the browser) and save the token.

  uv run --no-sync python tools\\tado_login.py

The installer runs this too and keeps its output in the install log.
"""

from __future__ import annotations

import webbrowser

from PyTado.interface.interface import Tado

from openjarvis.tools.tado_heating import TOKEN_FILE  # the file the Tado tool reads


def main() -> None:
    tado = Tado(token_file_path=TOKEN_FILE)
    print("Status:", tado.device_activation_status(), flush=True)
    url = tado.device_verification_url()
    print("Open this link in your browser and approve:", url, flush=True)
    # Opens the default browser (Firefox, Edge, Chrome ...).
    if not webbrowser.open(url):
        print("(Could not open a browser by itself: copy the link above.)", flush=True)
    tado.device_activation()
    print("Login OK", flush=True)


if __name__ == "__main__":
    main()  # an error ends the script with its traceback, which the install log keeps
