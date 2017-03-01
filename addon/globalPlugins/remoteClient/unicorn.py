import shlobj
import os
import regobj
import sys

def unicorn_lib_path():
	try:
		location = os.path.join(regobj.HKLM.SOFTWARE.Microsoft.Windows.CurrentVersion.Uninstall.UnicornDVC['InstallLocation'].data,'lib')
	except AttributeError:
		# Assume the lib is included into the add-on for now
		location = os.path.abspath(os.path.dirname(__file__))
	standardLibPath=os.path.join(location,'UnicornDVCAppLib32.dll')
	if os.path.isfile(standardLibPath):
		return standardLibPath
	return None

def vdp_rdpvcbridge_path():
	try:
		location = os.path.join(regobj.HKLM.SOFTWARE.Microsoft.Windows.CurrentVersion.Uninstall.UnicornDVC['InstallLocation'].data,'lib')
	except AttributeError:
		# Assume the lib is included into the add-on for now
		location = os.path.abspath(os.path.dirname(__file__))
	bridgeLibPath=os.path.join(location,'vdp_rdpvcbridge.dll')
	if os.path.isfile(bridgeLibPath):
		return bridgeLibPath
	return None

def unicorn_client():
	try:
		return bool(regobj.HKCU.SOFTWARE.Microsoft.get_subkey('Terminal Server Client').Default.Addins.UnicornDVCPlugin)
	except AttributeError:
		return False
