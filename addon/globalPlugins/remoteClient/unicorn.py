import shlobj
import os
import regobj

def unicorn_lib_path():
	try:
		location = regobj.HKLM.SOFTWARE.Microsoft.Windows.CurrentVersion.Uninstall.UnicornDVC['InstallLocation'].data
	except AttributeError:
		# Assume the lib is included into the add-on for now
		location = os.path.abspath(os.path.dirname(__file__))
	libPath=os.path.join(location,'UnicornDVCAppLib32.dll')
	if os.path.isfile(libPath):
		return libPath
	else:
		return None

def unicorn_client():
	try:
		return bool(regobj.HKCU.SOFTWARE.Microsoft.get_subkey('Terminal Server Client').Default.Addins.UnicornDVCPlugin)
	except AttributeError:
		return False
