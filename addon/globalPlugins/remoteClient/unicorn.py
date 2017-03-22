import shlobj
import os
import _winreg
import sys
from ctypes import *
from ctypes.wintypes import *

ARCHITECTURE=len(bin(sys.maxsize)[1:])
CTYPE_SERVER=0
CTYPE_CLIENT=1

def unicorn_lib_path():
	try:
		with _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\UnicornDVC",0,_winreg.KEY_READ|_winreg.KEY_WOW64_32KEY) as k:
			location = os.path.join(_winreg.QueryValueEx(k,"InstallLocation")[0],'lib64' if ARCHITECTURE==64 else 'lib')
	except WindowsError:
		# Assume the lib is in the current directory
		location = os.path.abspath(os.path.dirname(__file__))
	standardLibPath=os.path.join(location,'UnicornDVCAppLib%s.dll'%ARCHITECTURE)
	if os.path.isfile(standardLibPath):
		return standardLibPath
	return None

def vdp_rdpvcbridge_path():
	try:
		with _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\UnicornDVC",0,_winreg.KEY_READ|_winreg.KEY_WOW64_32KEY) as k:
			location = os.path.join(_winreg.QueryValueEx(k,"InstallLocation")[0],'lib64' if ARCHITECTURE==64 else 'lib')
	except WindowsError:
		# Assume the lib is in the current directory
		location = os.path.abspath(os.path.dirname(__file__))
	bridgeLibPath=os.path.join(location,'vdp_rdpvcbridge.dll')
	if os.path.isfile(bridgeLibPath):
		return bridgeLibPath
	return None

def unicorn_client():
	try:
		return bool(_winreg.OpenKey(_winreg.HKEY_CURRENT_USER,"SOFTWARE\Microsoft\Terminal Server Client\Default\Addins\UnicornDVCPlugin"))
	except WindowsError:
		return False

# Utility function borrowed from NVDA to point an exported function pointer in a dll  to a ctypes wrapped python function
def _setDllFuncPointer(dll,name,cfunc):
	cast(getattr(dll,name),POINTER(c_void_p)).contents.value=cast(cfunc,c_void_p).value

class Unicorn(object):
	"""Class to facilitate DVC communication using the Unicorn DVC library"""

	def __init__(self, callbackHandler, supportView=True):
		if not isinstance(callbackHandler, UnicornCallbackHandler):
			raise TypeError("callbackHandler must be of type UnicornCallbackHandler")
		self.callbackHandler=callbackHandler
		self.supportView=supportView
		lib_path=unicorn_lib_path()
		if supportView:
			# Try to load the vdp_rdpvcbridge so UNicorn can find it regardless of its path
			try:
				self.vdp_bridge=windll.vdp_rdpvcbridge
			except WindowsError:
				vdp_bridge_path=vdp_rdpvcbridge_path()
				if vdp_bridge_path:
					try:
						self.vdp_bridge=WinDLL(vdp_bridge_path)
					except:
						self.vdp_bridge=None
		# Load Unicorn
		try:
			self.lib=getattr(windll,'UnicornDVCAppLib%s'%ARCHITECTURE)
		except WindowsError:
			if not lib_path:
				raise RuntimeError("UnicornDVC library not found")
			self.lib=WinDLL(lib_path)
		self.closed = False
		self.initialized = False
		self.Initialize=None
		self.Open=None
		self.Write=None
		self.Reader=None
		self.Close=None
		self.Terminate=None
		self.registerCallbacks(callbackHandler)
		self.registerFunctions()

	def registerCallbacks(self, callbackHandler):
		callbacks=("Connected","Disconnected","Terminated","OnNewChannelConnection","OnDataReceived","OnReadError","OnClose")
		for callback in callbacks:
			try:
				_setDllFuncPointer(self.lib,'_Unicorn_%s'%callback,getattr(callbackHandler,"c_%s"%callback))
			except AttributeError as e:
				raise AttributeError("DVC Client function pointer for %s could not be found"%callback)

	def registerFunctions(self):
		self.Initialize=WINFUNCTYPE(DWORD,DWORD,c_char_p)(('Unicorn_Initialize',self.lib),((1,'connectionType'),(1,'channelName')))
		self.Open=WINFUNCTYPE(DWORD)(('Unicorn_Open',self.lib))
		self.Write=WINFUNCTYPE(DWORD,ULONG,POINTER(BYTE))(('Unicorn_Write',self.lib),((1,'cbSize'),(1,'pBuffer')))
		self.Reader=WINFUNCTYPE(DWORD)(('Unicorn_Reader',self.lib))
		self.Close=WINFUNCTYPE(DWORD)(('Unicorn_Close',self.lib))
		self.Terminate=WINFUNCTYPE(DWORD)(('Unicorn_Terminate',self.lib))

class UnicornCallbackHandler(object):

	def __init__(self):
		self.c_Connected=WINFUNCTYPE(DWORD)(self._Connected)
		self.c_Disconnected=WINFUNCTYPE(DWORD, DWORD)(self._Disconnected)
		self.c_Terminated=WINFUNCTYPE(DWORD)(self._Terminated)
		self.c_OnNewChannelConnection=WINFUNCTYPE(DWORD)(self._OnNewChannelConnection)
		self.c_OnDataReceived=WINFUNCTYPE(DWORD,ULONG,POINTER(BYTE))(self._OnDataReceived)
		self.c_OnReadError=WINFUNCTYPE(DWORD,DWORD)(self._OnReadError)
		self.c_OnClose=WINFUNCTYPE(DWORD)(self._OnClose)

	def _Connected(self):
		return 0

	def _Disconnected(self,dwDisconnectCode):
		return 0

	def _Terminated(self):
		return 0

	def _OnNewChannelConnection(self):
		return 0

	def _OnDataReceived(self,cbSize,data):
		return 0

	def _OnReadError(self,dwError):
		return 0

	def _OnClose(self):
		return 0
