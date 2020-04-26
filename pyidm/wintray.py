"""
systray for windows only,
source code: https://github.com/Infinidat/infi.systray

Copyright (c) 2017 INFINIDAT
This module is adapted from an implementation by Simon Brunning,
which in turn was adapted from Mark Hammond's win32gui_taskbar.py and win32gui_menu.py demos from PyWin32.
"""

# this file is a merge of traybar.py and win32_adapter.py from Infinidat/infi.systray package

import ctypes
import ctypes.wintypes
import locale
import sys
import os
# from .win32_adapter import *
import threading
import uuid

RegisterWindowMessage = ctypes.windll.user32.RegisterWindowMessageA
LoadCursor = ctypes.windll.user32.LoadCursorA
LoadIcon = ctypes.windll.user32.LoadIconA
LoadImage = ctypes.windll.user32.LoadImageA
RegisterClass = ctypes.windll.user32.RegisterClassA
CreateWindowEx = ctypes.windll.user32.CreateWindowExA
UpdateWindow = ctypes.windll.user32.UpdateWindow
DefWindowProc = ctypes.windll.user32.DefWindowProcA
GetSystemMetrics = ctypes.windll.user32.GetSystemMetrics
InsertMenuItem = ctypes.windll.user32.InsertMenuItemA
PostMessage = ctypes.windll.user32.PostMessageA
PostQuitMessage = ctypes.windll.user32.PostQuitMessage
SetMenuDefaultItem = ctypes.windll.user32.SetMenuDefaultItem
GetCursorPos = ctypes.windll.user32.GetCursorPos
SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
TrackPopupMenu = ctypes.windll.user32.TrackPopupMenu
CreatePopupMenu = ctypes.windll.user32.CreatePopupMenu
CreateCompatibleDC = ctypes.windll.gdi32.CreateCompatibleDC
GetDC = ctypes.windll.user32.GetDC
CreateCompatibleBitmap = ctypes.windll.gdi32.CreateCompatibleBitmap
GetSysColorBrush = ctypes.windll.user32.GetSysColorBrush
FillRect = ctypes.windll.user32.FillRect
DrawIconEx = ctypes.windll.user32.DrawIconEx
SelectObject = ctypes.windll.gdi32.SelectObject
DeleteDC = ctypes.windll.gdi32.DeleteDC
DestroyWindow = ctypes.windll.user32.DestroyWindow
GetModuleHandle = ctypes.windll.kernel32.GetModuleHandleA
GetMessage = ctypes.windll.user32.GetMessageA
TranslateMessage = ctypes.windll.user32.TranslateMessage
DispatchMessage = ctypes.windll.user32.DispatchMessageA
Shell_NotifyIcon = ctypes.windll.shell32.Shell_NotifyIcon
DestroyIcon = ctypes.windll.user32.DestroyIcon

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_ICON = 2
NIF_MESSAGE = 1
NIF_TIP = 4
MIIM_ID = 2
MIIM_SUBMENU = 4
MIIM_STRING = 64
MIIM_BITMAP = 128
WM_DESTROY = 2
WM_CLOSE = 16
WM_COMMAND = 273
WM_USER = 1024
WM_LBUTTONDBLCLK = 515
WM_RBUTTONUP = 517
WM_LBUTTONUP = 514
WM_NULL = 0
CS_VREDRAW = 1
CS_HREDRAW = 2
IDC_ARROW = 32512
COLOR_WINDOW = 5
WS_OVERLAPPED = 0
WS_SYSMENU = 524288
CW_USEDEFAULT = -2147483648
LR_LOADFROMFILE = 16
LR_DEFAULTSIZE = 64
IMAGE_ICON = 1
IDI_APPLICATION = 32516  # IDI_INFORMATION  # default application icon , https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-loadicona
TPM_LEFTALIGN = 0
SM_CXSMICON = 49
SM_CYSMICON = 50
COLOR_MENU = 4
DI_NORMAL = 3

WPARAM = ctypes.wintypes.WPARAM
LPARAM = ctypes.wintypes.LPARAM
HANDLE = ctypes.wintypes.HANDLE
if ctypes.sizeof(ctypes.c_long) == ctypes.sizeof(ctypes.c_void_p):
    LRESULT = ctypes.c_long
elif ctypes.sizeof(ctypes.c_longlong) == ctypes.sizeof(ctypes.c_void_p):
    LRESULT = ctypes.c_longlong

SZTIP_MAX_LENGTH = 128
LOCALE_ENCODING = locale.getpreferredencoding()


def encode_for_locale(s):
    """
    Encode text items for system locale. If encoding fails, fall back to ASCII.
    """
    try:
        return s.encode(LOCALE_ENCODING, 'ignore')
    except (AttributeError, UnicodeDecodeError):
        return s.decode('ascii', 'ignore').encode(LOCALE_ENCODING)

