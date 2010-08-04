#!/usr/bin/python
# -*- coding: UTF-8 -*-

"""
 Tuquito Update Manager 0.1
 Copyright (C) 2010
 Author: Mario Colque <mario@tuquito.org.ar>
 Tuquito Team! - www.tuquito.org.ar

 This program is free software; you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation; version 3 of the License.
 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 GNU General Public License for more details.
 You should have received a copy of the GNU General Public License
 along with this program; if not, write to the Free Software
 Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
"""

import os
import commands
#import sys
import gtk
import threading
import tempfile
import time
import gettext, webkit, string
import apt
from user import home
from subprocess import Popen, PIPE

# i18n
gettext.install('tuquito-update-manager', '/usr/share/tuquito/locale')

APP_PATH = '/usr/lib/tuquito/tuquito-update/'

# icons
updated = os.path.join(APP_PATH, 'icons/updated.png')
busy = os.path.join(APP_PATH, 'icons/busy.png')
error = os.path.join(APP_PATH, 'icons/error.png')
errorConnecting = os.path.join(APP_PATH, 'icons/errorConnecting.png')
newUpdates = os.path.join(APP_PATH, 'icons/newUpdates.png')
newUpgrade = os.path.join(APP_PATH, 'icons/newUpgrade.png')

# Falgs
ready = False
showWindow  = False

class RefreshThread(threading.Thread):
	def __init__(self, statusIcon, window, synaptic=False):
		threading.Thread.__init__(self)
		self.synaptic = synaptic
		self.window = window
		self.statusIcon = statusIcon
		self.statusIcon.set_from_file(busy)

	def convert(self, size):
		strSize = str(size) + _('B')
		if (size >= 1000):
			strSize = str(size / 1000) + _('KB')
		if (size >= 1000000):
			strSize = str(size / 1000000) + _('MB')
		if (size >= 1000000000):
			strSize = str(size / 1000000000) + _('GB')
		return strSize

	def checkDependencies(self, changes, cache):
		foundSomething = False
		for pkg in changes:
			for dep in pkg.candidateDependencies:
				for o in dep.or_dependencies:
					try:
						if cache[o.name].isUpgradable:
							pkgFound = False
							for pkg2 in changes:
								if o.name == pkg2.name:
									pkgFound = True
							if pkgFound == False:
								newPkg = cache[o.name]
								changes.append(newPkg)
								foundSomething = True
					except Exception, detail:
						pass
		if foundSomething:
			changes = checkDependencies(changes, cache)
		return changes

	def run(self):
		global log, html, totalSize, cant, ready, showWindow
		proxy = None
		try:
			from urllib import urlopen
			url=urlopen('http://google.com', None, proxy)
			url.read()
			url.close()
		except Exception, detail:
			if os.system('ping google.com -c1 -q'):
				gtk.gdk.threads_enter()
				self.statusIcon.set_from_file(errorConnecting)
				self.statusIcon.set_tooltip(_('Could not connect to the Internet'))
				log.writelines('-- No connection found (tried to read http://www.google.com and to ping google.com)\n')
				log.flush()
				gtk.gdk.threads_leave()
				return False
			else:
				log.writelines('++ Connection found - checking for updates\n')
				log.flush()

		gtk.gdk.threads_enter()
		self.statusIcon.set_tooltip(_('Checking for Updates...'))
		gtk.gdk.threads_leave()

		try:
			if self.synaptic:
				print "synaptic"
				from subprocess import Popen, PIPE
				cmd = 'gksu "/usr/sbin/synaptic --hide-main-window --update-at-startup --non-interactive" -D "%s"' % _('Tuquito Update')
				comnd = Popen(cmd, shell=True)
				returnCode = comnd.wait()
			else:
				print "no synaptic"
				cache = apt.Cache()
				cache.update()
			cache = apt.Cache()
			cache.upgrade(True)
			changes = cache.getChanges()
		except Exception, detail:
			print detail
			#sys.exit(1)

		changes = self.checkDependencies(changes, cache)
		cant = len(changes)

		if cant == 0:
			gtk.gdk.threads_enter()
			self.statusIcon.set_from_file(newUpdates)
			self.statusIcon.set_tooltip(_('You have %d update available') % cant)
			gtk.gdk.threads_leave()
		elif cant > 1:
			gtk.gdk.threads_enter()
			self.statusIcon.set_from_file(newUpdates)
			self.statusIcon.set_tooltip(_('You have %d updates available') % cant)
			gtk.gdk.threads_leave()
		else:
			gtk.gdk.threads_enter()
			self.statusIcon.set_from_file(updated)
			self.statusIcon.set_tooltip(_('Your system is up to date!'))
			gtk.gdk.threads_leave()

		level = 3 # Level 3 by default
		extraInfo = ''
		warning = ''
		rulesFile = open(os.path.join(APP_PATH, 'rules'), 'r')
		rules = rulesFile.readlines()
		goOn = True
		foundPackageRule = False # whether we found a rule with the exact package name or not
		html = ''
		totalSize = 0
		for pkg in changes:
			package = pkg.name
			newVersion = pkg.candidateVersion
			oldVersion = pkg.installedVersion
			size = pkg.packageSize
			description = pkg.description
			totalSize +=  size

			for rule in rules:
				if (goOn == True):
					rule_fields = rule.split('|')
					if len(rule_fields) == 5:
						rule_package = rule_fields[0]
						rule_version = rule_fields[1]
						rule_level = rule_fields[2]
						rule_extraInfo = rule_fields[3]
						rule_warning = rule_fields[4]
						if rule_package == package:
							foundPackageRule = True
							level = rule_level
							extraInfo = rule_extraInfo
							warning = rule_warning
							if rule_version == newVersion:
								goOn = False # We found a rule with the exact package name and version, no need to look elsewhere
						else:
							if rule_package.startswith('*'):
								keyword = rule_package.replace('*', '')
								index = package.find(keyword)
								if (index > -1 and foundPackageRule == False):
									level = rule_level
									extraInfo = rule_extraInfo
									warning = rule_warning

			html = html + '<li class="check level%s" level="%s" size="%d" name="%s"><a>%s</a><div id="data" class="hidden"><u><b>%s</b></u>: %s<br><u><b>%s</b></u>: %s<br><u><b>%s</b></u>: %s<br><u><b>%s</b></u>: %s<br><u><b>%s</b></u>: %s<br></div></li>\n' % (str(level), str(level), size, str(package), str(package), _('Description'), description, _('Safety level'), str(level), _('Size'), self.convert(int(size)), _('Installed version'), oldVersion, _('New Version'), newVersion)
		rulesFile.close()
		ready = True
		if self.synaptic:
			showWindow = True
			gtk.gdk.threads_enter()
			self.window.show_all()
			gtk.gdk.threads_leave()

