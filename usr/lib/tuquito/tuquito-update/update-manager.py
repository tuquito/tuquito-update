#!/usr/bin/python
# -*- coding: UTF-8 -*-

"""
 Tuquito Update Manager 0.7
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
import sys
import gtk
import threading
import tempfile
import gettext
import apt
from user import home
from subprocess import Popen, PIPE
import time
import ConfigParser

# i18n
gettext.install('tuquito-update', '/usr/share/tuquito/locale')

gtk.gdk.threads_init()

class RefreshThread(threading.Thread):
	def __init__(self, synaptic, glade=None):
		threading.Thread.__init__(self)
		self.synaptic  = synaptic
		self.glade = glade
		self.window = self.glade.get_object('window')
		self.statusIcon = self.glade.get_object('statusicon')

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
		global log, showWindow, ready, cant, totalSize
		global updated, newUpdates, errorConnecting
		global httpProxy, ftpProxy, gopherProxy
		global httpProxyPort, ftpProxyPort, gopherProxyPort

		proxy={}
		if checkEnableProxy == 'True':
			if httpProxy != '' and httpProxyPort != '':
				proxy['http'] = httpProxy + ':' + httpProxyPort
			if ftpProxy != '' and ftpProxyPort != '':
				proxy['ftp'] = ftpProxy + ':' + ftpProxyPort
			if gopherProxy != '' and gopherProxyPort != '':
				proxy['gopher'] = gopherProxy + ':' + gopherProxyPort
		else:
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
		self.statusIcon.set_tooltip(_('Checking for updates...'))
		gtk.gdk.threads_leave()

		try:
			if os.getuid() == 0 :
				if self.synaptic or showWindow:
					from subprocess import Popen, PIPE
					cmd = 'gksu "/usr/sbin/synaptic --hide-main-window --update-at-startup --non-interactive" -D "%s"' % _('Tuquito Update')
					comnd = Popen(cmd, shell=True)
					returnCode = comnd.wait()
				else:
					cache = apt.Cache()
					cache.update()
			cache = apt.Cache()
			cache.upgrade(bool(distUpgrade))
			changes = cache.getChanges()
		except Exception, detail:
			print detail
			sys.exit(1)

		changes = self.checkDependencies(changes, cache)
		cant = len(changes)

		if cant == 1:
			gtk.gdk.threads_enter()
			self.statusIcon.set_from_file(newUpdates)
			self.statusIcon.set_tooltip(_('You have 1 update available'))
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
		rulesFile.close()
		goOn = True
		foundPackageRule = False # whether we found a rule with the exact package name or not
		totalSize = 0
		model = gtk.TreeStore(str, str, gtk.gdk.Pixbuf, str, int, str, str, str, int)
		for pkg in changes:
			package = pkg.name
			newVersion = pkg.candidateVersion
			oldVersion = pkg.installedVersion
			size = pkg.packageSize
			description = pkg.description
			totalSize +=  size

			for rule in rules:
				if goOn:
					ruleFields = rule.split('|')
					if len(ruleFields) == 5:
						rule_package = ruleFields[0]
						rule_version = ruleFields[1]
						rule_level = ruleFields[2]
						rule_extraInfo = ruleFields[3]
						rule_warning = ruleFields[4]
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

			data = '<b>%s</b>: %s\n<b>%s</b>: %s\n<b>%s</b>: %s\n<b>%s</b>: %s' % (_('Description'), description, _('Size'), convert(size), _('Installed Version'), oldVersion, _('New Version'), newVersion)

			iter = model.insert_before(None, None)
			model.set_value(iter, 0, 'true')
			model.set_value(iter, 4, int(level))
			model.set_value(iter, 5, data)
			model.set_value(iter, 6, oldVersion)
			model.set_value(iter, 7, newVersion)
			model.set_value(iter, 8, size)
			model.set_value(iter, 1, str(package))
			model.row_changed(model.get_path(iter), iter)
			model.set_value(iter, 2, gtk.gdk.pixbuf_new_from_file(APP_PATH + 'icons/' + str(level) + '.png'))
			model.set_value(iter, 3, convert(size))

		gtk.gdk.threads_enter()
		treeviewUpdate.set_model(model)
		del model
		self.glade.get_object('header').set_markup(_('<big><b>You have %d packages to update</b></big>') % cant)
		self.glade.get_object('pkgSelected').set_markup(_('Packages selected: <b>%d</b>') % cant)
		self.glade.get_object('totalSize').set_markup(_('Download size: <b>%s</b>') % convert(totalSize))
		gtk.gdk.threads_leave()
		ready = True
		if self.synaptic:
			showWindow = True
			gtk.gdk.threads_enter()
			self.window.show()
			gtk.gdk.threads_leave()

class InstallThread(threading.Thread):
	def __init__(self, treeView, glade):
		threading.Thread.__init__(self)
		self.treeView = treeView
		self.glade = glade
		self.statusIcon = self.glade.get_object('statusicon')

	def run(self):
		global busy, error
		global log
		try:
			log.writelines('++ Install requested by user\n')
			log.flush()
			gtk.gdk.threads_enter()
			self.glade.get_object('window').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
			self.glade.get_object('window').set_sensitive(False)
			installNeeded = False
			packages = []
			model = self.treeView.get_model()
			gtk.gdk.threads_leave()

			iter = model.get_iter_first()
			while iter != None:
				checked = model.get_value(iter, 0)
				if checked == 'true':
					installNeeded = True
					package = model.get_value(iter, 1)
					level = model.get_value(iter, 4)
					oldVersion = model.get_value(iter, 6)
					newVersion = model.get_value(iter, 7)
					packages.append(package)
					log.writelines('++ Will install ' + str(package) + '\n')
					log.flush()
				iter = model.iter_next(iter)

			if installNeeded:
				gtk.gdk.threads_enter()
				self.statusIcon.set_from_file(busy)
				self.statusIcon.set_tooltip(_('Installing updates'))
				gtk.gdk.threads_leave()

				log.writelines('++ Ready to launch synaptic\n')
				log.flush()
				cmd = ['sudo', '/usr/sbin/synaptic', '--hide-main-window', '--non-interactive']
				cmd.append('--progress-str')
        			cmd.append('"' + _('Please wait, this can take some time') + '"')
				cmd.append('--finish-str')
				cmd.append('"' + _('Update is complete') + '"')
				f = tempfile.NamedTemporaryFile()

				for pkg in packages:
        			    f.write('%s\tinstall\n' % pkg)
        			cmd.append('--set-selections-file')
        			cmd.append('%s' % f.name)
        			f.flush()
        			comnd = Popen(' '.join(cmd), stdout=log, stderr=log, shell=True)
				returnCode = comnd.wait()
				log.writelines('++ Return code: ' + str(returnCode) + '\n')
			        #sts = os.waitpid(comnd.pid, 0)
        			f.close()
				log.writelines('++ Install finished\n')
				log.flush()

				gtk.gdk.threads_enter()
				self.statusIcon.set_from_file(busy)
				self.statusIcon.set_tooltip(_('Checking for updates...'))
				self.glade.get_object('window').window.set_cursor(None)
				self.glade.get_object('window').set_sensitive(True)
				global showWindow
				showWindow = False
				self.glade.get_object('window').hide()
				gtk.gdk.threads_leave()

				refresh = RefreshThread(self.treeView, self.glade)
				refresh.start()
			else:
				gtk.gdk.threads_enter()
				self.glade.get_object('window').window.set_cursor(None)
				self.glade.get_object('window').set_sensitive(True)
				gtk.gdk.threads_leave()
		except Exception, detail:
			log.writelines('-- Exception occured in the install thread: ' + str(detail) + '\n')
			log.flush()
			gtk.gdk.threads_enter()
			self.statusIcon.set_from_file(error)
			self.statusIcon.set_tooltip(_('Could not install the security updates'))
			log.writelines('-- Could not install security updates\n')
			log.flush()
			self.glade.get_object('window').window.set_cursor(None)
			self.glade.get_object('window').set_sensitive(True)
			gtk.gdk.threads_leave()

def convert(size):
	strSize = str(size) + _('B')
	if (size >= 1000):
		strSize = str(size / 1000) + _('KB')
	if (size >= 1000000):
		strSize = str(size / 1000000) + _('MB')
	if (size >= 1000000000):
		strSize = str(size / 1000000000) + _('GB')
	return strSize

def celldatafunctionCheckbox(column, cell, model, iter):
        cell.set_property('activatable', True)
	checked = model.get_value(iter, 0)
	if checked == 'true':
		cell.set_property('active', True)
	else:
		cell.set_property('active', False)

def toggled(renderer, path, treeview):
	global cant, totalSize
	model = treeview.get_model()
	iter = model.get_iter(path)
	if iter != None:
		checked = model.get_value(iter, 0)
		sizes = model.get_value(iter, 8)
		if checked == 'true':
			model.set_value(iter, 0, 'false')
			cant -= 1
			totalSize -= sizes
		else:
			model.set_value(iter, 0, 'true')
			cant += 1
			totalSize += sizes
	glade.get_object('pkgSelected').set_markup(_('Packages selected: <b>%d</b>') % cant)
	glade.get_object('totalSize').set_markup(_('Download size: <b>%s</b>') % convert(totalSize))

def displaySelectedPackage(selection):
	glade.get_object('expander').set_sensitive(True)
	(model, iter) = selection.get_selected()
	if iter != None:
		dataPackage = model.get_value(iter, 5)
		dataLabel.set_markup(str(dataPackage))

def submenu(widget, button, time, data=None):
	if button == 3:
		if data:
			data.show_all()
			data.popup(None, None, None, 3, time)

def onActivate(widget):
	global showWindow
	if ready:
		if showWindow:
			showWindow = False
			window.hide_all()
			return True
		else:
			if os.getuid() != 0:
				try:
					log.writelines('++ Launching Tuquito Update in root mode, waiting for it to kill us...\n')
					log.flush()
					log.close()
				except:
					pass #cause we might have closed it already
				os.system('gksu ' + APP_PATH + 'update-manager.py show ' + str(pid) + ' -D "' + _('Tuquito Update') + '" &')
			else:
				showWindow = True
				window.show_all()

def refresh(widget, data=False):
	ready = False
	showWindow = False
	window.hide()
	statusIcon.set_from_file(busy)
	if os.getuid() == 0 :
		refresh = RefreshThread(True, glade)
	else:
		refresh = RefreshThread(False, glade)
	refresh.start()

def install(widget, treeView, glade):
	install = InstallThread(treeView, glade)
	install.start()

def openRepo(widget):
	if os.path.exists('/usr/bin/software-properties-gtk'):
		os.system('gksu /usr/bin/software-properties-gtk -D "%s" &' % _('Software sources'))
	elif os.path.exists('/usr/bin/software-properties-kde'):
		os.system('gksu /usr/bin/software-properties-kde -D "%s" &' % _('Software sources'))

def about(widget):
	os.system('/usr/lib/tuquito/tuquito-update/about.py &')

def hide(widget, data=None):
	global showWindow
	showWindow = False
	window.hide_all()
	return True

def quit(widget):
	gtk.main_quit()

def openPref(widget):
	windowPref = glade.get_object('windowPref')
	windowPref.set_title(_('Tuquito Update preferences'))
	glade.get_object('label2').set_label(_('Update Method'))
	glade.get_object('label3').set_label(_('Proxy'))
	glade.get_object('label4').set_label(_('Startup delay (in seconds): '))
	glade.get_object('label5').set_label(_('Internet check (domain name or IP address): '))
	glade.get_object('label6').set_label(_('<i>Note: Newer versions of packages can have different dependencies. If an upgrade requires the installation or the removal of another package it will be kept back and not upgraded. If you select this option however, it will be upgraded and all new dependencies will be resolved. Since this can result in the installation of new packages or the removal of some of your packages you should only use this option if you are experienced with APT.</i>'))
	glade.get_object('check_dist_upgrade').set_label(_('Include dist-upgrade packages?'))
	glade.get_object('enable_proxy').set_label(_('Manual proxy configuration'))
	glade.get_object('check_same_proxy').set_label(_('Use the same proxy for all protocols'))
	glade.get_object('label_http_proxy').set_label(_('HTTP Proxy:'))
	glade.get_object('label_ftp_proxy').set_label(_('FTP Proxy:'))
	glade.get_object('label_gopher_proxy').set_label(_('Gopher Proxy:'))
	glade.get_object('label_port1').set_label(_('Port:'))
	glade.get_object('label_port2').set_label(_('Port:'))
	glade.get_object('label_port3').set_label(_('Port:'))
	windowPref.connect('delete-event', hidePref)
	windowPref.connect('destroy-event', hidePref)
	glade.get_object('cancel').connect('clicked', hidePref)
	if os.path.exists('/usr/bin/software-properties-gtk') or os.path.exists('/usr/bin/software-properties-kde'):
		glade.get_object('labelSoftwareSources').set_label(_('Software sources'))
		glade.get_object('buttonSoftwareSources').connect('clicked', openRepo)
		glade.get_object('buttonSoftwareSources').show()
	else:
		glade.get_object('buttonSoftwareSources').hide()
	glade.get_object('enable_proxy').connect('toggled', enableProxy)
	glade.get_object('check_same_proxy').connect('toggled', setSameProxy)
	glade.get_object('save_pref').connect('clicked', savePref)
	glade.get_object('http_proxy').connect('changed', updateProxyHost)
	glade.get_object('http_proxy_port').connect('changed', updateProxyPort)
	glade.get_object('url_ping').set_text(urlPing)
	glade.get_object('spin_delay').set_value(float(delay))
	if distUpgrade == 'True':
		glade.get_object('check_dist_upgrade').set_active(True)
	else:
		glade.get_object('check_dist_upgrade').set_active(False)
	if checkEnableProxy == 'True':
		glade.get_object('enable_proxy').set_active(True)
		if checkSameProxy == 'True':
			glade.get_object('check_same_proxy').set_active(True)
		glade.get_object('http_proxy').set_text(httpProxy)
		glade.get_object('http_proxy_port').set_text(httpProxyPort)
		glade.get_object('ftp_proxy').set_text(ftpProxy)
		glade.get_object('ftp_proxy_port').set_text(ftpProxyPort)
		glade.get_object('gopher_proxy').set_text(gopherProxy)
		glade.get_object('gopher_proxy_port').set_text(gopherProxyPort)
	else:
		glade.get_object('table1').set_sensitive(False)
	windowPref.show()

def readPref(widget=None):
	global delay, urlPing, distUpgrade, checkEnableProxy, checkSameProxy
	global httpProxy, ftpProxy, gopherProxy
	global httpProxyPort, ftpProxyPort, gopherProxyPort
	global configFile
	config = ConfigParser.ConfigParser()
	configFile =  os.path.join(home, '.tuquito/tuquito-update/tuquito-update.conf')
	if os.path.exists(configFile):
		config.read(configFile)
	else:
		config.read('/etc/tuquito/tuquito-update.conf')
	try:
		delay = config.get('User settings', 'delay')
		urlPing = config.get('User settings', 'url')
		distUpgrade = config.get('User settings', 'distUpgrade')
	except:
		delay = 30
		urlPing = 'google.com'
		distUpgrade = True
	try:
		checkEnableProxy = config.get('User settings', 'manualProxy')
		checkSameProxy = config.get('User settings', 'checkSameProxy')
		httpProxy = config.get('User settings', 'httpProxy')
		ftpProxy = config.get('User settings', 'ftpProxy')
		gopherProxy = config.get('User settings', 'gopherProxy')
		httpProxyPort = config.get('User settings', 'httpProxyPort')
		ftpProxyPort = config.get('User settings', 'ftpProxyPort')
		gopherProxyPort = config.get('User settings', 'gopherProxyPort')
	except:
		checkEnableProxy = False
		checkSameProxy = False
		httpProxy = ''
		ftpProxy = ''
		gopherProxy = ''
		httpProxyPort = ''
		ftpProxyPort = ''
		gopherProxyPort = ''

def savePref(widget):
	global checkEnableProxy
	config = ConfigParser.ConfigParser()
	config.add_section('User settings')
	spinDelay = glade.get_object('spin_delay').get_value_as_int()
	urlPing = glade.get_object('url_ping').get_text().strip()
	distUpgrade = glade.get_object('check_dist_upgrade').get_active()
	checkEnableProxy = glade.get_object('enable_proxy').get_active()
	config.set('User settings', 'delay', spinDelay)
	config.set('User settings', 'url', urlPing)
	config.set('User settings', 'distUpgrade', distUpgrade)
	config.set('User settings', 'manualProxy', checkEnableProxy)
	if checkEnableProxy:
		httpProxy = glade.get_object('http_proxy').get_text().strip()
		ftpProxy = glade.get_object('ftp_proxy').get_text().strip()
		gopherProxy = glade.get_object('gopher_proxy').get_text().strip()
		port1 = glade.get_object('http_proxy_port').get_text().strip()
		port2 = glade.get_object('ftp_proxy_port').get_text().strip()
		port3 = glade.get_object('gopher_proxy_port').get_text().strip()
		config.set('User settings', 'checkSameProxy', checkSameProxy)
		config.set('User settings', 'httpProxy', httpProxy)
		config.set('User settings', 'ftpProxy', ftpProxy)
		config.set('User settings', 'gopherProxy', gopherProxy)
		config.set('User settings', 'httpProxyPort', port1)
		config.set('User settings', 'ftpProxyPort', port2)
		config.set('User settings', 'gopherProxyPort', port3)
	config.write(open(configFile, 'w'))
	readPref()
	hidePref()

def setSameProxy(widget):
	if glade.get_object('check_same_proxy').get_active():
		glade.get_object('ftp_proxy').set_text(glade.get_object('http_proxy').get_text())
		glade.get_object('ftp_proxy_port').set_text(glade.get_object('http_proxy_port').get_text())
		glade.get_object('gopher_proxy').set_text(glade.get_object('http_proxy').get_text())
		glade.get_object('gopher_proxy_port').set_text(glade.get_object('http_proxy_port').get_text())
		glade.get_object('ftp_proxy').set_sensitive(False)
		glade.get_object('ftp_proxy_port').set_sensitive(False)
		glade.get_object('gopher_proxy').set_sensitive(False)
		glade.get_object('gopher_proxy_port').set_sensitive(False)
	else:
		glade.get_object('ftp_proxy').set_sensitive(True)
		glade.get_object('ftp_proxy_port').set_sensitive(True)
		glade.get_object('gopher_proxy').set_sensitive(True)
		glade.get_object('gopher_proxy_port').set_sensitive(True)

def enableProxy(widget):
	global checkEnableProxy
	checkEnableProxy = glade.get_object('enable_proxy').get_active()
	if checkEnableProxy:
		glade.get_object('table1').set_sensitive(True)
	else:
		glade.get_object('table1').set_sensitive(False)

def updateProxyHost(widget):
	if glade.get_object('check_same_proxy').get_active():
		glade.get_object('ftp_proxy').set_text(widget.get_text())
		glade.get_object('gopher_proxy').set_text(widget.get_text())

def updateProxyPort(widget):
	if glade.get_object('check_same_proxy').get_active():
		glade.get_object('ftp_proxy_port').set_text(widget.get_text())
		glade.get_object('gopher_proxy_port').set_text(widget.get_text())

def hidePref(widget=None, data=None):
	glade.get_object('windowPref').hide()
	return True

readPref()

try:
	arg = sys.argv[1].strip()
except Exception, d:
	arg = False

if arg == 'time':
	time.sleep(delay)


# Flags
ready = False
showWindow  = False

parentPid = '0'
APP_PATH = '/usr/lib/tuquito/tuquito-update/'

if len(sys.argv) > 2:
	parentPid = sys.argv[2]
	if parentPid != '0':
		os.system('kill -9 ' + parentPid)

pid = os.getpid()
logdir = '/tmp/tuquito-update/'

if os.getuid() == 0 :
	mode = 'root'
else:
	mode = 'user'

os.system('mkdir -p ' + logdir)
log = tempfile.NamedTemporaryFile(prefix = logdir, delete=False)
logFile = log.name

log.writelines('++ Launching Tuquito Update in ' + mode + ' mode\n')
log.flush()

try:
	global updated, busy, errorConnecting, error, newUpdates, newUpgrade
	updated = os.path.join(APP_PATH, 'icons/updated.png')
	busy = os.path.join(APP_PATH, 'icons/busy.png')
	error = os.path.join(APP_PATH, 'icons/error.png')
	errorConnecting = os.path.join(APP_PATH, 'icons/errorConnecting.png')
	newUpdates = os.path.join(APP_PATH, 'icons/newUpdates.png')
	newUpgrade = os.path.join(APP_PATH, 'icons/newUpgrade.png')

	glade = gtk.Builder()
	glade.add_from_file('/usr/lib/tuquito/tuquito-update/update-manager.glade')
	window = glade.get_object('window')
	window.set_title(_('Update Manager'))
	dataLabel = glade.get_object('data')
	treeviewUpdate = glade.get_object('treeview')
	statusIcon = glade.get_object('statusicon')
	glade.get_object('expanderLabel').set_label(_('Description of package'))

	glade.get_object('preference').connect('clicked', openPref)
	glade.get_object('refresh').connect('clicked', refresh, True)
	glade.get_object('apply').connect('clicked', install, treeviewUpdate, glade)

	menu = glade.get_object('menu')
	window.connect('delete-event', hide)
	window.connect('destroy-event', hide)

	menuItem=gtk.ImageMenuItem(gtk.STOCK_REFRESH)
	menuItem.connect('activate', refresh)
	menu.append(menuItem)

	menuItem=gtk.ImageMenuItem(gtk.STOCK_PREFERENCES)
	menuItem.connect('activate', openPref)
	menu.append(menuItem)

	if os.path.exists('/usr/bin/software-properties-gtk') or os.path.exists('/usr/bin/software-properties-kde'):
		menuItem=gtk.ImageMenuItem(_('Software sources'))
		menuItem.set_image(gtk.image_new_from_file(os.path.join(APP_PATH, '/icons/software-properties.png')))
		menuItem.connect('activate', openRepo)
		menu.append(menuItem)

	menuItem = gtk.ImageMenuItem(gtk.STOCK_ABOUT)
	menuItem.connect('activate', about)
	menu.append(menuItem)

	separator = gtk.SeparatorMenuItem()
	menu.append(separator)

	menuItem = gtk.ImageMenuItem(gtk.STOCK_QUIT)
	menuItem.connect('activate', quit)
	menu.append(menuItem)

	statusIcon.set_tooltip(_('Connecting...'))
	statusIcon.set_from_file(busy)
	statusIcon.connect('popup-menu', submenu, menu)
	statusIcon.connect('activate', onActivate)

	cr = gtk.CellRendererToggle()
	cr.connect('toggled', toggled, treeviewUpdate)

	column1 = gtk.TreeViewColumn(_('Upgrade'), cr)
	column1.set_cell_data_func(cr, celldatafunctionCheckbox)
	column1.set_sort_column_id(2)
	column1.set_resizable(True)

	column2 = gtk.TreeViewColumn(_('Package'), gtk.CellRendererText(), text=1)
	column2.set_sort_column_id(1)
	column2.set_resizable(True)

	column3 = gtk.TreeViewColumn(_('Level'), gtk.CellRendererPixbuf(), pixbuf=2)
	column3.set_sort_column_id(4)
	column3.set_resizable(True)

	column6 = gtk.TreeViewColumn(_('Size'), gtk.CellRendererText(), text=3)
	column6.set_sort_column_id(8)
	column6.set_resizable(True)

	treeviewUpdate.append_column(column3)
	treeviewUpdate.append_column(column1)
	treeviewUpdate.append_column(column2)
	treeviewUpdate.append_column(column6)

	selection = treeviewUpdate.get_selection()
	selection.connect('changed', displaySelectedPackage)

	if len(sys.argv) > 1 and sys.argv[1] == 'show':
		showWindow = True
		refresh = RefreshThread(True, glade)
	else:
		refresh = RefreshThread(False, glade)
	refresh.start()
	gtk.main()
except Exception, detail:
	print detail
	log.writelines('-- Exception occured in main thread: ' + str(detail) + '\n')
	log.flush()
	log.close()

