#!/usr/bin/env python
"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""

# This is the main application module ........................................

# standard modules
import os, sys

# install update if user downloaded an update batch "FROZEN application only"
if hasattr(sys, 'frozen'):  # like if application frozen by cx_freeze
    current_directory = os.path.dirname(sys.executable)

    # Should copy contents of PyIDM_update_files folder and overwrite PyIDM original files
    update_batch_path = os.path.join(current_directory, 'PyIDM_update_files')
    if os.path.isdir(update_batch_path):
        from distutils.dir_util import copy_tree, remove_tree
        copy_tree(update_batch_path, current_directory)
        print('done installing updates')

        # delete folder
        remove_tree(update_batch_path)

# standard modules
from threading import Thread
import time


# This code should stay on top to handle relative imports in case of direct call of pyIDM.py
if __package__ is None:
    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(path))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))
    
    __package__ = 'pyidm'
    import pyidm

# check and auto install external modules
from .dependency import install_missing_pkgs
install_missing_pkgs()


# local modules
from .utils import *
from . import config
from . import setting
from . import video
from .gui import MainWindow, SysTray


def clipboard_listener():
    old_data = ''
    # monitor = True

    while True:

        new_data = clipboard.paste()

        if new_data == f'PyIDM "{config.APP_VERSION}", any one there?':  # a possible message coming from new instance of this script
            clipboard.copy('hey, get lost!')  # it will be read by singleApp() as an exit signal
            config.main_q.put('start_main_window')
            config.main_window_q.put(('visibility', 'show'))  # restore main window if minimized

        if config.monitor_clipboard and new_data != old_data:
            if new_data.startswith('http') and ' ' not in new_data:
                config.main_window_q.put(('url', new_data))

            old_data = new_data

        # monitor global termination flag
        if config.shutdown:
            break

        time.sleep(0.2)


def singleApp():
    """send a message thru clipboard to check if an app instance already running"""
    original = clipboard.paste()  # get original clipboard value
    clipboard.copy(f'PyIDM "{config.APP_VERSION}", any one there?')
    time.sleep(0.3)
    answer = clipboard.paste()
    clipboard.copy(original)  # restore clipboard original value

    if answer == 'hey, get lost!':
        return False
    else:
        return True


def main():

    # quit if there is previous instance of this script already running
    if not singleApp():
        print('previous instance already running')
        config.shutdown = True
        return

    # import youtube-dl in a separate thread
    Thread(target=video.import_ytdl, daemon=True).start()

    # load stored setting from disk
    setting.load_setting()
    config.d_list = setting.load_d_list()

    # run clipboard monitor thread
    Thread(target=clipboard_listener, daemon=True).start()

    # run systray
    systray = SysTray()
    Thread(target=systray.run, daemon=True).start()

    # start gui main loop
    main_window = MainWindow(config.d_list)

    # create main run loop
    while True:

        if main_window and main_window.active:
            main_window.run()
            sleep_time = 0.01
        else:
            main_window = None
            sleep_time = 0.5

        # sleep a little to save cpu resources
        time.sleep(sleep_time)

        if systray.active:
            state = f'PyIDM is active \n{main_window.total_speed}' if not config.terminate else 'PyIDM is off'
            systray.update(hover_text=state)

        # read Main queue
        for _ in range(config.main_q.qsize()):
            value = config.main_q.get()
            if value == 'start_main_window':
                if not main_window:
                    main_window = MainWindow(config.d_list)
                    # main_window.active = True
                else:
                    main_window.un_hide()
            elif value == 'minimize_to_systray':
                if main_window:
                    main_window.hide()
            elif value == 'close_to_systray':
                if main_window:
                    main_window.close()

        # global shutdown flag
        if config.shutdown or (not main_window and not systray.active):
            print('config.shutdown, systray.active', config.shutdown, systray.active)
            systray.shutdown()
            config.shutdown = True
            break

    # Save setting to disk
    setting.save_setting()
    setting.save_d_list(config.d_list)


if __name__ == '__main__':
    main()

