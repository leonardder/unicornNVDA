import threading
import time
import Queue
import ssl
import socket
import select
from collections import defaultdict
#from logging import getLogger
#log = getLogger('transport')
from logHandler import log
import callback_manager
from ctypes import *
from ctypes.wintypes import *
import NVDAHelper
import win32con
from unicorn import *

PROTOCOL_VERSION = 2
DVCTYPES=('slave','master')

class Transport(object):

	def __init__(self, serializer):
		self.serializer = serializer
		self.callback_manager = callback_manager.CallbackManager()
		self.connected = False
		self.successful_connects = 0

	def transport_connected(self):
		self.successful_connects += 1
		self.connected = True
		self.callback_manager.call_callbacks('transport_connected')

class TCPTransport(Transport):

	def __init__(self, serializer, address, timeout=0):
		super(TCPTransport, self).__init__(serializer=serializer)
		self.closed = False
		#Buffer to hold partially received data
		self.buffer = ""
		self.queue = Queue.Queue()
		self.address = address
		self.server_sock = None
		self.queue_thread = None
		self.timeout = timeout
		self.reconnector_thread = ConnectorThread(self)

	def run(self):
		self.closed = False
		self.server_sock = self.create_server_socket()
		try:
			self.server_sock.connect(self.address)
		except Exception as e:
			self.callback_manager.call_callbacks('transport_connection_failed')
			raise
		self.transport_connected()
		self.queue_thread = threading.Thread(target=self.send_queue)
		self.queue_thread.daemon = True
		self.queue_thread.start()
		while self.server_sock is not None:
			try:
				readers, writers, error = select.select([self.server_sock], [], [self.server_sock])
			except socket.error:
				self.buffer = ""
				break
			if self.server_sock in error:
				self.buffer = ""
				break
			if self.server_sock in readers:
				try:
					self.handle_server_data()
				except socket.error:
					self.buffer = ""
					break
		self.connected = False
		self.callback_manager.call_callbacks('transport_disconnected')
		self._disconnect()

	def create_server_socket(self):
		server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		if self.timeout:
			server_sock.settimeout(self.timeout)
		server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		server_sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 60000, 2000))
		server_sock = ssl.wrap_socket(server_sock)
		return server_sock

	def handle_server_data(self):
		data = self.buffer + self.server_sock.recv(16384)
		self.buffer = ""
		if data == '':
			self._disconnect()
			return
		if '\n' not in data:
			self.buffer += data
			return
		while '\n' in data:
			line, sep, data = data.partition('\n')
			self.parse(line)
		self.buffer += data

	def parse(self, line):
		obj = self.serializer.deserialize(line)
		if 'type' not in obj:
			return
		callback = "msg_"+obj['type']
		del obj['type']
		self.callback_manager.call_callbacks(callback, **obj)

	def send_queue(self):
		while True:
			item = self.queue.get()
			if item is None:
				return
			try:
				self.server_sock.sendall(item)
			except socket.error:
				return

	def send(self, type, **kwargs):
		obj = self.serializer.serialize(type=type, **kwargs)
		if self.connected:
			self.queue.put(obj)

	def _disconnect(self):
		"""Disconnect the transport due to an error, without closing the connector thread."""
		if not self.connected:
			return
		if self.queue_thread is not None:
			self.queue.put(None)
			self.queue_thread.join()
		clear_queue(self.queue)
		self.server_sock.close()
		self.server_sock = None

	def close(self):
		self.callback_manager.call_callbacks('transport_closing')
		self.reconnector_thread.running = False
		self._disconnect()
		self.closed = True
		self.reconnector_thread = ConnectorThread(self)

class RelayTransport(TCPTransport):

	def __init__(self, serializer, address, timeout=0, channel=None, connection_type=None, protocol_version=PROTOCOL_VERSION):
		super(RelayTransport, self).__init__(address=address, serializer=serializer, timeout=timeout)
		log.info("Connecting to %s channel %s" % (address, channel))
		self.channel = channel
		self.connection_type = connection_type
		self.protocol_version = protocol_version
		self.callback_manager.register_callback('transport_connected', self.on_connected)

	def on_connected(self):
		self.send('protocol_version', version=self.protocol_version)
		if self.channel is not None:
			self.send('join', channel=self.channel, connection_type=self.connection_type)
		else:
			self.send('generate_key')

