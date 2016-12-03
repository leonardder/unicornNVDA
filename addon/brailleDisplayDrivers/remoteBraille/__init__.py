import braille
import brailleInput
import globalPluginHandler
import scriptHandler
import inputCore
import api

class BrailleDisplayDriver(braille.BrailleDisplayDriver):
	"""A braille display driver to allow sending of braille data to NVDA Remote
	"""
	name = "remoteBraille"
	# Translators: User visible name of the virtual braille display driver
	description = _("Remote braille")
	isThreadSafe = True
	#gestureMap=inputCore.GlobalGestureMap()

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
			inputCore.manager.executeGesture(InputGesture(self.remoteName, **kwargs))
		except inputCore.NoInputGestureAction:
			pass

class InputGesture(braille.BrailleDisplayGesture, brailleInput.BrailleInputGesture):

	def __init__(self, **kwargs):
		super(InputGesture, self).__init__()
		self.__dict__.update(kwargs)
		self.source="remote{}{}".format(self.source[0].upper(),self.source[1:])
		self.scriptPath=getattr(self,"scriptPath","")
		self.script=self.findScript() if self.scriptPath else None

	def findScript(self):
		if not self.scriptPath:
			return None
		module,cls,scriptName=self.scriptPath
		focus = api.getFocusObject()
		if not focus:
			return None
		if scriptName.startswith("kb:"):
			# Emulate a key press.
			return scriptHandler._makeKbEmulateScript(scriptName)
		
				# Global plugin level.
		for plugin in globalPluginHandler.runningPlugins:
			func = getattr(plugin, "script_%s" % scriptName, None)
			if func:
				return func

		# App module level.
		app = focus.appModule
		if app:
			func = getattr(app, "script_%s" % scriptName, None)
			if func:
				return func

		# Tree interceptor level.
		treeInterceptor = focus.treeInterceptor
		if treeInterceptor and treeInterceptor.isReady:
			func = getattr(treeInterceptor , "script_%s" % scriptName, None)
			# We are no keyboard input
			return func

		# NVDAObject level.
		func = getattr(focus, "script_%s" % scriptName, None)
		if func:
			return func
		for obj in reversed(api.getFocusAncestors()):
			func = getattr(obj, "script_%s" % scriptName, None)
			if func and getattr(func, 'canPropagate', False):
				return func

		# Global commands.
		func = getattr(globalCommands.commands, "script_%s" % scriptName, None)
		if func:
			return func

		return None
