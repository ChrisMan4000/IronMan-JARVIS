"""Log Jarvis in to Tado once (device login in the browser) and save the token.

  uv run --no-sync python tools\\tado_login.py

The installer runs this too and keeps its output in the install log.
"""

import os
import webbrowser

# Same file as openjarvis.tools.tado_heating.TOKEN_FILE; not imported from there because
# that loads the whole tools package and slows down the installer's login step.
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".openjarvis", "tado-token.json")


def main():
    from PyTado.interface.interface import Tado

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
