import braille
import brailleInput
import globalPluginHandler
import scriptHandler
import inputCore

class BrailleDisplayDriver(braille.BrailleDisplayDriver):
	"""A braille display driver to allow sending of braille data to NVDA Remote
	"""
	name = "remoteBraille"
	# Translators: User visible name of the virtual braille display driver
	description = _("Remote braille")
	isThreadSafe = True

	def __init__(self):
		super(BrailleDisplayDriver, self).__init__()
		self.remoteName=None
		self.remoteDescription=None
		self.remoteNumCells=0
		self.transport=None
		if self.remoteClient.slave_session:
			self.transport=self.remoteClient.slave_session.transport
			self.transport.callback_manager.register_callback('msg_set_braille_info', self.handle_set_braille_info)
			self.transport.callback_manager.register_callback('msg_script', self.handle_input)
			self.transport.send(type="send_braille_info")

	def terminate(self):
		self.remoteName=None
		self.remoteDescription=None
		self.remoteNumCells=0
		self.transport=None
		super(BrailleDisplayDriver, self).terminate()

	def _get_remoteClient(self):
		try:
			return next(plugin for plugin in globalPluginHandler.runningPlugins if plugin.__module__=='globalPlugins.remoteClient')
		except StopIteration:
			return None

	@classmethod
	def check(cls):
		return any(plugin for plugin in globalPluginHandler.runningPlugins if plugin.__module__=='globalPlugins.remoteClient')

	def _get_numCells(self):
		return self.remoteNumCells

	def display(self, cells):
		"""Displays the given braille cells on the local machine.
		@param cells: The braille cells to display.
		@type cells: [int, ...]
		"""
		if self.transport:
			self.transport.send(type="braille_write_cells", cells=cells)
		else:
			raise RuntimeError("No transport")

	def handle_set_braille_info(self, name=None, description=None, numCells=0):
		self.remoteName=name
		self.remoteDescription=description
		self.remoteNumCells=numCells
		braille.handler.displaySize=numCells
		braille.handler.enabled = bool(numCells)

	def handle_input(self, **kwargs):
		try:
			inputCore.manager.executeGesture(InputGesture(kwargs))
		except inputCore.NoInputGestureAction:
			pass

class InputGesture(braille.BrailleDisplayGesture, brailleInput.BrailleInputGesture):

	def __init__(self, **kwargs):
		super(InputGesture, self).__init__()
		self.kwargs=kwargs
		self.__dict__.update(kwargs)
		self.source="remote{}{}".format(self.source[0].upper(),self.source[1:])
		self.attachScript(self.script)

	def attachScript(self,scriptId):
		cls=None
		script=None
		mappings=inputCore.manager.getAllGestureMappings()
		for category in mappings:
			for command in mappings[category].itervalues():
				if [command.moduleName,command.className,command.scriptName]==scriptId.rsplit(".", 2):
					cls=command.cls
					script = getattr(cls, "script_%s" % command.scriptName)
					break
		self.script=script
