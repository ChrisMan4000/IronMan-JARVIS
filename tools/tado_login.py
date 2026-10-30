import os, webbrowser, traceback
try:
    from PyTado.interface.interface import Tado
    t = Tado(token_file_path=os.path.join(os.path.expanduser("~"), ".openjarvis", "tado-token.json"))
    print("Status:", t.device_activation_status(), flush=True)
    url = t.device_verification_url()
    print("Open this link in your browser and approve:", url, flush=True)
    try:
        webbrowser.open(url)   # opens the default browser (Firefox, Edge, Chrome ...)
    except Exception:
        pass
    t.device_activation()
    print("Login OK", flush=True)
except Exception:
    traceback.print_exc()
    raise