class DVCTransport(Transport):

	def __init__(self, serializer, timeout=60, connection_type=None, channel=None, protocol_version=PROTOCOL_VERSION):
		super(DVCTransport, self).__init__(serializer=serializer)
		lib_path=unicorn_lib_path()
		vdp_bridge_path=vdp_rdpvcbridge_path()
		if connection_type not in DVCTYPES:
			raise ValueError("Unsupported connection type for DVC connection")
		elif not isinstance(channel,str):
			raise ValueError("Invalid key provided")
		elif not lib_path:
			raise NotImplementedError("UnicornDVC library not found")
		log.info("Connecting to DVC as %s" % connection_type)
		# first, try to load the vdp_rdpvcbridge
		try:
			vdp_bridge=cdll.LoadLibrary(vdp_bridge_path)
		except:
			log.exception('Unable to load VDP RDP VC Bridge')
		self.lib=windll.LoadLibrary(lib_path)
		self.channel = channel
		self.closed = False
		self.initialized = False
		#Buffer to hold partially received data
		self.buffer = ""
		self.queue = Queue.Queue()
		self.queue_thread = None
		self.read_thread = None
		self.error_event=threading.Event()
		self.timeout = timeout
		self.reconnector_thread = ConnectorThread(self,run_except=WindowsError)
		self.connection_type = connection_type
		self.protocol_version = protocol_version
		self.callback_manager.register_callback('msg_protocol_version', self.handle_p2p)
		self	.register_lib_callbacks()

	def register_lib-callbacks(self):
		callbacks=("_Connected","_Disconnected","_Terminated","_OnNewChannelConnection","_OnDataReceived","_OnReadError","_OnClose")
		self.c_Connected=WINFUNCTYPE(LONG)(self._Connected)
		self.c_Disconnected=WINFUNCTYPE(LONG, DWORD)(self._Disconnected)
		self.c_Terminated=WINFUNCTYPE(LONG)(self._Terminated)
		self.c_OnNewChannelConnection=WINFUNCTYPE(LONG)(self._OnNewChannelConnection)
		self.c_OnDataReceived=WINFUNCTYPE(LONG,ULONG,POINTER(c_char))(self._OnDataReceived)
		self.c_OnReadError=WINFUNCTYPE(LONG,DWORD)(self._OnReadError)
		self.c_OnClose=WINFUNCTYPE(LONG)(self._OnClose)
		for callback in callbacks:
			try:
				NVDAHelper._setDllFuncPointer(self.lib,callback,getattr(self,"c%s"%callback))
			except AttributeError as e:
				log.error("DVC Client function pointer for %s could not be found"%callback,exc_info=True)
				raise e

	def initialize_lib(self):
		if self.initialized:
			return
		res=self.lib.Initialize(DWORD(DVCTYPES.index(self.connection_type)),create_string_buffer(self.channel))
		if res:
			raise WinError(res)
		self.initialized = True

	def terminate_lib(self):
		if not self.initialized:
			return
		res=self.lib.Terminate()
		if res:
			raise WinError(res)
		self.initialized = False

	def run(self):
		self.closed = False
		self.error_event.clear()
		self.queue_thread = threading.Thread(target=self.send_queue)
		self.queue_thread.daemon = True
		self.queue_thread.start()
		self	.initialize_lib()
		if self.connection_type=='slave':
			res=self.lib.Open()
			if res:
				self.callback_manager.call_callbacks('transport_connection_failed')
				raise WinError(res)
			self.read_thread = threading.Thread(target=self.lib.Reader)
			self.read_thread.daemon = True
			self.read_thread.start()
		elif not unicorn_client(): # Master
			self.callback_manager.call_callbacks('transport_connection_failed')
			raise
		self.error_event.wait()
		self.connected = False
		self.callback_manager.call_callbacks('transport_disconnected')
		res = self.lib.Close()
		if res:
			log.warning(WinError(res))
		self._disconnect()

	def handle_data(self, str):
		data = self.buffer+str
		self.buffer = ""
		if data == '':
			self._disconnect()
			return
		if '\n' not in data:
			self.buffer += data
			return
		while '\n' in data:
			line, sep, data = data.partition('\n')
			self.parse(line)
		self.buffer += data

	def parse(self, line):
		obj = self.serializer.deserialize(line)
		if 'type' not in obj:
			return
		callback = "msg_"+obj['type']
		del obj['type']
		self.callback_manager.call_callbacks(callback, **obj)

	def send_queue(self):
		while True:
			item = self.queue.get()
			if item is None:
				return
			strbuf=create_string_buffer(item)
			res=self.lib.Write(sizeof(strbuf),strbuf)
			if res:
				log.warning(WinError(res))
				return

	def send(self, type, **kwargs):
		obj = self.serializer.serialize(type=type, origin=-1, **kwargs)
		if self.connected:
			self.queue.put(obj)

	def _disconnect(self):
		if not self.connected:
			return
		self.error_event.set()
		# Closing in this context is the equivalent for disconnecting the transport
		res = self.lib.Close()
		if res:
			log.warning(WinError(res))
		if self.queue_thread is not None:
			self.queue.put(None)
			self.queue_thread.join()
		clear_queue(self.queue)
		if self.connection_type=='slave' and self.read_thread is not None:
			self.read_thread.join()

	def close(self):
		self.callback_manager.call_callbacks('transport_closing')
		self.reconnector_thread.running = False
		self._disconnect()
		# Terminating in this context is the equivalent for closing the transport
		res = self.terminate_lib()
		if res:
			raise WinError(res)
		self.closed = True
		self.reconnector_thread = ConnectorThread(self,run_except=WindowsError)

	def handle_p2p(self, version, **kwargs):
		if version==PROTOCOL_VERSION:
			self.send(type='client_joined', client=dict(id=-1, connection_type=self.connection_type))
		else:
			self.send(type='version_mismatch')

	def _Connected(self):
		log.info("Connected to remote protocol server")
		return 0

	def _Disconnected(self,dwDisconnectCode):
		log.warning("Disconnected from remote protocol server")
		self._disconnect()
		return 0

	def _Terminated(self):
		log.info("Remote protocol client terminated")
		self._disconnect()
		return 0

	def _OnNewChannelConnection(self):
		log.info("DVC connection initiated from remote protocol server")
		self.transport_connected()
		self.send('protocol_version', version=self.protocol_version)		
		return 0

	def _OnDataReceived(self,cbSize,data):
		str="".join(data[i] for i in xrange(cbSize))
		if "\x00" not in str:
			self.buffer+=str
		else:
			self.handle_data(str.replace("\x00",""))
		return 0

	def _OnReadError(self,dwError):
		# Note, this is called from self.read_thread
		log.warning("Error reading from DVC, %d"%dwError)
		self.error_event.set()
		return 0

	def _OnClose(self):
		log.info("DVC close request received")
		self.callback_manager.call_callbacks('msg_client_left', client=dict(id=-1))
		self._disconnect()
		return 0

class ConnectorThread(threading.Thread):

	def __init__(self, connector, connect_delay=5, run_except=socket.error):
		super(ConnectorThread, self).__init__()
		self.connect_delay = connect_delay
		self.run_except = run_except
		self.running = True
		self.connector = connector
		self.name = self.name + "_connector_loop"
		self.daemon = True

	def run(self):
		while self.running:
			try:
				self.connector.run()
			except self.run_except as e:
				log.debugWarning("Connection failed",exc_info=True)
				time.sleep(self.connect_delay)
				continue
			else:
				time.sleep(self.connect_delay)
		log.info("Ending control connector thread %s" % self.name)

def clear_queue(queue):
	try:
		while True:
			queue.get_nowait()
	except:
		pass
