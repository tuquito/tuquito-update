#!/usr/bin/python
# -*- coding: UTF-8 -*-

"""
 Tuquito Update Manager
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
from subprocess import Popen, PIPE
import time
import ConfigParser
import pynotify

if not pynotify.init ('Update-Manager'):
    sys.exit(1)

#globals
APP_PATH = '/usr/lib/tuquito/tuquito-update/'
logdir = '/tmp/tuquito-update/'
uid = os.getuid()
notifyStatus = True

# i18n
gettext.install('tuquito-update', '/usr/share/tuquito/locale')

architecture = commands.getoutput('uname -a')
if architecture.find('x86_64') >= 0:
    import ctypes
    libc = ctypes.CDLL('libc.so.6')
    libc.prctl(15, 'updateManager', 0, 0, 0)
else:
    import dl
    if os.path.exists('/lib/libc.so.6'):
        libc = dl.open('/lib/libc.so.6')
        libc.call('prctl', 15, 'updateManager', 0, 0, 0)
    elif os.path.exists('/lib/i386-linux-gnu/libc.so.6'):
        libc = dl.open('/lib/i386-linux-gnu/libc.so.6')
        libc.call('prctl', 15, 'updateManager', 0, 0, 0)

gtk.gdk.threads_init()

class RefreshThread(threading.Thread):
    def __init__(self, synaptic, glade=None, auto=True):
        threading.Thread.__init__(self)
        self.synaptic  = synaptic
        self.glade = glade
        self.window = self.glade.get_object('window')
        self.statusIcon = self.glade.get_object('statusicon')
        self.auto = auto

    def checkDependencies(self, changes, cache):
        foundSomething = False
        for pkg in changes:
            for dep in pkg.versions[0].dependencies:
                for o in dep.or_dependencies:
                    try:
                        if cache[o.name].is_upgradable:
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
            changes = self.checkDependencies(changes, cache)
        return changes

    def run(self):
        global log, showWindow, ready, cant, totalSize
        ready = False
        proxy={}
        if checkEnableProxy:
            if httpProxy != '' and httpProxyPort != '':
                proxy['http'] = httpProxy + ':' + httpProxyPort
            if ftpProxy != '' and ftpProxyPort != '':
                proxy['ftp'] = ftpProxy + ':' + ftpProxyPort
            if gopherProxy != '' and gopherProxyPort != '':
                proxy['gopher'] = gopherProxy + ':' + gopherProxyPort
        else:
            proxy = None
        gtk.gdk.threads_enter()
        self.statusIcon.set_visible(showIcon)
        self.statusIcon.set_tooltip(_('Checking connection...'))
        gtk.gdk.threads_leave()
        try:
            from urllib import urlopen
            url = urlopen('http://google.com', None, proxy)
            url.read()
            url.close()
        except Exception, detail:
            if os.system('ping ' + urlPing + ' -c1 -q'):
                gtk.gdk.threads_enter()
                self.statusIcon.set_from_file(errorConnecting)
                self.statusIcon.set_tooltip(_('Could not connect to the Internet'))
                try:
                    log.writelines('-- No connection found (tried to read http://google.com and to ' + urlPing + ')\n')
                    log.flush()
                except:
                    pass
                gtk.gdk.threads_leave()
                autoRefresh = AutomaticRefreshThread(self.glade, False)
                autoRefresh.start()
                return False
            else:
                try:
                    log.writelines('++ Connection found - checking for updates\n')
                    log.flush()
                except:
                    pass
        gtk.gdk.threads_enter()
        self.statusIcon.set_tooltip(_('Checking for updates...'))
        gtk.gdk.threads_leave()
        try:
            if uid == 0 :
                if self.synaptic or showWindow:
                    from subprocess import Popen, PIPE
                    cmd = 'gksu "/usr/sbin/synaptic --hide-main-window --update-at-startup --non-interactive" -D /usr/share/applications/synaptic.desktop'
                    comnd = Popen(cmd, shell=True)
                    comnd.wait()
                else:
                    cache = apt.Cache()
                    cache.update()
            cache = apt.Cache()
            cache.upgrade(distUpgrade)
            changes = cache.get_changes()
        except Exception, detail:
            print detail
            sys.exit(1)
        changes = self.checkDependencies(changes, cache)
        cant = len(changes)
        if cant == 1:
            gtk.gdk.threads_enter()
            self.statusIcon.set_visible(True)
            self.statusIcon.set_from_file(newUpdates)
            self.statusIcon.set_tooltip(_('You have 1 update available'))
            gtk.gdk.threads_leave()
            if showNotification:
                notify(_('You have 1 update available'))
        elif cant > 1:
            gtk.gdk.threads_enter()
            self.statusIcon.set_visible(True)
            self.statusIcon.set_from_file(newUpdates)
            self.statusIcon.set_tooltip(_('You have %d updates available') % cant)
            gtk.gdk.threads_leave()
            if showNotification:
                notify(_('You have %d updates available') % cant)
        else:
            gtk.gdk.threads_enter()
            self.statusIcon.set_from_file(updated)
            self.statusIcon.set_tooltip(_('Your system is up to date!'))
            gtk.gdk.threads_leave()
        level = 3
        rulesFile = open(os.path.join(APP_PATH, 'rules'), 'r')
        rules = rulesFile.readlines()
        rulesFile.close()
        goOn = True
        totalSize = 0
        model = gtk.TreeStore(str, str, gtk.gdk.Pixbuf, str, int, str, str, str, int)
        for pkg in changes:
            foundPackageRule = False
            package = pkg.name
            newVersion = pkg.versions[0].version
            try:
                oldVersion = pkg.installed.version
            except:
                oldVersion = 'None'
            size = pkg.versions[0].size
            description = pkg.versions[0].description
            totalSize +=  size
            for rule in rules:
                if goOn:
                    ruleFields = rule.split('|')
                    if len(ruleFields) == 5:
                        rule_package = ruleFields[0]
                        rule_version = ruleFields[1]
                        rule_level = ruleFields[2]
                        if rule_package == package:
                            foundPackageRule = True
                            level = rule_level
                            if rule_version == newVersion:
                                goOn = False
                        else:
                            if rule_package.startswith('*'):
                                keyword = rule_package.replace('*', '')
                                index = package.find(keyword)
                                if (index > -1 and foundPackageRule == False):
                                    level = rule_level
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
        if self.glade.get_object('data').get_label() == '':
            self.glade.get_object('data').set_markup(_('<b>Select a package to see its information</b>'))
        gtk.gdk.threads_leave()
        if cant > 0:
            ready = True
            if self.synaptic and uid == 0:
                showWindow = True
                gtk.gdk.threads_enter()
                self.window.show()
                gtk.gdk.threads_leave()
        if self.auto and (not showWindow):
            autoRefresh = AutomaticRefreshThread(self.glade)
            autoRefresh.start()

class AutomaticRefreshThread(threading.Thread):
    def __init__(self, glade, connectStatus=True):
        threading.Thread.__init__(self)
        self.glade = glade
        self.connectStatus = connectStatus

    def run(self):
        global log
        try:
            if self.connectStatus:
                timer = (int(timerMin) * 60) + (int(timerHours) * 60 * 60) + (int(timerDays) * 24 * 60 * 60)
            else:
                timer = 60
            try:
                log.writelines('++ Auto-refresh timer is going to sleep for ' + str(timerMin) + ' minutes, ' + str(timerHours) + ' hours and ' + str(timerDays) + ' days\n')
                log.flush()
            except:
                pass
            if int(timer) > 0:
                time.sleep(int(timer))
                if showWindow:
                    try:
                        log.writelines('++ The Tuquito Update window is open, skipping auto-refresh\n')
                        log.flush()
                    except:
                        pass
                else:
                    try:
                        log.writelines('++ Tuquito Update is in tray mode, performing auto-refresh\n')
                        log.flush()
                    except:
                        pass
                    refresh = RefreshThread(False, self.glade)
                    refresh.start()
        except Exception, detail:
            try:
                log.writelines('-- Exception occured in the auto-refresh thread.. so it\'s probably dead now: ' + str(detail) + '\n')
                log.flush()
            except:
                pass

class InstallThread(threading.Thread):
    def __init__(self, treeView, glade):
        threading.Thread.__init__(self)
        self.treeView = treeView
        self.glade = glade
        self.statusIcon = self.glade.get_object('statusicon')

    def run(self):
        global log
        global showWindow
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
                cmd = ['gksu', '\'/usr/sbin/synaptic', '--hide-main-window', '--non-interactive']
                cmd.append('--progress-str')
                cmd.append('"' + _('Please wait, this can take some time') + '"')
                cmd.append('--finish-str')
                cmd.append('"' + _('Update is complete') + '"')
                f = tempfile.NamedTemporaryFile()
                for pkg in packages:
                    f.write('%s\tinstall\n' % pkg)
                cmd.append('--set-selections-file')
                cmd.append('%s\'' % f.name)
                cmd.append('-D /usr/share/applications/synaptic.desktop')
                f.flush()
                comnd = Popen(' '.join(cmd), stdout=log, stderr=log, shell=True)
                returnCode = comnd.wait()
                log.writelines('++ Return code: ' + str(returnCode) + '\n')
                f.close()
                log.writelines('++ Install finished\n')
                log.flush()
                if 'tuquito-update' in packages:
                    # Restart
                    gtk.gdk.threads_enter()
                    showWindow = False
                    self.glade.get_object('window').hide()
                    gtk.gdk.threads_leave()
                    try:
                        log.writelines("++ Tuquito Update was updated, restarting it in root mode...\n")
                        log.flush()
                        log.close()
                    except:
                        pass #cause we might have closed it already
                    os.system('gksudo /usr/lib/tuquito/tuquito-update/update-manager.py show &')
                else:
                    # Refresh
                    gtk.gdk.threads_enter()
                    self.statusIcon.set_from_file(busy)
                    self.statusIcon.set_tooltip(_('Checking for updates...'))
                    self.glade.get_object('window').window.set_cursor(None)
                    self.glade.get_object('window').set_sensitive(True)
                    showWindow = False
                    self.glade.get_object('window').hide()
                    gtk.gdk.threads_leave()
                    refresh = RefreshThread(self.treeView, self.glade)
                    refresh.start()
            else:
                gtk.gdk.threads_enter()
                self.glade.get_object('window').window.set_cursor(None)
                self.glade.get_object('window').set_sensitive(True)
                showWindow = True
                self.glade.get_object('window').show()
                gtk.gdk.threads_leave()
        except Exception, detail:
            log.writelines('-- Exception occured in the install thread: ' + str(detail) + '\n')
            log.flush()
            gtk.gdk.threads_enter()
            self.statusIcon.set_visible(True)
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
            window.hide()
            return True
        else:
            if uid != 0:
                try:
                    log.writelines('++ Launching Tuquito Update in root mode, waiting for it to kill us...\n')
                    log.flush()
                    log.close()
                except:
                    pass
                os.system('gksu tuquito-update -D /usr/share/applications/tuquito-update.desktop &')
            else:
                showWindow = True
                window.show()

def refresh(widget, data=False):
    statusIcon.set_from_file(busy)
    statusIcon.set_visible(showIcon)
    if uid == 0 and showWindow:
        refresh = RefreshThread(True, glade, False)
    else:
        refresh = RefreshThread(False, glade, False)
    refresh.start()
    hide(widget)

def install(widget, treeView, glade):
    global advancedActive, showWindow
    if express or advancedActive:
        showWindow = False
        window.hide()
        install = InstallThread(treeView, glade)
        install.start()
    else:
        advancedActive = True
        glade.get_object('notebook').next_page()
        glade.get_object('pkgSelected').set_visible(True)

def openRepo(widget):
    if os.path.exists('/usr/bin/software-properties-gtk'):
        os.system('gksu /usr/bin/software-properties-gtk -D /usr/share/applications/software-properties-gtk.desktop &')
    elif os.path.exists('/usr/bin/software-properties-kde'):
        os.system('gksu /usr/bin/software-properties-kde -D /usr/share/applications/software-properties-kde.desktop &')

def about(widget):
    abt = glade.get_object('about')
    abt.connect('response', quitAbout)
    abt.connect('delete-event', quitAbout)
    abt.connect('destroy-event', quitAbout)
    abt.set_comments(_('Update Manager for Tuquito'))
    abt.show()

def quitAbout(widget, data=None):
    widget.hide()
    return True

def hide(widget, data=None):
    global showWindow
    showWindow = False
    window.hide()
    return True

def quit(widget):
    pid = os.getpid()
    os.system('kill -9 %d &' % pid)

def openPref(widget):
    windowPref = glade.get_object('windowPref')
    windowPref.set_title(_('Tuquito Update preferences'))
    glade.get_object('label1').set_label(_('Refresh the list of updates every:'))
    glade.get_object('label2').set_label(_('Auto Refresh'))
    glade.get_object('label3').set_label(_('minutes'))
    glade.get_object('label4').set_label(_('Startup delay (in seconds): '))
    glade.get_object('label5').set_label(_('Internet check (domain name or IP address): '))
    glade.get_object('label6').set_markup(_("<i>Note: The dist-upgrade option, in addition to performing the function of upgrade, also intelligently handles changing dependencies with new versions of packages. Without this option, only the latest versions of any out-of-date packages on your system are installed. Packages that are not yet installed don't get installed automatically and newer versions of packages which dependencies require such installations are simply ignored.</i>"))
    glade.get_object('label7').set_label(_('hours'))
    glade.get_object('label8').set_label(_('General'))
    glade.get_object('label9').set_label(_('Proxy'))
    glade.get_object('label10').set_label(_('days'))
    glade.get_object('label11').set_markup(_('<i>Note: The list only gets refreshed while the Tuquito Update window is closed (system tray mode).</i>'))
    glade.get_object('check_dist_upgrade').set_label(_('Include dist-upgrade packages?'))
    glade.get_object('check_auto_start').set_label(_('Auto start'))
    glade.get_object('check_show_icon').set_label(_('Show icon only when updates are available'))
    glade.get_object('check_notification').set_label(_('Show notifications when updates are available'))
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
    glade.get_object('spin_delay').set_value(delay)
    glade.get_object('timer_min').set_value(timerMin)
    glade.get_object('timer_hours').set_value(timerHours)
    glade.get_object('timer_days').set_value(timerDays)
    glade.get_object('check_dist_upgrade').set_active(distUpgrade)
    glade.get_object('check_auto_start').set_active(autoStart)
    glade.get_object('check_show_icon').set_active(not showIcon)
    glade.get_object('check_notification').set_active(showNotification)
    if checkEnableProxy:
        glade.get_object('enable_proxy').set_active(True)
        glade.get_object('check_same_proxy').set_active(checkSameProxy)
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
    global delay, urlPing, distUpgrade, checkEnableProxy, checkSameProxy, showIcon
    global timerMin, timerHours, timerDays
    global httpProxy, ftpProxy, gopherProxy
    global httpProxyPort, ftpProxyPort, gopherProxyPort
    global configFile, autoStart, home, showNotification
    config = ConfigParser.ConfigParser()
    if uid == 0 :
        home = '/home/' + os.environ.get('SUDO_USER')
    else:
        from user import home
    configDir = os.path.join(home, '.tuquito/tuquito-update')
    configFile =  os.path.join(configDir, 'tuquito-update.conf')
    if os.path.exists(configDir):
        if os.path.exists(configFile):
            config.read(configFile)
        else:
            config.read('/etc/tuquito/tuquito-update.conf')
    else:
        config.read('/etc/tuquito/tuquito-update.conf')
        os.system('mkdir -p ' + configDir)
    try:
        delay = config.getfloat('User settings', 'delay')
        urlPing = config.get('User settings', 'url')
        distUpgrade = config.getboolean('User settings', 'distUpgrade')
        autoStart = config.getboolean('User settings', 'autoStart')
        showIcon = config.getboolean('User settings', 'showIcon')
        showNotification = config.getboolean('User settings', 'showNotification')
    except:
        delay = 30
        urlPing = 'google.com'
        distUpgrade = True
        autoStart = True
        showIcon = False
        showNotification = True
    try:
        timerMin = config.getfloat('User settings', 'timerMin')
        timerHours = config.getfloat('User settings', 'timerHours')
        timerDays = config.getfloat('User settings', 'timerDays')
    except:
        timerMin = 30
        timerHours = 0
        timerDays = 0

    try:
        checkEnableProxy = config.getboolean('User settings', 'manualProxy')
        checkSameProxy = config.getboolean('User settings', 'checkSameProxy')
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
    autoStart = glade.get_object('check_auto_start').get_active()
    showIcon = not (glade.get_object('check_show_icon').get_active())
    showNotification = glade.get_object('check_notification').get_active()
    checkEnableProxy = glade.get_object('enable_proxy').get_active()
    timerMin = glade.get_object('timer_min').get_value_as_int()
    timerHours = glade.get_object('timer_hours').get_value_as_int()
    timerDays = glade.get_object('timer_days').get_value_as_int()
    config.set('User settings', 'delay', spinDelay)
    config.set('User settings', 'showIcon', showIcon)
    config.set('User settings', 'showNotification', showNotification)
    config.set('User settings', 'url', urlPing)
    config.set('User settings', 'distUpgrade', distUpgrade)
    config.set('User settings', 'autoStart', autoStart)
    config.set('User settings', 'manualProxy', checkEnableProxy)
    config.set('User settings', 'timerMin', timerMin)
    config.set('User settings', 'timerHours', timerHours)
    config.set('User settings', 'timerDays', timerDays)
    if checkEnableProxy:
        checkSameProxy = glade.get_object('check_same_proxy').get_active()
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
    if uid == 0:
        os.system('chown %s:%s %s' % (os.environ.get('SUDO_USER'), os.environ.get('SUDO_USER'), configFile))
        os.system('chmod 655 %s' % configFile)
    readPref()
    hidePref(widget)

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
    glade.get_object('table1').set_sensitive(checkEnableProxy)

def updateProxyHost(widget):
    if glade.get_object('check_same_proxy').get_active():
        glade.get_object('ftp_proxy').set_text(widget.get_text())
        glade.get_object('gopher_proxy').set_text(widget.get_text())

def updateProxyPort(widget):
    if glade.get_object('check_same_proxy').get_active():
        glade.get_object('ftp_proxy_port').set_text(widget.get_text())
        glade.get_object('gopher_proxy_port').set_text(widget.get_text())

def setModeExpress(widget, data=None):
    global express
    express = widget.get_active()

def hidePref(widget, data=None):
    glade.get_object('windowPref').hide()
    return True

def notify(text):
    global notifyStatus
    if showNotification and notifyStatus and uid != 0:
        n = pynotify.Notification(_('Update Manager'), text, newUpdates)
        n.show()
        notifyStatus = False

## Init
readPref()

if uid == 0:
    mode = 'root'
else:
    if not autoStart:
        sys.exit(0)
    mode = 'user'
    while not os.path.exists('/tmp/tuquito-update.tmp'):
        time.sleep(10)

# Flags
ready = False
showWindow  = False
advancedActive = False
express = True

if not os.path.exists(logdir):
    os.system('mkdir -p ' + logdir)

log = tempfile.NamedTemporaryFile(prefix=logdir, delete=False)
logFile = log.name
log.writelines('++ Launching Tuquito Update whith uid: ' + str(uid) + '\n')
log.flush()
log.writelines('++ Launching Tuquito Update in ' + mode + ' mode\n')
log.flush()

try:
    global updated, busy, errorConnecting, error, newUpdates
    updated = os.path.join(APP_PATH, 'icons/updated.png')
    busy = os.path.join(APP_PATH, 'icons/busy.png')
    error = os.path.join(APP_PATH, 'icons/error.png')
    errorConnecting = os.path.join(APP_PATH, 'icons/errorConnecting.png')
    newUpdates = os.path.join(APP_PATH, 'icons/newUpdates.png')

    glade = gtk.Builder()
    glade.add_from_file('/usr/lib/tuquito/tuquito-update/tuquito-update.glade')
    window = glade.get_object('window')
    window.set_title(_('Update Manager'))
    dataLabel = glade.get_object('data')
    treeviewUpdate = glade.get_object('treeview')
    statusIcon = glade.get_object('statusicon')
    glade.get_object('labelRefresh').set_label(_('Check'))
    glade.get_object('expanderLabel').set_label(_('Details of package'))
    glade.get_object('label12').set_label('<big><b>%s</b></big>' % _('How do you want to install updates?'))
    glade.get_object('radiobutton_recomendaded').set_label(_('Express install (Recomended)'))
    glade.get_object('label13').set_label(_('The easy way to update your computer. This will ensure that your computer is up to date with the latest software.'))
    glade.get_object('radiobutton_advanced').set_label(_('Custom install (Advanced)'))
    glade.get_object('label15').set_label(_('Select what you want to update manually. You will have more detailed information on the packages.'))
    glade.get_object('pkgSelected').set_visible(False)

    glade.get_object('preference').connect('clicked', openPref)
    glade.get_object('refresh').connect('clicked', refresh, True)
    glade.get_object('apply').connect('clicked', install, treeviewUpdate, glade)
    glade.get_object('radiobutton_recomendaded').connect('toggled', setModeExpress)

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
        menuItem.set_image(gtk.image_new_from_file(os.path.join(APP_PATH, 'icons/software-properties.png')))
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
    statusIcon.set_visible(showIcon)

    cellRender = gtk.CellRendererToggle()
    cellRender.connect('toggled', toggled, treeviewUpdate)
    column1 = gtk.TreeViewColumn(_('Level'), gtk.CellRendererPixbuf(), pixbuf=2)
    column1.set_sort_column_id(4)
    column1.set_resizable(True)
    column2 = gtk.TreeViewColumn(_('Upgrade'), cellRender)
    column2.set_cell_data_func(cellRender, celldatafunctionCheckbox)
    column2.set_sort_column_id(2)
    column2.set_resizable(True)
    column3 = gtk.TreeViewColumn(_('Package'), gtk.CellRendererText(), text=1)
    column3.set_sort_column_id(1)
    column3.set_resizable(True)
    column4 = gtk.TreeViewColumn(_('Size'), gtk.CellRendererText(), text=3)
    column4.set_sort_column_id(8)
    column4.set_resizable(True)

    treeviewUpdate.append_column(column1)
    treeviewUpdate.append_column(column2)
    treeviewUpdate.append_column(column3)
    treeviewUpdate.append_column(column4)

    selection = treeviewUpdate.get_selection()
    selection.connect('changed', displaySelectedPackage)

    if uid == 0:
        refresh = RefreshThread(True, glade)
        showWindow = True
    else:
        refresh = RefreshThread(False, glade)
    refresh.start()

    gtk.main()
except Exception, detail:
    log.writelines('-- Exception occured in main thread: ' + str(detail) + '\n')
    log.flush()
    log.close()
