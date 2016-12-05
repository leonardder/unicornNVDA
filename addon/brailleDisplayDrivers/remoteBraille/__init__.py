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
			self.transport.callback_manager.register_callback('msg_execute_gesture', self.handle_input)
			self.transport.send(type="send_braille_info")

	def terminate(self):
		if self.transport:
			self.transport.callback_manager.unregister_callback('msg_set_braille_info', self.handle_set_braille_info)
			self.transport.callback_manager.unregister_callback('msg_execute_gesture', self.handle_input)
			self.transport.send(type="sending_braille", state=False)
			self.transport=None
		self.remoteName=None
		self.remoteDescription=None
		self.remoteNumCells=0
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
		currentNumCells=braille.handler.display.numCells
		braille.handler.displaySize=numCells 		if braille.handler.display==self or currentNumCells==0 else min(currentNumCells,numCells)
		braille.handler.enabled = bool(braille.handler.displaySize)
		self.transport.send(type="sending_braille", state=True)

	def handle_input(self, **kwargs):
		try:
			inputCore.manager.executeGesture(InputGesture(**kwargs))
		except inputCore.NoInputGestureAction:
			pass

class InputGesture(braille.BrailleDisplayGesture, brailleInput.BrailleInputGesture):

	def __init__(self, **kwargs):
		super(InputGesture, self).__init__()
		self.__dict__.update(kwargs)
		self.source="remote{}{}".format(self.source[0].upper(),self.source[1:])
		self.scriptPath=getattr(self,"scriptPath",None)
		self.script=self.findScript() if self.scriptPath else None

	def findScript(self):
		if not (isinstance(self.scriptPath,list) and len(self.scriptPath)==3):
			return None
		module,cls,scriptName=self.scriptPath
		focus = api.getFocusObject()
		if not focus:
			return None
		if scriptName.startswith("kb:"):
			# Emulate a key press.
			return scriptHandler._makeKbEmulateScript(scriptName)

		import globalCommands

		# Global plugin level.
		if cls=='GlobalPlugin':
			for plugin in globalPluginHandler.runningPlugins:
				if module==plugin.__module__:
					func = getattr(plugin, "script_%s" % scriptName, None)
					if func:
						return func

		# App module level.
		app = focus.appModule
		if app and cls=='AppModule' and module==app.__module__:
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
