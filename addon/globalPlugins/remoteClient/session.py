import threading
import time
import speech
import ui
import tones
import braille
import nvda_patcher

class RemoteSession(object):

	def __init__(self, local_machine, transport):
		self.local_machine = local_machine
		self.transport = transport
		self.patcher = None

class SlaveSession(RemoteSession):
	"""Session that runs on the slave and manages state."""

	def __init__(self, *args, **kwargs):
		super(SlaveSession, self).__init__(*args, **kwargs)
		self.transport.callback_manager.register_callback('msg_client_joined', self.handle_client_connected)
		self.transport.callback_manager.register_callback('msg_client_left', self.handle_client_disconnected)
		self.transport.callback_manager.register_callback('msg_key', self.local_machine.send_key)
		self.masters = {}
		self.last_client_index = None
		self.transport.callback_manager.register_callback('msg_index', self.update_index)
		self.transport.callback_manager.register_callback('transport_closing', self.handle_transport_closing)
		self.patcher = nvda_patcher.NVDASlavePatcher()
		self.patch_callbacks_added = False
		self.transport.callback_manager.register_callback('msg_channel_joined', self.handle_channel_joined)
		self.transport.callback_manager.register_callback('msg_set_clipboard_text', self.local_machine.set_clipboard_text)
		self.transport.callback_manager.register_callback('msg_send_SAS', self.local_machine.send_SAS)

	def handle_client_connected(self, user_id=None):
		self.patcher.patch()
		if not self.patch_callbacks_added:
			self.add_patch_callbacks()
			self.patch_callbacks_added = True
		self.patcher.orig_beep(1000, 300)
		self.masters[user_id] = True

	def handle_channel_joined(self, channel=None, user_ids=None):
		for user in user_ids:
			self.handle_client_connected(user_id=user)

	def handle_transport_closing(self):
		self.patcher.unpatch()
		if self.patch_callbacks_added:
			self.remove_patch_callbacks()
			self.patch_callbacks_added = False

	def handle_transport_disconnected(self):
		self.patcher.orig_beep(1000, 300)
		self.patcher.unpatch()

	def handle_client_disconnected(self, user_id=None):
		self.patcher.orig_beep(108, 300)
		del self.masters[user_id]
		if not self.masters:
			self.patcher.unpatch()

	def add_patch_callbacks(self):
		patcher_callbacks = (('speak', self.speak), ('beep', self.beep), ('wave', self.playWaveFile), ('cancel_speech', self.cancel_speech))
		for event, callback in patcher_callbacks:
			self.patcher.register_callback(event, callback)
		self.patcher.set_last_index_callback(self._get_lastIndex)

	def remove_patch_callbacks(self):
		patcher_callbacks = (('speak', self.speak), ('beep', self.beep), ('wave', self.playWaveFile), ('cancel_speech', self.cancel_speech))
		for event, callback in patcher_callbacks:
			self.patcher.unregister_callback(event, callback)

	def speak(self, speechSequence):
		self.transport.send(type="speak", sequence=speechSequence)

	def cancel_speech(self):
		self.transport.send(type="cancel")

	def _get_lastIndex(self):
		return self.last_client_index

	def beep(self, hz, length, left=50, right=50):
		self.transport.send(type='tone', hz=hz, length=length, left=left, right=right)

	def playWaveFile(self, fileName, async=True):
		self.transport.send(type='wave', fileName=fileName, async=async)

	def update_index(self, index=None):
		self.last_client_index = index

class MasterSession(RemoteSession):

	def __init__(self, *args, **kwargs):
		super(MasterSession, self).__init__(*args, **kwargs)
		self.slaves = []
		self.index_thread = None
		self.patcher = nvda_patcher.NVDAMasterPatcher()
		self.patch_callbacks_added = False
		self.transport.callback_manager.register_callback('msg_speak', self.local_machine.speak)
		self.transport.callback_manager.register_callback('msg_cancel', self.local_machine.cancel_speech)
		self.transport.callback_manager.register_callback('msg_braille_write_cells', self.local_machine.braille_write_cells)
		self.transport.callback_manager.register_callback('msg_tone', self.local_machine.beep)
		self.transport.callback_manager.register_callback('msg_wave', self.local_machine.play_wave)
		self.transport.callback_manager.register_callback('msg_nvda_not_connected', self.handle_nvda_not_connected)
		self.transport.callback_manager.register_callback('msg_client_joined', self.handle_client_connected)
		self.transport.callback_manager.register_callback('msg_client_left', self.handle_client_disconnected)
		self.transport.callback_manager.register_callback('msg_channel_joined', self.handle_channel_joined)
		self.transport.callback_manager.register_callback('msg_set_clipboard_text', self.local_machine.set_clipboard_text)
		self.transport.callback_manager.register_callback('msg_send_braille_info', self.send_braille_info)
		self.transport.callback_manager.register_callback('transport_connected', self.handle_connected)
		self.transport.callback_manager.register_callback('transport_disconnected', self.handle_disconnected)

	def handle_nvda_not_connected(self):
		speech.cancelSpeech()
		ui.message(_("Remote NVDA not connected."))

	def handle_connected(self):
		if self.index_thread is not None:
			return
		self.index_thread = threading.Thread(target=self.send_indexes)
		self.index_thread.daemon = True
		self.index_thread.start()

	def handle_disconnected(self):
		self.index_thread = None

	def handle_channel_joined(self, channel=None, user_ids=None):
		for user in user_ids:
			self.handle_client_connected(user_id=user)

	def handle_client_connected(self, user_id=None):
		self.patcher.patch_set_display()
		if not self.patch_callbacks_added:
			self.add_patch_callbacks()
			self.patch_callbacks_added = True
		tones.beep(1000, 300)

	def handle_client_disconnected(self, user_id=None):
		self.patcher.unpatch_set_display()
		if self.patch_callbacks_added:
			self.remove_patch_callbacks()
			self.patch_callbacks_added = False
		tones.beep(108, 300)

	def execute_gesture(self,**kwargs):
		self.transport.send(type="execute_gesture", **kwargs)

	def send_braille_info(self):
		display=braille.handler.display
		self.transport.send(type="set_braille_info", name=display.name, description=display.description, numCells=display.numCells)

	def send_indexes(self):
		last = None
		POLL_TIME = 0.05
		while self.transport.connected:
			synth = speech.getSynth()
			if synth is None: #While switching synths
				time.sleep(POLL_TIME)
				continue
			index = synth.lastIndex
			if index != last:
				self.transport.send(type="index", index=index)
				last = index
			time.sleep(POLL_TIME)

	def add_patch_callbacks(self):
		patcher_callbacks = (('execute_gesture', self.execute_gesture), ('set_display', self.send_braille_info))
		for event, callback in patcher_callbacks:
			self.patcher.register_callback(event, callback)

	def remove_patch_callbacks(self):
		patcher_callbacks = (('execute_gesture', self.execute_gesture), ('set_display', self.send_braille_info))
		for event, callback in patcher_callbacks:
			self.patcher.unregister_callback(event, callback)
