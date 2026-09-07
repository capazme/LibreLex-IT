# -*- coding: utf-8 -*-
# Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0.
# This file stays under the Mozilla Public License 2.0.
"""Minimal sidebar panel: a read-only log fed by a worker thread through AsyncCallback."""
import queue
import threading
import time

import uno
import unohelper
from com.sun.star.awt import XActionListener, XCallback
from com.sun.star.lang import XComponent
from com.sun.star.ui import LayoutSize, XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory
from com.sun.star.ui.UIElementType import TOOLPANEL

PANEL_URL = "private:resource/toolpanel/LibreLexSpikeFactory/Panel"
XDL_URL = "vnd.sun.star.extension://org.librelex.spike/panel.xdl"


class PanelFactory(unohelper.Base, XUIElementFactory):
    def __init__(self, ctx):
        self.ctx = ctx

    def createUIElement(self, url, args):
        frame = parent = None
        for a in args:
            if a.Name == "Frame":
                frame = a.Value
            elif a.Name == "ParentWindow":
                parent = a.Value
        panel = Panel(self.ctx, frame, parent, url)
        panel.getRealInterface()
        panel.Window.Visible = True
        return panel


class Panel(unohelper.Base, XUIElement, XToolPanel, XSidebarPanel, XComponent, XActionListener, XCallback):
    def __init__(self, ctx, frame, parent, url):
        self.ctx = ctx
        self.frame = frame
        self.parent = parent
        self.url = url
        self.window = None
        self.queue = queue.Queue()
        self.async_cb = ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.AsyncCallback", ctx)

    # --- XUIElement -------------------------------------------------------
    def getRealInterface(self):
        if self.window is None:
            provider = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.ContainerWindowProvider", self.ctx)
            self.window = provider.createContainerWindow(XDL_URL, "", self.parent, None)
            self._build_controls()
        return self

    @property
    def Frame(self):
        return self.frame

    @property
    def ResourceURL(self):
        return self.url

    @property
    def Type(self):
        return TOOLPANEL

    # --- XToolPanel / XSidebarPanel ----------------------------------------
    @property
    def Window(self):
        return self.window

    def createAccessible(self, parent):
        return self

    def getHeightForWidth(self, width):
        return LayoutSize(260, 260, 260)

    def getMinimalWidth(self):
        return 200

    # --- XComponent --------------------------------------------------------
    def dispose(self):
        pass

    def addEventListener(self, listener):
        pass

    def removeEventListener(self, listener):
        pass

    # --- controls ----------------------------------------------------------
    def _build_controls(self):
        smgr = self.ctx.ServiceManager
        model = smgr.createInstanceWithContext("com.sun.star.awt.UnoControlDialogModel", self.ctx)
        self.window.setModel(model)
        log = model.createInstance("com.sun.star.awt.UnoControlEditModel")
        log.Name = "Log"
        log.PositionX, log.PositionY, log.Width, log.Height = 4, 4, 160, 200
        log.MultiLine = True
        log.ReadOnly = True
        log.AutoVScroll = True
        model.insertByName("Log", log)
        btn = model.createInstance("com.sun.star.awt.UnoControlButtonModel")
        btn.Name = "Start"
        btn.PositionX, btn.PositionY, btn.Width, btn.Height = 4, 210, 60, 16
        btn.Label = "Start stream"
        model.insertByName("Start", btn)
        self.window.getControl("Start").addActionListener(self)
        self.window.getControl("Start").setActionCommand("start")

    # --- XActionListener: button click on the UI thread ---------------------
    def actionPerformed(self, event):
        if event.ActionCommand == "start":
            self.window.getControl("Log").Text = ""
            threading.Thread(target=self._worker, daemon=True).start()

    def disposing(self, event):
        pass

    def _worker(self):
        """Simulates streaming: 100 chunks over ~5 s, pushed to the UI via AsyncCallback."""
        for i in range(1, 101):
            time.sleep(0.05)
            self.queue.put(f"chunk {i}\n")
            self.async_cb.addCallback(self, None)    # schedules notify() on the UI thread
        self.queue.put("[done]\n")
        self.async_cb.addCallback(self, None)

    # --- XCallback: runs on the UI thread ------------------------------------
    def notify(self, data):
        chunks = []
        try:
            while True:
                chunks.append(self.queue.get_nowait())
        except queue.Empty:
            pass
        if chunks:
            ctrl = self.window.getControl("Log")
            ctrl.Text = ctrl.Text + "".join(chunks)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(PanelFactory, "org.librelex.spike.PanelFactory", ("com.sun.star.task.Job",))