POINT = ctypes.wintypes.POINT
RECT = ctypes.wintypes.RECT
MSG = ctypes.wintypes.MSG

LPFN_WNDPROC = ctypes.CFUNCTYPE(LRESULT, HANDLE, ctypes.c_uint, WPARAM, LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint),
                ("lpfnWndProc", LPFN_WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", HANDLE),
                ("hIcon", HANDLE),
                ("hCursor", HANDLE),
                ("hbrBackground", HANDLE),
                ("lpszMenuName", ctypes.c_char_p),
                ("lpszClassName", ctypes.c_char_p),
               ]


class MENUITEMINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint),
                ("fMask", ctypes.c_uint),
                ("fType", ctypes.c_uint),
                ("fState", ctypes.c_uint),
                ("wID", ctypes.c_uint),
                ("hSubMenu", HANDLE),
                ("hbmpChecked", HANDLE),
                ("hbmpUnchecked", HANDLE),
                ("dwItemData", ctypes.c_void_p),
                ("dwTypeData", ctypes.c_char_p),
                ("cch", ctypes.c_uint),
                ("hbmpItem", HANDLE),
               ]


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint),
                ("hWnd", HANDLE),
                ("uID", ctypes.c_uint),
                ("uFlags", ctypes.c_uint),
                ("uCallbackMessage", ctypes.c_uint),
                ("hIcon", HANDLE),
                ("szTip", ctypes.c_char * SZTIP_MAX_LENGTH),
                ("dwState", ctypes.c_uint),
                ("dwStateMask", ctypes.c_uint),
                ("szInfo", ctypes.c_char * 256),
                ("uTimeout", ctypes.c_uint),
                ("szInfoTitle", ctypes.c_char * 64),
                ("dwInfoFlags", ctypes.c_uint),
                ("guidItem", ctypes.c_char * 16),
               ]
    if sys.getwindowsversion().major >= 5:
        _fields_.append(("hBalloonIcon", HANDLE))


def PackMENUITEMINFO(text=None, hbmpItem=None, wID=None, hSubMenu=None):
    res = MENUITEMINFO()
    res.cbSize = ctypes.sizeof(res)
    res.fMask = 0
    if hbmpItem is not None:
        res.fMask |= MIIM_BITMAP
        res.hbmpItem = hbmpItem
    if wID is not None:
        res.fMask |= MIIM_ID
        res.wID = wID
    if text is not None:
        text = encode_for_locale(text)
        res.fMask |= MIIM_STRING
        res.dwTypeData = text
    if hSubMenu is not None:
        res.fMask |= MIIM_SUBMENU
        res.hSubMenu = hSubMenu
    return res


def LOWORD(w):
    return w & 0xFFFF


def PumpMessages():
    msg = MSG()
    while GetMessage(ctypes.byref(msg), None, 0, 0) > 0:
        TranslateMessage(ctypes.byref(msg))
        DispatchMessage(ctypes.byref(msg))


def NotifyData(hWnd=0, uID=0, uFlags=0, uCallbackMessage=0, hIcon=0, szTip=""):
    szTip = encode_for_locale(szTip)[:SZTIP_MAX_LENGTH]
    res = NOTIFYICONDATA()
    res.cbSize = ctypes.sizeof(res)
    res.hWnd = hWnd
    res.uID = uID
    res.uFlags = uFlags
    res.uCallbackMessage = uCallbackMessage
    res.hIcon = hIcon
    res.szTip = szTip
    return res