class InstallThread(threading.Thread):
	def __init__(self, statusIcon, window, packages):
		threading.Thread.__init__(self)
		self.statusIcon = statusIcon
		self.window = window
		self.packages = packages

	def run(self):
		global log
		try:
			log.writelines('++ Install requested by user\n')
			log.flush()
			history = open(os.path.join(home, '.tuquito/tuquito-update/history'), 'a')

			gtk.gdk.threads_enter()
			self.statusIcon.set_from_file(busy)
			self.statusIcon.set_tooltip(_('Installing updates'))
			gtk.gdk.threads_leave()

			log.writelines('++ Ready to launch synaptic\n')
			log.flush()
			cmd = ['gksu', '"/usr/sbin/synaptic', '--hide-main-window', '--non-interactive']
			cmd.append('--progress-str')
			cmd.append('"' + _('Please wait, this can take some time') + '"')
			cmd.append('--finish-str')
			cmd.append('"' + _('Update is complete') + '"')

			f = tempfile.NamedTemporaryFile()
			if f:
				print "se creo el archivo"
			time.sleep(100)

			for pkg in self.packages:
				f.write("%s\tinstall\n" % pkg)
				history.write(commands.getoutput('date +"%d %b %Y %H:%M:%S"') + "\t" + pkg + "\n")
				log.writelines('++ Will install ' + str(pkg) + '\n')
				log.flush()

			cmd.append('--set-selections-file')
			cmd.append('%s' % f.name)
			cmd.append('" -D "%s"' % _('Tuquito Update'))
			f.flush()
			history.close()
			#comnd = Popen(' '.join(cmd), stdout=log, stderr=log, shell=True)
			f.close()
			print ' '.join(cmd)
			#returnCode = comnd.wait()
			#log.writelines('++ Return code:' + str(returnCode) + '\n')
			#sts = os.waitpid(comnd.pid, 0)
			log.writelines('++ Install finished\n')
			log.flush()

			gtk.gdk.threads_enter()
			self.statusIcon.set_tooltip(_('Checking for updates'))
			gtk.gdk.threads_leave()

			refresh = RefreshThread(self.statusIcon, self.window, True)
			refresh.start()

		except Exception, detail:
			log.writelines('-- Exception occured in the install thread: ' + str(detail) + '\n')
			log.flush()
			gtk.gdk.threads_enter()
			self.statusIcon.set_from_file(error)
			self.statusIcon.set_tooltip(_('Could not install the security updates'))
			log.writelines('-- Could not install security updates\n')
			log.flush()
			gtk.gdk.threads_leave()

