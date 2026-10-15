import os
from PyTado.interface.interface import Tado
t = Tado(token_file_path=os.path.join(os.path.expanduser("~"), ".openjarvis", "tado-token.json"))
print("Status:", t.device_activation_status())
url = t.device_verification_url()
print("Open this link in Firefox and approve:", url)
t.device_activation()
print("Login OK")