class SysTrayIcon(object):
    """
    menu_options: tuple of tuples (menu text, menu icon path or None, function name)

    menu text and tray hover text should be Unicode
    hover_text length is limited to 128; longer text will be truncated

    Can be used as context manager to enable automatic termination of tray
    if parent thread is closed:

        with SysTrayIcon(icon, hover_text) as systray:
            for item in ['item1', 'item2', 'item3']:
                systray.update(hover_text=item)
                do_something(item)

    """
    QUIT = 'QUIT'
    SPECIAL_ACTIONS = [QUIT]

    FIRST_ID = 1023

    def __init__(self,
                 icon,
                 hover_text,
                 menu_options=None,
                 on_quit=None,
                 default_menu_index=None,
                 window_class_name=None):

        self._icon = icon
        self._icon_shared = False
        self._hover_text = hover_text
        self._on_quit = on_quit

        menu_options = menu_options or ()
        menu_options = menu_options + (('Quit', None, SysTrayIcon.QUIT),)
        self._next_action_id = SysTrayIcon.FIRST_ID
        self._menu_actions_by_id = set()
        self._menu_options = self._add_ids_to_menu_options(list(menu_options))
        self._menu_actions_by_id = dict(self._menu_actions_by_id)

        window_class_name = window_class_name or ("SysTrayIconPy-%s" % (str(uuid.uuid4())))

        self._default_menu_index = (default_menu_index or 0)
        self._window_class_name = encode_for_locale(window_class_name)
        self._message_dict = {RegisterWindowMessage("TaskbarCreated"): self._restart,
                              WM_DESTROY: self._destroy,
                              WM_CLOSE: self._destroy,
                              WM_COMMAND: self._command,
                              WM_USER+20: self._notify}
        self._notify_id = None
        self._message_loop_thread = None
        self._hwnd = None
        self._hicon = 0
        self._hinst = None
        self._window_class = None
        self._menu = None
        self._register_class()

    def __enter__(self):
        """Context manager so SysTray can automatically close"""
        self.start()
        return self

    def __exit__(self, *args):
        """Context manager so SysTray can automatically close"""
        self.shutdown()

    def WndProc(self, hwnd, msg, wparam, lparam):
        hwnd = HANDLE(hwnd)
        wparam = WPARAM(wparam)
        lparam = LPARAM(lparam)
        if msg in self._message_dict:
            self._message_dict[msg](hwnd, msg, wparam.value, lparam.value)
        return DefWindowProc(hwnd, msg, wparam, lparam)

    def _register_class(self):
        # Register the Window class.
        self._window_class = WNDCLASS()
        self._hinst = self._window_class.hInstance = GetModuleHandle(None)
        self._window_class.lpszClassName = self._window_class_name
        self._window_class.style = CS_VREDRAW | CS_HREDRAW
        self._window_class.hCursor = LoadCursor(0, IDC_ARROW)
        self._window_class.hbrBackground = COLOR_WINDOW
        self._window_class.lpfnWndProc = LPFN_WNDPROC(self.WndProc)
        RegisterClass(ctypes.byref(self._window_class))

    def _create_window(self):
        style = WS_OVERLAPPED | WS_SYSMENU
        self._hwnd = CreateWindowEx(0, self._window_class_name,
                                      self._window_class_name,
                                      style,
                                      0,
                                      0,
                                      CW_USEDEFAULT,
                                      CW_USEDEFAULT,
                                      0,
                                      0,
                                      self._hinst,
                                      None)
        UpdateWindow(self._hwnd)
        self._refresh_icon()

    def _message_loop_func(self):
        self._create_window()
        PumpMessages()

    def start(self):
        if self._hwnd:
            return      # already started
        self._message_loop_thread = threading.Thread(target=self._message_loop_func)
        self._message_loop_thread.start()

    def shutdown(self):
        if not self._hwnd:
            return      # not started
        PostMessage(self._hwnd, WM_CLOSE, 0, 0)
        self._message_loop_thread.join()

    def update(self, icon=None, hover_text=None):
        """ update icon image and/or hover text """
        if icon:
            self._icon = icon
            self._load_icon()
        if hover_text:
            self._hover_text = hover_text
        self._refresh_icon()

    def _add_ids_to_menu_options(self, menu_options):
        result = []
        for menu_option in menu_options:
            option_text, option_icon, option_action = menu_option
            if callable(option_action) or option_action in SysTrayIcon.SPECIAL_ACTIONS:
                self._menu_actions_by_id.add((self._next_action_id, option_action))
                result.append(menu_option + (self._next_action_id,))
            elif non_string_iterable(option_action):
                result.append((option_text,
                               option_icon,
                               self._add_ids_to_menu_options(option_action),
                               self._next_action_id))
            else:
                raise Exception('Unknown item', option_text, option_icon, option_action)
            self._next_action_id += 1
        return result

    def _load_icon(self):
        # release previous icon, if a custom one was loaded
        # note: it's important *not* to release the icon if we loaded the default system icon (with
        # the LoadIcon function) - this is why we assign self._hicon only if it was loaded using LoadImage
        if not self._icon_shared and self._hicon != 0:
            DestroyIcon(self._hicon)
            self._hicon = 0

        # Try and find a custom icon
        hicon = 0
        if self._icon is not None and os.path.isfile(self._icon):
            icon_flags = LR_LOADFROMFILE | LR_DEFAULTSIZE
            icon = encode_for_locale(self._icon)
            hicon = self._hicon = LoadImage(0, icon, IMAGE_ICON, 0, 0, icon_flags)
            self._icon_shared = False

        # Can't find icon file - using default shared icon
        if hicon == 0:
            self._hicon = LoadIcon(0, IDI_APPLICATION)
            self._icon_shared = True
            self._icon = None

    def _refresh_icon(self):
        if self._hwnd is None:
            return
        if self._hicon == 0:
            self._load_icon()
        if self._notify_id:
            message = NIM_MODIFY
        else:
            message = NIM_ADD
        self._notify_id = NotifyData(self._hwnd,
                          0,
                          NIF_ICON | NIF_MESSAGE | NIF_TIP,
                          WM_USER+20,
                          self._hicon,
                          self._hover_text)
        Shell_NotifyIcon(message, ctypes.byref(self._notify_id))

    def _restart(self, hwnd, msg, wparam, lparam):
        self._refresh_icon()

    def _destroy(self, hwnd, msg, wparam, lparam):
        if self._on_quit:
            self._on_quit(self)
        nid = NotifyData(self._hwnd, 0)
        Shell_NotifyIcon(NIM_DELETE, ctypes.byref(nid))
        PostQuitMessage(0)  # Terminate the app.
        # TODO * release self._menu with DestroyMenu and reset the memeber
        #      * release self._hicon with DestoryIcon and reset the member
        #      * release loaded menu icons (loaded in _load_menu_icon) with DeleteObject
        #        (we don't keep those objects anywhere now)
        self._hwnd = None
        self._notify_id = None

    def _notify(self, hwnd, msg, wparam, lparam):
        if lparam == WM_LBUTTONDBLCLK:
            self._execute_menu_option(self._default_menu_index + SysTrayIcon.FIRST_ID)
        elif lparam == WM_RBUTTONUP:
            self._show_menu()
        elif lparam == WM_LBUTTONUP:
            pass
        return True

    def _show_menu(self):
        if self._menu is None:
            self._menu = CreatePopupMenu()
            self._create_menu(self._menu, self._menu_options)
            #SetMenuDefaultItem(self._menu, 1000, 0)

        pos = POINT()
        GetCursorPos(ctypes.byref(pos))
        # See http://msdn.microsoft.com/library/default.asp?url=/library/en-us/winui/menus_0hdi.asp
        SetForegroundWindow(self._hwnd)
        TrackPopupMenu(self._menu,
                       TPM_LEFTALIGN,
                       pos.x,
                       pos.y,
                       0,
                       self._hwnd,
                       None)
        PostMessage(self._hwnd, WM_NULL, 0, 0)

    def _create_menu(self, menu, menu_options):
        for option_text, option_icon, option_action, option_id in menu_options[::-1]:
            if option_icon:
                option_icon = self._prep_menu_icon(option_icon)

            if option_id in self._menu_actions_by_id:
                item = PackMENUITEMINFO(text=option_text,
                                        hbmpItem=option_icon,
                                        wID=option_id)
                InsertMenuItem(menu, 0, 1, ctypes.byref(item))
            else:
                submenu = CreatePopupMenu()
                self._create_menu(submenu, option_action)
                item = PackMENUITEMINFO(text=option_text,
                                        hbmpItem=option_icon,
                                        hSubMenu=submenu)
                InsertMenuItem(menu, 0, 1,  ctypes.byref(item))

    def _prep_menu_icon(self, icon):
        icon = encode_for_locale(icon)
        # First load the icon.
        ico_x = GetSystemMetrics(SM_CXSMICON)
        ico_y = GetSystemMetrics(SM_CYSMICON)
        hicon = LoadImage(0, icon, IMAGE_ICON, ico_x, ico_y, LR_LOADFROMFILE)

        hdcBitmap = CreateCompatibleDC(None)
        hdcScreen = GetDC(None)
        hbm = CreateCompatibleBitmap(hdcScreen, ico_x, ico_y)
        hbmOld = SelectObject(hdcBitmap, hbm)
        # Fill the background.
        brush = GetSysColorBrush(COLOR_MENU)
        FillRect(hdcBitmap, ctypes.byref(RECT(0, 0, 16, 16)), brush)
        # draw the icon
        DrawIconEx(hdcBitmap, 0, 0, hicon, ico_x, ico_y, 0, 0, DI_NORMAL)
        SelectObject(hdcBitmap, hbmOld)

        # No need to free the brush
        DeleteDC(hdcBitmap)
        DestroyIcon(hicon)

        return hbm

    def _command(self, hwnd, msg, wparam, lparam):
        id = LOWORD(wparam)
        self._execute_menu_option(id)

    def _execute_menu_option(self, id):
        menu_action = self._menu_actions_by_id[id]
        if menu_action == SysTrayIcon.QUIT:
            DestroyWindow(self._hwnd)
        else:
            menu_action(self)


def non_string_iterable(obj):
    try:
        iter(obj)
    except TypeError:
        return False
    else:
        return not isinstance(obj, str)