class UpdateManager:
	def submenu(self, widget, button, time, data=None):
		if button == 3:
			if data:
				data.show_all()
				data.popup(None, None, None, 3, time)

	def convert(self, size):
		strSize = str(size) + _('B')
		if (size >= 1000):
			strSize = str(size / 1000) + _('KB')
		if (size >= 1000000):
			strSize = str(size / 1000000) + _('MB')
		if (size >= 1000000000):
			strSize = str(size / 1000000000) + _('GB')
		return strSize

	def onActivate(self, widget, data=None):
		global showWindow, ready
		if ready:
			if showWindow:
				self.hide(self)
			else:
				showWindow = True
				global html, totalSize, cant
				self.browser = webkit.WebView()
				self.scrolled.add(self.browser)
				self.browser.connect('button-press-event', lambda w, e: e.button == 3)
				text = {}

				strSize = self.convert(totalSize)

				text['kb'] = _('KB')
				text['mb'] = _('MB')
				text['gb'] = _('GB')
				text['size'] = totalSize

				text['selectAll'] = _('Select all')
				text['clear'] = _('Clear')
				text['install'] = _('Install')
				text['refresh'] = _('Refresh')

				text['header'] = _('<strong>Los siguientes paquetes están disponibles para su actualización.</strong><br><small>You have <strong>%d</strong> packages to update.<br>Download size: <strong id="size">%s</strong></small>') % (cant, strSize)
				text['list'] = html

				template = open('/usr/lib/tuquito/tuquito-update/frontend/index.html').read()
				html = string.Template(template).safe_substitute(text)
				self.browser.load_html_string(html, 'file:/')
				self.browser.connect('title-changed', self._on_title_changed)
				self.window.show_all()

	def _on_title_changed(self, view, frame, title):
		""" no op - needed to reset the title after a action so that the action can be triggered again """
		if title.startswith('nop'):
			return
		""" call directclass InstallThread(threading.Thread):
		"call:func:arg1,arg2"
		"call:func" """
		if title.startswith('call:'):
			argsStr = ''
			argsList = []
			""" try long form (with arguments) first """
			try:
				(t,funcname,argsStr) = title.split(':')
			except ValueError:
				""" now try short (without arguments) """
				(t,funcname) = title.split(':')
			if argsStr:
				argsList = argsStr.split(',')
			""" see if we have it and if it can be called """
			f = getattr(self, funcname)
			if f and callable(f):
				f(*argsList)
			""" now we need to reset the title """
			self.browser.execute_script('document.title = "nop"')

	def about(self, widget, data=None):
		os.system('/usr/lib/tuquito/tuquito-update/about.py &')

	def hide(self, widget, data=None):
		global showWindow
		showWindow = False
		self.window.hide_all()
		return True

	def quit(self, widget, data=None):
		gtk.main_quit()

	def refresh(self, widget=None, data=None):
		ready = False
		if showWindow:
			self.hide(self)
			synaptic = True
		else:
			synaptic = False
		refresh = RefreshThread(self.statusIcon, self.window, synaptic)
		refresh.start()

	def getPackages(self, package):
		self.packages.append(package)

	def install(self):
		self.hide(self)
		install = InstallThread(self.statusIcon, self.window, self.packages)
		install.start()
		self.packages = []

	def __init__(self):
		self.glade = gtk.Builder()
		self.glade.add_from_file('/usr/lib/tuquito/tuquito-update/update-manager.glade')
		self.window = self.glade.get_object('window')
		self.window.set_title(_('Tuquito Update'))
		self.statusIcon = self.glade.get_object('statusicon')
		self.scrolled = self.glade.get_object('scrolled')

		menu = self.glade.get_object('menu')
		self.glade.connect_signals(self)

		self.packages = []

		menuItem=gtk.ImageMenuItem(gtk.STOCK_REFRESH)
		menuItem.connect('activate', self.refresh)
		menu.append(menuItem)

		menuItem=gtk.ImageMenuItem(gtk.STOCK_PREFERENCES)
		#menuItem.connect('activate', self.openURL)
		menu.append(menuItem)

		menuItem = gtk.ImageMenuItem(gtk.STOCK_ABOUT)
		menuItem.connect('activate', self.about)
		menu.append(menuItem)

		separator = gtk.SeparatorMenuItem()
		menu.append(separator)

		menuItem = gtk.ImageMenuItem(gtk.STOCK_QUIT)
		menuItem.connect('activate', self.quit, self.statusIcon)
		menu.append(menuItem)

		self.statusIcon.set_tooltip(_('Connecting...'))
		self.statusIcon.connect('popup_menu', self.submenu, menu)

		self.refresh(self)

if __name__ == '__main__':
	gtk.gdk.threads_init()
	logdir = '/tmp/tuquito-update/'
	if os.getuid() == 0:
		mode = 'root'
	else:
		mode = 'user'
	os.system('mkdir -p ' + logdir)

	if not os.path.exists(os.path.join(home, '.tuquito/tuquito-update/')):
		os.system('mkdir -p ' + os.path.join(home, '.tuquito/tuquito-update/'))

	log = tempfile.NamedTemporaryFile(prefix=logdir, delete=False)
	logFile = log.name
	log.writelines(_('++ Launching Tuquito Update in %s mode\n') % mode)
	log.flush()
	UpdateManager()
	gtk.main()
