"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""

import PySimpleGUI as sg
import os
import re
import time
import copy
import subprocess
from threading import Thread, Barrier, Timer, Lock
from collections import deque

from .utils import *
from . import config
from .config import Status
from . import update
from .brain import brain
from . import video
from .video import Video, check_ffmpeg, download_ffmpeg, unzip_ffmpeg, ydl_opts
from .about import about_notes
from .downloaditem import DownloadItem


# gui setting
config.all_themes = sg.ListOfLookAndFeelValues()
sg.ChangeLookAndFeel(config.current_theme)
sg.SetOptions(icon=config.APP_ICON, font='Helvetica 11', auto_size_buttons=True, progress_meter_border_depth=0,
              border_width=1)


class MainWindow:
    def __init__(self, d_list):
        """This is the main application user interface window"""
        
        # current download_item
        self.d = DownloadItem()

        # main window
        self.window = None

        # download windows
        self.download_windows = {}  # dict that holds Download_Window() objects --> {d.id: Download_Window()}

        # url
        self.url_timer = None  # usage: Timer(0.5, self.refresh_headers, args=[self.d.url])
        self.bad_headers = [0, range(400, 404), range(405, 418), range(500, 506)]  # response codes

        # youtube specific
        self.video = None
        self.yt_id = 0  # unique id for each youtube thread
        self.playlist = []
        self.pl_title = ''
        self.pl_quality = None
        self._pl_menu = []
        self._stream_menu = []
        self.s_bar_lock = Lock()  # a lock to access a video quality progress bar from threads
        self._s_bar = 0  # side progress bar for video quality loading
        self._m_bar = 0  # main playlist progress par
        self.stream_menu_selection = ''

        # download
        self.pending = deque()
        self.disabled = True  # for download button

        # download list
        self.d_headers = ['i', 'num', 'name', 'progress', 'speed', 'time_left', 'size', 'downloaded', 'status',
                          'resumable', 'folder', 'max_connections', 'live_connections', 'remaining_parts']
        self.d_list = d_list  # list of DownloadItem() objects
        self.selected_row_num = None
        self.selected_d = None

        # update
        self.new_version_available = False
        self.new_version_description = None

        # initial setup
        self.setup()

    def setup(self):
        """initial setup"""
        # download folder
        if not self.d.folder:
            self.d.folder = config.download_folder

        # main window
        self.start_window()

        self.reset()
        self.disable_video_controls()

    def read_q(self):
        # read incoming messages from queue
        for _ in range(config.main_window_q.qsize()):
            k, v = config.main_window_q.get()
            if k == 'log':
                try:
                    if len(self.window['log'].get()) > 3000:
                        self.window['log'](self.window['log'].get()[:2000])
                    self.window['log'](v, append=True)
                except:
                    pass

                # show youtube_dl activity in status text
                if '[youtube]' in v:
                    self.set_status(v.strip('\n'))

            elif k == 'url':
                self.window.Element('url').Update(v)
                self.url_text_change()

            elif k == 'monitor':
                self.window.Element('monitor').Update(v)

            elif k == 'visibility' and v == 'show':
                self.window.BringToFront()
                sg.popup_ok('application is already running', title=config.APP_NAME)

            elif k == 'download':  # can receive download requests
                self.start_download(*v)

            elif k == 'popup':  # can receive download requests
                sg.popup(*v)

    # region gui design
    def create_window(self):
        # main tab
        col1 = [[sg.Combo(values= self.pl_menu, size=(34, 1), key='pl_menu', enable_events=True)],
                [sg.ProgressBar(max_value=100, size=(20, 5), key='m_bar')]]

        col2 = [[sg.Combo(values= self.stream_menu, size=(34, 1), key='stream_menu', enable_events=True)],
                [sg.ProgressBar(max_value=100, size=(20, 5), key='s_bar')]]

        main_layout = [
            [sg.Text(f'{config.APP_NAME}', font='any 20', justification='center', key='app_title')],

            # url
            [sg.T('', size=(50, 1), justification='center', key='update_note', enable_events=True)],
            [sg.Text('URL:'), sg.Input(self.d.url, enable_events=True, change_submits=True, key='url', size=(66, 1)),
             sg.Button('Retry', key='Retry', tooltip=' retry ')],
            [sg.Text('Status:', size=(70, 1), key='status')],

            # spacer
            [sg.T('', font='any 1')],

            # youtube playlist ⚡
            [sg.Frame('Youtube Playlist / videos:', key='youtube_frame', pad=(5, 5), layout=[
                [sg.Column(col1, size=(300, 40),  element_justification='center'),
                 sg.Button('⚡',  pad=(0, 0), tooltip='download this playlist', key='pl_download'),
                 sg.Column(col2, size=(300, 40), element_justification='center')]]
                      )
             ],


            # file info
            [sg.Text('File name:'), sg.Input('', size=(65, 1), key='name', enable_events=True)],
            [sg.T('File size: '), sg.T('-' * 30, key='size'), sg.T('Type:'), sg.T('-' * 35, key='type'),
             sg.T('Resumable:'), sg.T('-----', key='resumable')],
            [sg.Text('Save To:  '), sg.Input(self.d.folder, size=(55, 1), key='folder', enable_events=True),
             sg.FolderBrowse(key='browse')],  #initial_folder=self.d.folder,

            # download button
            [sg.Column([[sg.Button('Download', font='Helvetica 14', border_width=1)]], size=(120, 40),
                       justification='center')],  # sg.T(' ', size=(29, 1), font='Helvetica 12'),

        ]

        # downloads tab
        table_right_click_menu = ['Table', ['!Options for selected file:', '---', 'Open File', 'Open File Location',
                                            '▶ Watch while downloading', 'copy webpage url', 'copy download url',
                                            '⏳ Schedule download', '⏳ Cancel schedule!', 'properties']]
        # ['i', 'num', 'name', 'progress', 'speed', 'time_left', 'size', 'downloaded', 'status',
        #                           'resumable', 'folder', 'max_connections', 'live_connections', 'remaining_parts']
        spacing = [' ' * 4, ' ' * 3, ' ' * 30, ' ' * 3, ' ' * 3, ' ' * 3, ' ' * 6, ' ' * 8, ' ' * 10, ' ' * 12,
                   ' ' * 30, ' ', ' ', ' ']  # setup initial column width

        downloads_layout = [[sg.Button('Resume'), sg.Button('Cancel'), sg.Button('Refresh'),
                             sg.Button('Folder'), sg.Button('D.Window'),
                             sg.T(' ' * 5), sg.T('Item:'),
                             sg.T('---', key='selected_row_num', text_color='white', background_color='red')],
                            [sg.Table(values=[spacing], headings=self.d_headers, size=(70, 13), justification='left',
                                      vertical_scroll_only=False, key='table', enable_events=True, font='any 10',
                                      right_click_menu=table_right_click_menu)],
                            [sg.Button('Resume All'), sg.Button('Stop All'), sg.B('Schedule All'),
                             sg.Button('Delete', button_color=('white', 'red')),
                             sg.Button('Delete All', button_color=('white', 'red'))],
                            ]

        # setting tab
        setting_layout = [[sg.T('User Setting:'), sg.T(' ', size=(50,1)), sg.Button(' about ', key='about')],
                          [sg.Text('Select Theme:'),
                           sg.Combo(values=config.all_themes, default_value=config.current_theme, size=(15, 1),
                                    enable_events=True, key='themes'), sg.Text(f' Total: {len(config.all_themes)} Themes')],
                          [sg.Checkbox('Speed Limit:', key= 'speed_limit_switch', change_submits=True,
                                       tooltip='accepted format: numbers+[k, kb, m, mb] small or capital, examples: 50 k, 10kb, 2m, 3mb, 20, 10MB '),
                           sg.Input('', size=(10, 1), key='speed_limit', disabled=True, enable_events=True),
                           sg.T('0', size=(30, 1), key='current_speed_limit')],
                          [sg.Checkbox('Monitor copied urls in clipboard', default=config.monitor_clipboard, key='monitor',
                                       enable_events=True)],
                          [sg.Checkbox("Show download window", key='show_download_window',
                                       default=config.show_download_window, enable_events=True)],
                          [sg.Text('Max concurrent downloads:'),
                           sg.Combo(values=[x for x in range(1, 101)], size=(5, 1), enable_events=True,
                                    key='max_concurrent_downloads', default_value=config.max_concurrent_downloads)],
                          [sg.Text('Max connections per download:'),
                           sg.Combo(values=[x for x in range(1, 101)], size=(5, 1), enable_events=True,
                                    key='max_connections', default_value=config.max_connections)],
                          [sg.Text('file part size:'), sg.Input(default_text=1024, size=(6, 1),
                                                                enable_events=True, key='part_size'),
                           sg.Text('KBytes   *affects new downloads only')],
                          [sg.T('')],
                          [sg.Checkbox('Check for update on startup', default=config.check_for_update_on_startup,
                                       key='check_for_update_on_startup', change_submits=True)],
                          [sg.T('    '), sg.T('Youtube-dl version = 00.00.00', size=(50,1), key='youtube_dl_update_note'),
                           sg.Button('update youtube-dl', key='update_youtube_dl')],
                          [sg.T('    '), sg.T(f'pyIDM version = {config.APP_VERSION}', size=(50, 1), key='pyIDM_version_note'),
                           sg.Button('update pyIDM', key='update_pyIDM')]
                          ]

        log_layout = [[sg.T('Details events:')], [sg.Multiline(default_text='', size=(70, 17), key='log',
                                                               autoscroll=True)],
                      [sg.Button('Clear Log')]]

        # update_layout = [[sg.T('hello')]]

        layout = [[sg.TabGroup(
            [[sg.Tab('Main', main_layout), sg.Tab('Downloads', downloads_layout), sg.Tab('Setting', setting_layout),
              sg.Tab('Log', log_layout)]],
            key='tab_group')],
            [sg.StatusBar('', size=(81, 1), font='Helvetica 11', key='status_bar')]
        ]

        # window
        window = sg.Window(title=config.APP_TITLE, layout=layout, size=(700, 450),  margins=(2, 2))
        return window

    def start_window(self):
        self.window = self.create_window()
        self.window.Finalize()

        # expand elements to fit
        elements = ['url', 'name', 'folder', 'youtube_frame', 'm_bar', 's_bar', 'pl_menu', 'update_note', 'app_title',
                    'stream_menu', 'log', 'status_bar']  # elements to be expanded
        for e in elements:
            self.window[e].expand(expand_x=True)

        # bind keys events for table, it is tkinter specific
        self.window['table'].Widget.bind("<Button-3>", self.table_right_click)  # right click
        self.window['table'].bind('<Double-Button-1>', '_double_clicked')  # double click
        self.window['table'].bind('<Return>', '_enter_key')  # Enter key

    def restart_window(self):
        try:
            self.window.Close()
        except:
            pass

        self.start_window()

        if self.video:
            self.update_pl_menu()
            self.update_stream_menu()
        else:
            self.pl_menu = ['Playlist']
            self.stream_menu = ['Video quality']

    def table_right_click(self, event):
        try:
            # select row under mouse
            id_ = self.window['table'].Widget.identify_row(event.y)  # first row = 1 not 0
            if id_:
                # mouse pointer over item
                self.window['table'].Widget.selection_set(id_)
                self.select_row(int(id_)-1)  # get count start from zero
                self.window['table']._RightClickMenuCallback(event)
        except:
            pass

    def select_row(self, row_num):
        try:
            self.selected_row_num = int(row_num)
            self.selected_d = self.d_list[self.selected_row_num]
            self.window['selected_row_num']('---' if row_num is None else row_num + 1)

        except Exception as e:
            log('MainWindow.select_row(): ', e)

    def select_tab(self, tab_name):
        try:
            self.window[tab_name].Select()
        except Exception as e:
            print(e)

    def update_gui(self):

        # update Elements
        try:
            if self.window['name'].get() != self.d.name:  # it will prevent cursor jump to end when modifying name
                self.window['name'](self.d.name)
            self.window.Element('size')(size_format(self.d.size))
            self.window.Element('type')(self.d.type)
            self.window.Element('resumable')('Yes' if self.d.resumable else 'No')

            # download list / table
            table_values = [[self.format_cell_data(key, getattr(item, key, '')) for key in self.d_headers] for item in
                            self.d_list]
            self.window.Element('table').Update(values=table_values[:])

            # re-select the previously selected row in the table
            if self.selected_row_num is not None:
                self.window.Element('table').Update(select_rows=(self.selected_row_num,))
            else:
                # update selected item number
                self.window.Element('selected_row_num').Update('---')

            # update status bar
            self.window.Element('status_bar').Update(
                f'Active downloads: {len(config.active_downloads)}, pending: {len(self.pending)}')

            # setting
            speed_limit = size_format(config.speed_limit * 1024) if config.speed_limit > 0 else "_no limit_"
            self.window['current_speed_limit'](f'current speed limit: {speed_limit}')

            self.window['youtube_dl_update_note'](f'Youtube-dl version = {config.ytdl_VERSION}, Latest version = {config.ytdl_LATEST_VERSION}')
            self.window['pyIDM_version_note'](f'pyIDM version = {config.APP_VERSION}, Latest version = {config.APP_LATEST_VERSION}')

        except Exception as e:
            print('MainWindow.update_gui() error:', e)

    def enable(self):
        self.disabled = False

    def disable(self):
        self.disabled = True

    def set_status(self, text):
        try:
            self.window.Element('status').Update(text)
        except:
            pass

    # endregion

    def run(self):
        """main loop"""
        timer1 = 0
        timer2 = 0
        one_time = True
        while True:
            event, values = self.window.Read(timeout=50)
            self.event, self.values = event, values
            # if event != '__TIMEOUT__': print(event, values)

            if event is None:
                self.main_frameOnClose()
                break

            elif event == 'update_note':
                # if clicked on update notification text
                if self.new_version_available:
                    self.update_app()

            elif event == 'url':
                self.url_text_change()

            elif event == 'Download':
                self.download_btn()

            elif event == 'folder':
                if values['folder']:
                    self.d.folder = values['folder']
                else:  # in case of empty entries
                    self.window.Element('folder').Update(self.d.folder)

            elif event == 'name':
                self.d.name = validate_file_name(values['name'])

            elif event == 'Retry':
                self.retry()

            # downloads tab events
            elif event == 'table':
                try:
                    row_num = values['table'][0]
                    self.select_row(row_num)
                except Exception as e:
                    log("MainWindow.run:if event == 'table': ", e)

            elif event in ('table_double_clicked', 'table_enter_key', 'Open File', 'Watch while downloading') and self.selected_d:
                if self.selected_d.status == Status.completed:
                    open_file(self.selected_d.full_name)
                else:
                    open_file(self.selected_d.full_temp_name)

            # table right click menu event
            elif event == 'Open File Location':
                self.open_file_location()

            elif event == 'copy webpage url':
                clipboard_write(self.selected_d.url)

            elif event == 'copy download url':
                clipboard_write(self.selected_d.eff_url)

            elif event == 'properties':
                try:
                    info = self.window['table'].get()[self.selected_row_num]

                    if info:
                        msg = ''
                        for i in range(len(info)):

                            msg += f'{self.d_headers[i]}: {info[i]} \n'
                        msg += f'webpage url: {self.selected_d.url} \n\n'
                        msg += f'playlist url: {self.selected_d.pl_url} \n'
                        sg.popup_scrolled(msg, title='File properties')
                except:
                    pass

            elif event == '⏳ Schedule download':
                response = self.ask_for_sched_time(msg=self.selected_d.name)
                if response:
                    self.selected_d.sched = response

            elif event == '⏳ Cancel schedule!':
                self.selected_d.sched = None

            elif event == 'Resume':
                self.resume_btn()

            elif event == 'Cancel':
                self.cancel_btn()

            elif event == 'Refresh':
                self.refresh_link_btn()

            elif event == 'Folder':
                self.open_file_location()

            elif event == 'D.Window':
                # create download window
                if self.selected_d.status == Status.downloading:
                    d = self.selected_d
                    if d.id not in self.download_windows:
                        self.download_windows[d.id] = DownloadWindow(d=d)
                    else:
                        self.download_windows[d.id].focus()

            elif event == 'Resume All':
                self.resume_all_downloads()

            elif event == 'Stop All':
                self.stop_all_downloads()

            elif event == 'Schedule All':
                response = self.ask_for_sched_time(msg='Schedule all non completed files')
                if response:
                    for d in self.d_list:
                        if d.status in (Status.pending, Status.cancelled):
                            d.sched = response

            elif event == 'Delete':
                self.delete_btn()

            elif event == 'Delete All':
                self.delete_all_downloads()

            # video events
            elif event == 'pl_download':
                self.download_playlist()

            elif event == 'pl_menu':
                self.playlist_OnChoice(values['pl_menu'])

            elif event == 'stream_menu':
                self.stream_OnChoice(values['stream_menu'])

            # setting tab
            elif event == 'themes':
                config.current_theme = values['themes']
                sg.ChangeLookAndFeel(config.current_theme)

                # close all download windows if existed
                for win in self.download_windows.values():
                    win.window.Close()
                self.download_windows = {}

                self.restart_window()

            elif event == 'speed_limit_switch':
                switch = values['speed_limit_switch']

                if switch:
                    self.window['speed_limit'](disabled=False)
                    event == 'speed_limit'
                else:
                    config.speed_limit = 0
                    self.window['speed_limit'](disabled=True)

            elif event == 'speed_limit':
                sl = values['speed_limit'].replace(' ', '')  # if values['speed_limit'] else 0

                # validate speed limit,  expecting formats: number + (k, kb, m, mb) final value should be in kb
                # pattern \d*[mk]b?

                match = re.fullmatch(r'\d+([mk]b?)?', sl, re.I)
                if match:
                    # print(match.group())

                    digits = re.match(r"[0-9]+", sl, re.I).group()
                    digits = int(digits)

                    letters = re.search(r"[a-z]+", sl, re.I)
                    letters = letters.group().lower() if letters else None

                    # print(digits, letters)

                    if letters in ('k', 'kb', None):
                        sl = digits
                    elif letters in('m', 'mb'):
                        sl = digits * 1024
                else:
                    sl = 0

                config.speed_limit = sl
                # print('speed limit:', config.speed_limit)

            elif event == 'max_concurrent_downloads':
                config.max_concurrent_downloads = int(values['max_concurrent_downloads'])

            elif event == 'max_connections':
                mc = int(values['max_connections'])
                if mc > 0: self.max_connections = mc

            elif event == 'monitor':
                global monitor_clipboard
                monitor_clipboard = values['monitor']
                config.clipboard_q.put(('monitor', monitor_clipboard))

            elif event == 'show_download_window':
                config.show_download_window = values['show_download_window']

            elif event == 'part_size':
                try:
                    self.d.part_size = int(values['part_size']) * 1024
                except:
                    pass

            elif event == 'check_for_update_on_startup':
                config.check_for_update_on_startup = values['check_for_update_on_startup']

            elif event == 'update_youtube_dl':
                self.update_ytdl()

            elif event == 'update_pyIDM':
                self.update_app()

            # log
            elif event == 'Clear Log':
                try:
                    self.window['log']('')
                except:
                    pass

            # about window
            elif event == 'about':
                sg.PopupNoButtons(about_notes, title=f'About {config.APP_NAME} DM', non_blocking=True)

            # Run every n seconds
            if time.time() - timer1 >= 1:
                timer1 = time.time()

                # gui update
                self.update_gui()

                # read incoming requests and messages from queue
                self.read_q()

                # scheduled downloads
                self.check_scheduled()

                # process pending jobs
                if self.pending and len(config.active_downloads) < config.max_concurrent_downloads:
                    self.start_download(self.pending.popleft())

            # run download windows if existed
            keys = list(self.download_windows.keys())
            for i in keys:
                win = self.download_windows[i]
                win.run()
                if win.event is None:
                    self.download_windows.pop(i, None)

            # run one time, reason this is here not in setup, is to minimize gui loading time
            if one_time:
                one_time = False
                # check availability of ffmpeg in the system or in same folder with this script
                self.ffmpeg_check()

                # check_for_update_on_startup
                if config.check_for_update_on_startup:
                    Thread(target=self.check_for_update, daemon=True).start()
                    Thread(target=self.check_for_ytdl_update, daemon=True).start()

            if time.time() - timer2 >= 1:
                timer2 = time.time()
                # update notification
                if self.new_version_available:
                    self.animate_update_note()
                else:
                    self.window['update_note']('')


    # region headers
    def refresh_headers(self, url):
        if self.d.url != '':
            self.change_cursor('busy')
            Thread(target=self.get_header, args=[url], daemon=True).start()

    def get_header(self, url):
        # curl_headers = get_headers(url)
        self.d.update(url)

        # update headers only if no other curl thread created with different url
        if url == self.d.url:
            # self.headers = curl_headers
            # self.d.eff_url = curl_headers.get('eff_url')

            # self.status_code = self.d.status_code  # curl_headers.get('status_code', '')
            self.set_status(self.d.status_code_description)  #(f"{self.status_code} - {translate_server_code(self.status_code)}")

            # update file info
            # self.update_info()

            # enable download button
            if self.d.status_code not in self.bad_headers and self.d.type != 'text/html':
                self.enable()

            # check if the link is html maybe it contains stream video
            if self.d.type == 'text/html':
                Thread(target=self.youtube_func, daemon=True).start()

            self.change_cursor('default')

    # endregion

    # region download
    def start_download(self, d, silent=False):
        """Receive a DownloadItem and pass it to brain
        :param bool silent: True or False, show a download window
        :param DownloadItem d: DownloadItem() object"""
        # callback = post_download_callback
        if d is None:
            return

        # check for ffmpeg availability in case this is a video only stream
        if d.audio_url:
            log('Dash video detected')
            self.ffmpeg_check()

        # validate destination folder for existence and permission
        try:
            with open(os.path.join(d.folder, 'test'), 'w') as test_file:
                test_file.write('0')
            os.unlink(os.path.join(d.folder, 'test'))
        except FileNotFoundError:
            sg.Popup(f'destination folder {d.folder} does not exist', title='folder error')
            return 'error'
        except PermissionError:
            sg.Popup(f"you don't have enough permission for destination folder {d.folder}", title='folder error')
            return 'error'
        except Exception as e:
            sg.Popup(f'problem in destination folder {repr(e)}', title='folder error')
            return 'error'

        # validate file name
        if d.name == '':
            sg.popup("File name can't be empty!!", title='invalid file name!!')
            return 'error'
        # elif d.name.rsplit('.', 1) != d.extension:  # no extension yet for download item d
        #     r = sg.popup_ok_cancel(f"Warning, File name doesn't have correct file extension: {d.type} \nContinue?", title=Warning)
        #     if r != 'Ok':
        #         return 'error'

        d.max_connections = config.max_connections if d.resumable else 1
        if silent is None:
            silent = not config.show_download_window

        # check if file with the same name exist in destination
        if os.path.isfile(os.path.join(d.folder, d.name)):
            #  show dialogue
            msg = 'File with the same name already exist in ' + self.d.folder + '\n Do you want to overwrite file?'
            response = sg.PopupYesNo(msg)

            if response != 'Yes':
                log('Download cancelled by user')
                return 'cancelled'
            else:
                log('deleting existing file:', d.full_name)
                try:
                    os.unlink(d.full_name)
                    os.unlink(d.full_audio_name)
                except:
                    pass

        # check if file already existed in download list
        i = self.file_in_d_list(d.name, d.folder)
        if i is not None:  # file already exist in d_list
            _d = self.d_list[i]
            log(f'start download fn> file exist in d_list, num {_d.num}')

            # if item in active downloads, quit or if status is downloading, quit
            if _d.status == Status.downloading:
                log('start download fn> file is being downloaded already, abort mission, taking no action')
                return
            else:
                # get some info from old one
                d.id = _d.id
                d.part_size = d.segment_size

                self.d_list[i] = d

        else:  # new file
            # generate unique id number for each download
            d.id = len(self.d_list)

            # add to download list
            self.d_list.append(d)

        # if max concurrent downloads exceeded download job will be added to pending deque
        if len(config.active_downloads) >= config.max_concurrent_downloads:
            d.status = Status.pending
            self.pending.append(d)
            return

        # start downloading
        if not silent:
            # create download window
            self.download_windows[d.id] = DownloadWindow(d)

        # create and start brain in a separate thread
        Thread(target=brain, daemon=True, args=(d, config.speed_limit)).start()

    def stop_all_downloads(self):
        # change status of pending items to cancelled
        for i, d in enumerate(self.d_list):
            if d.status == Status.pending:
                d.status = Status.cancelled

        # send cancelled status for all queues
        for i in config.active_downloads:
            d = self.d_list[i]
            d.q.brain.put(('status', Status.cancelled))

        self.pending.clear()

    def resume_all_downloads(self):
        # change status of all non completed items to pending
        for i, d in enumerate(self.d_list):
            if d.status == Status.cancelled:
                self.start_download(d, silent=True)

    def file_in_d_list(self, name, folder):
        for i, d in enumerate(self.d_list):
            if name == d.name and folder == d.folder:
                return i
        return None

    def download_btn(self):
        d = copy.copy(self.d)

        if self.disabled:
            sg.popup_ok('Nothing to download', 'it might be a web page or invalid url link',
                        'check your link or click "Retry"')
            return

        # search current list for previous item with same name, folder
        found_index = self.file_in_d_list(self.d.name, self.d.folder)
        if found_index is not None: # might be zero
            #  show dialogue
            msg = f'File with the same name: \n{self.d.name},\n already exist in download list\n' \
                  'Do you want to resume this file?\n' \
                  'Resume ==> continue if it has been partially downloaded ... \n' \
                  'Overwrite ==> delete old downloads and overwrite existing item... \n' \
                  'note: "if you need fresh download, you have to change file name \n' \
                  'or target folder or delete same entry from download list'
            # response = sg.PopupYesNo(msg)
            window = sg.Window(title='', layout=[[sg.T(msg)], [sg.B('Resume'), sg.B('Overwrite'), sg.B('Cancel')]])
            response, _ = window()
            window.close()
            if response == 'Resume':
                eff_url = self.d.eff_url
                d = self.d_list[found_index]
                d.eff_url = eff_url

            elif response == 'Overwrite':
                _d = self.d_list[found_index]

                # delete temp folder on disk
                delete_folder(_d.temp_folder)
                os.unlink(_d.temp_file)

                d.id = _d.id

            else:
                log('Download cancelled by user')
                return

        # if max concurrent downloads exceeded download job will be added to pending deque
        if len(config.active_downloads) >= config.max_concurrent_downloads:
            #  show dialogue
            msg = 'File has been added to pending list'
            sg.Popup(msg)

        r = self.start_download(d)

        if r not in ('error', 'cancelled'):
            self.select_tab('Downloads')

    # endregion

    # region downloads tab

    @staticmethod
    def format_cell_data(k, v):
        """take key, value and prepare it for display in cell"""
        if k in ['size', 'downloaded']:
            v = size_format(v)
        elif k == 'speed':
            v = size_format(v, '/s')
        elif k in ('percent', 'progress'):
            v = f'{v}%' if v else '---'
        elif k == 'time_left':
            v = time_format(v)
        elif k == 'resume':
            v = 'yes' if v else 'no'
        elif k == 'name':
            v = validate_file_name(v)

        return v

    def resume_btn(self):
        if self.selected_row_num is None:
            return

        if self.selected_d.status == Status.completed:
            response = sg.PopupYesNo('File already completed before \ndo you want to re-download again?',
                                     title='Warning!!!')
            if response == 'No':
                return

        self.start_download(self.selected_d)

    def cancel_btn(self):
        if self.selected_row_num is None:
            return
        d = self.selected_d
        if d.status == Status.pending:
            self.d_list[d.id].status = Status.cancelled
            config.active_downloads.pop(d.id)
        elif d.status == Status.downloading and d.q:
            d.q.brain.put(('status', Status.cancelled))

    def delete_btn(self):
        if self.selected_row_num is None:
            return

        # abort if there is items in progress or paused
        if config.active_downloads:
            msg = "Can't delete items while downloading.\nStop or cancel all downloads first!"
            sg.Popup(msg)
            return

        # confirm to delete
        msg = "Warninig!!!\nAre you sure you want to delete!\n%s?" % self.selected_d.name
        r = sg.PopupYesNo(msg, title='Delete file?', keep_on_top=True)
        if r != 'Yes': return

        try:
            # pop item
            d = self.d_list.pop(self.selected_row_num)

            # update count numbers for remaining items
            n = len(self.d_list)
            for i in range(n):
                self.d_list[i].id = i

            # fix a selected item number if it no longer exist
            if not self.d_list:
                self.selected_row_num = None
            else:
                last_num = len(self.d_list) - 1
                if self.selected_row_num > last_num: self.selected_row_num = last_num

            # delete temp folder on disk
            delete_folder(d.temp_folder)
            os.unlink(d.temp_file)

        except:
            pass

    def delete_all_downloads(self):
        # abort if there is items in progress or paused
        if config.active_downloads:
            msg = "Can't delete items while downloading.\nStop or cancel all downloads first!"
            sg.Popup(msg)
            return

        # warning / confirmation dialog, user has to write ok to proceed
        msg = 'you are about to delete all the items in download list and their progress temp files\n' \
              'if you are sure write the word "delete" down below and hit ok button?\n'
        response = sg.PopupGetText(msg, title='Warning!!', keep_on_top=True)
        if response == 'delete':
            log('start deleting all download items')
        else:
            return

        self.stop_all_downloads()

        # selected item number
        self.selected_row_num = None

        # pop item
        n = len(self.d_list)
        for i in range(n):
            try:  # to delete temp folder on disk
                d = self.d_list[i]
                delete_folder(d.temp_folder)
                os.unlink(d.temp_file)
            except Exception as e:
                handle_exceptions(e)

        self.d_list.clear()

    def open_file_location(self):
        if self.selected_row_num is None:
            return

        d = self.selected_d

        try:
            folder = os.path.abspath(d.folder)
            file = os.path.join(folder, d.name)

            if os.name == 'nt':
                # windows
                if d.name not in os.listdir(folder):
                    os.startfile(folder)
                else:
                    param = r'explorer /select, ' + '"' + file + '"'
                    subprocess.Popen(param)
            else:
                # linux
                os.system('xdg-open "%s"' % folder)
        except Exception as e:
            handle_exceptions(e)

    def refresh_link_btn(self):
        if self.selected_row_num is None:
            return

        d = self.selected_d

        # update current d
        self.d.size = d.size
        self.d.segment_size = d.segment_size
        self.d.folder = d.folder

        self.window['url'](d.url)
        self.url_text_change()

        self.window['folder'](self.d.folder)
        self.select_tab('Main')


    # endregion

    # region video

    @property
    def m_bar(self):
        return self._m_bar

    @m_bar.setter
    def m_bar(self, value):
        self._m_bar = value if value <= 100 else 100
        try:
            self.window.Element('m_bar').UpdateBar(value)
        except:
            pass

    @property
    def s_bar(self):
        return self._s_bar

    @s_bar.setter
    def s_bar(self, value):
        self._s_bar = value if value <= 100 else 100
        try:
            self.window.Element('s_bar').UpdateBar(value)
        except:
            pass

    @property
    def pl_menu(self):
        return self._pl_menu

    @pl_menu.setter
    def pl_menu(self, rows):
        self._pl_menu = rows
        try:
            self.window.Element('pl_menu').Update(values=rows)
        except:
            pass

    @property
    def stream_menu(self):
        return self._stream_menu

    @stream_menu.setter
    def stream_menu(self, rows):
        self._stream_menu = rows
        try:
            self.window.Element('stream_menu').Update(values=rows)
        except:
            pass

    # def enable_video_controls(self):
    #     try:
    #         pass # self.window.Element('pl_download').Update(disabled=False)
    #     except:
    #         pass

    def disable_video_controls(self):
        try:
            self.reset_progress_bar()
            self.pl_menu = ['Playlist']
            self.stream_menu = ['Video quality']
        except:
            pass

    def reset_progress_bar(self):
        self.m_bar = 0
        self.s_bar = 0

    def youtube_func(self):
        """fetch metadata from youtube and other websites"""

        # validate youtube url
        # pattern = r'^(http(s)?:\/\/)?((w){3}.)?youtu(be|.be)?(\.com)?\/.+'
        # match = re.match(pattern, self.d.url)
        # if not match:
        #     return  # quit if url is not a valid youtube watch url

        # getting videos from youtube is time consuming, if another thread starts, it should cancel the previous one
        # create unique identification for this thread
        self.yt_id += 1 if self.yt_id < 1000 else 0
        yt_id = self.yt_id
        url = self.d.url

        msg = f'looking for video streams ... Please wait'
        log(msg)
        self.set_status(msg)

        # reset video controls
        self.disable_video_controls()
        self.disable()
        self.change_cursor('busy')

        # main progress bar
        self.m_bar = 10

        # assign playlist items
        self.playlist = []

        # quit if main window terminated
        if config.terminate: return

        try:
            # we import youtube-dl in separate thread to minimize startup time
            if video.ytdl is None:
                log('youtube-dl module still not loaded completely, please wait')
                while not video.ytdl:
                    time.sleep(0.1)  # wait until module get imported

            # youtube-dl process
            with video.ytdl.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(self.d.url, download=False, process=False)

                print(result)

                # set playlist / video title
                self.pl_title = result.get('title', '')
                self.d.name = result.get('title', 'video')

                # main progress bar
                self.m_bar = 30
                # check results if it's a playlist
                if result.get('_type') == 'playlist' or 'entries' in result:
                    pl_info = list(result.get('entries'))

                    self.d.pl_url = self.d.url

                    # progress bars
                    self.m_bar = 50  # decide increment value in side bar based on number of threads

                    self.window['s_bar'].update_bar(0, max=len(pl_info))  # change maximum value
                    s_bar_incr = 1  # 100 / len(pl_info) # 100 // len(pl_info) + 1 #

                    self.playlist = [None for _ in range(len(pl_info))]  # fill list so we can store videos in order
                    v_threads = []
                    for num, item in enumerate(pl_info):
                        # we have an issue here with youtube-dl doesn't get full video url from playlist
                        # print("item.get('url')=", item.get('url'))
                        # print("item.get('webpage_url')=", item.get('webpage_url'))
                        # print(item)

                        t = Thread(target=self.get_video, daemon=True, args=[num, item.get('url'), yt_id, s_bar_incr])
                        v_threads.append(t)
                        t.start()

                    for t in v_threads:
                        t.join()

                    # clean playlist in case a slot left with 'None' value
                    self.playlist = [v for v in self.playlist if v]

                else:  # in case of single video
                    self.playlist = [Video(self.d.url, vid_info=result)]
                    self.s_bar = 100

            # quit if main window terminated
            if config.terminate: return

            # quit if we couldn't extract any videos info (playlist or single video)
            if not self.playlist:
                self.disable_video_controls()
                self.disable()
                self.set_status('')
                self.change_cursor('default')
                self.reset()
                log('youtube func: quitting, can not extract videos')
                return

            # quit if url changed by user
            if url != self.d.url:
                self.disable_video_controls()
                self.change_cursor('default')
                log('youtube func: quitting, url changed by user')
                return

            # quit if new youtube func thread started
            if yt_id != self.yt_id:
                log('youtube func: quitting, new instance has started')
                return

            # update playlist menu
            self.update_pl_menu()
            self.update_stream_menu()  # uses the current self.video
            self.update_video_param()  # take stream number as an argument, default 0

            # self.enable_video_controls()
            self.enable()

            self.m_bar = 100

        except Exception as e:
            handle_exceptions(e)
            self.disable_video_controls()
            self.disable()
            self.reset()

        finally:
            self.change_cursor('default')

    def get_video(self, num, vid_url, yt_id, s_bar_incr):
        try:
            video = Video(vid_url)

            # make sure no other youtube func thread started
            if yt_id != self.yt_id:
                log('get_video:> operation cancelled')
                return

            self.playlist[num] = video

        except Exception as e:
            log('MainWindow.get_video:> ', e)
        finally:
            with self.s_bar_lock:
                self.s_bar += s_bar_incr
                # log('MainWindow.get_video:>', f'num={num} - self.s_bar={self.s_bar} - s_bar_incr={s_bar_incr}')

    def update_pl_menu(self):
        try:
            # set playlist label
            self.set_status(f'{len(self.playlist)} videos in Playlist: {self.pl_title}')

            # update playlist menu items
            self.pl_menu = [str(i + 1) + '- ' + video.title for i, video in enumerate(self.playlist)]

            # choose current item
            self.video = self.playlist[0]
        except:
            pass

    def update_video_param(self):

        # update file properties
        self.d.url = self.video.url
        self.d.eff_url = self.video.eff_url
        self.d.name = self.video.name
        self.d.size = self.video.size
        self.d.type = self.video.type
        self.d.audio_url = self.video.audio_url
        self.d.audio_size = self.video.audio_size
        self.d.resumable = True

    def update_stream_menu(self):
        try:
            self.stream_menu = self.video.stream_menu

            # select first stream
            selected_text = self.video.stream_names[0]
            self.window['stream_menu'](selected_text)
            self.stream_OnChoice(selected_text)
        except:
            pass

    def playlist_OnChoice(self, selected_text):
        if selected_text not in self.pl_menu:
            return

        index = self.pl_menu.index(selected_text)
        self.video = self.playlist[index]

        self.update_stream_menu()
        self.update_video_param()

    def stream_OnChoice(self, selected_text):
        if selected_text not in self.stream_menu:
            return
        if selected_text not in self.video.stream_names:
            selected_text = self.stream_menu_selection or self.video.stream_names[0]
            self.window['stream_menu'](selected_text)

        self.stream_menu_selection = selected_text
        self.video.selected_stream = self.video.streams[selected_text]
        self.update_video_param()

    def download_playlist(self):
        # check if there is a video file or quit
        if not self.video:
            sg.popup_ok('Playlist is empty, nothing to download :)', title='Playlist download')
            return

        # prepare a list for master stream menu
        mp4_videos = {}
        other_videos = {}
        audio_streams = {}

        # will use raw stream names which doesn't include size
        for video in self.playlist:
            mp4_videos.update({stream.raw_name: stream for stream in video.mp4_videos.values()})
            other_videos.update({stream.raw_name: stream for stream in video.other_videos.values()})
            audio_streams.update({stream.raw_name: stream for stream in video.audio_streams.values()})

        # sort streams based on quality
        mp4_videos = {k: v for k, v in sorted(mp4_videos.items(), key=lambda item: item[1].quality, reverse=True)}
        other_videos = {k: v for k, v in sorted(other_videos.items(), key=lambda item: item[1].quality, reverse=True)}
        audio_streams = {k: v for k, v in sorted(audio_streams.items(), key=lambda item: item[1].quality, reverse=True)}

        raw_streams = {**mp4_videos, **other_videos, **audio_streams}
        master_stream_menu = ['● Video streams:                     '] + list(mp4_videos.keys()) + list(other_videos.keys()) + \
                      ['', '● Audio streams:                 '] + list(audio_streams.keys())
        master_stream_combo_selection = ''


        video_checkboxes = []
        stream_combos = []

        general_options_layout = [sg.Checkbox('Select All', enable_events=True, key='Select All'), sg.T('', size=(15,1)),
                                  sg.T('Choose quality for all videos:'),
                                  sg.Combo(values=master_stream_menu, default_value=master_stream_menu[0], size=(28,1), key='master_stream_combo', enable_events=True)]

        video_layout = []

        for num, video in enumerate(self.playlist):
            video_checkbox = sg.Checkbox(truncate(video.title, 40), size=(40, 1), tooltip=video.title, key=f'video {num}')
            video_checkboxes.append(video_checkbox)

            stream_combo = sg.Combo(values=video.raw_stream_menu, default_value=video.raw_stream_menu[1], font='any 8', size=(26, 1), key=f'stream {num}', enable_events=True)
            stream_combos.append(stream_combo)

            row = [video_checkbox, stream_combo, sg.T(size_format(video.size), size=(10, 1), font='any 8', key=f'size_text {num}')]
            video_layout.append(row)

        video_layout = [sg.Column(video_layout, scrollable=True, vertical_scroll_only=True, size=(650, 250), key='col')]

        layout = [[sg.T(f'Total Videos: {len(self.playlist)}')]]
        layout.append(general_options_layout)
        layout.append([sg.T('')])
        layout.append([sg.Frame(title='select videos to download:', layout=[video_layout])])
        layout.append([sg.Col([[sg.OK(), sg.Cancel()]], justification='right')])

        w= sg.Window(title='Playlist download window', layout=layout, finalize=True, margins=(2,2))

        chosen_videos = []

        while True:
            e, v = w()
            if e in (None, 'Cancel'):
                w.close()
                return
            # print(e, v)

            if e == 'OK':
                chosen_videos.clear()
                for num, video in enumerate(self.playlist):
                    selected_text = v[f'stream {num}']
                    video.selected_stream = raw_streams[selected_text]

                    if v[f'video {num}'] is True:
                        chosen_videos.append(self.playlist[num])

                w.close()
                break

            elif e == 'Select All':
                checked = w['Select All'].get()
                for checkbox in video_checkboxes:
                    checkbox(checked)

            elif e == 'master_stream_combo':
                selected_text = v['master_stream_combo']
                if selected_text in raw_streams:
                    # update all videos stream menus from master stream menu
                    for num, stream_combo in enumerate(stream_combos):
                        video = self.playlist[num]

                        if selected_text in video.raw_streams:
                            stream_combo(selected_text)
                            video.selected_stream = video.raw_streams[selected_text]
                            w[f'size_text {num}'](size_format(video.size))

            elif e.startswith('stream'):
                num = int(e.split()[-1])

                video = self.playlist[num]
                selected_text = w[e].get()

                if selected_text in video.raw_streams:
                    video.selected_stream = video.raw_streams[selected_text]
                else:
                    w[e](video.selected_stream.raw_name)

                w[f'size_text {num}'](size_format(video.size))

        self.select_tab('Downloads')

        for video in chosen_videos:
            # resume_support = True if video.size else False

            log('download playlist fn>', 'stream', repr(video.selected_stream))
            log(f'download playlist fn> media size= {video.size}, name= {video.name}')

            # start download
            d = DownloadItem(url=video.url,  name=video.name, folder=self.d.folder)

            # update file properties
            d.eff_url = video.eff_url
            d.size=video.size
            d.type = video.type
            d.audio_url = video.audio_url
            d.audio_size = video.audio_size
            d.max_connections=config.max_connections
            d.resumable=True

            self.start_download(d, silent=True)

    def ffmpeg_check(self):
        if not check_ffmpeg():
            if config.operating_system == 'Windows':
                response = sg.popup_yes_no(
                               '"ffmpeg" is missing',
                               'Download it for you?',
                               title='ffmpeg is missing')
                if response == 'Yes':
                    download_ffmpeg()
            else:
                sg.popup_error(
                    '"ffmpeg" is required to merge an audio stream with your video',
                    'executable must be copied into pyIDM folder or add ffmpeg path to system PATH',
                    '',
                    'you can download it manually from https://www.ffmpeg.org/download.html',
                    title='ffmpeg is missing')


    # endregion

    # region General
    def url_text_change(self):
        url = self.window.Element('url').Get().strip()
        if url == self.d.url:
            return

        # Focus and select main app page in case text changed from script
        self.window.BringToFront()
        self.select_tab('Main')

        self.reset()
        try:
            self.d.eff_url = self.d.url = url

            # schedule refresh header func
            if isinstance(self.url_timer, Timer):
                self.url_timer.cancel()  # cancel previous timer

            self.url_timer = Timer(0.5, self.refresh_headers, args=[url])
            self.url_timer.start()  # start new timer

        except:
            pass

    def retry(self):
        self.d.url = ''
        self.url_text_change()

    def reset(self):
        # reset some values
        self.d.reset()
        self.set_status('')
        self.playlist = []
        self.video = None

        # widgets
        self.disable()
        self.disable_video_controls()

    def change_cursor(self, cursor='busy'):
        if cursor == 'busy':
            self.window['Main'].set_cursor('watch')
        else:
            self.window['Main'].set_cursor('arrow')

    def main_frameOnClose(self):
        # global terminate
        config.terminate = True

        log('main frame closing')
        self.window.Close()

        # Terminate all downloads before quitting if any is a live
        try:
            for i in config.active_downloads:
                d = self.d_list[i]
                d.q.brain.put(('status', Status.cancelled))
        except:
            pass

        config.clipboard_q.put(('status', Status.cancelled))

    def check_scheduled(self):
        t = time.localtime()
        c_t = (t.tm_hour, t.tm_min)
        for d in self.d_list:
            if d.sched and d.sched[0] <= c_t[0] and d.sched[1] <=c_t[1]:
                self.start_download(d)  # send for download
                d.sched = None  # cancel schedule time

    def ask_for_sched_time(self, msg=''):
        """Show a gui dialog to ask user for schedule time for download items, it take one or more of download items"""
        response = None

        layout = [
            [sg.T('schedule download item:')],
            [sg.T(msg)],
            [sg.Combo(values=list(range(1, 13)), default_value=1, size=(5, 1), key='hours'), sg.T('H  '),
             sg.Combo(values=list(range(0, 60)), default_value=0, size=(5, 1), key='minutes'), sg.T('m  '),
             sg.Combo(values=['AM', 'PM'], default_value='AM', size=(5, 1), key='am pm')],
            [sg.Ok(), sg.Cancel()]
        ]

        window = sg.Window('Scheduling download item', layout, finalize=True)

        e, v = window()

        if e == 'Ok':
            h = int(v['hours'])
            if v['am pm'] == 'AM' and h == 12:
                h = 0
            elif v['am pm'] == 'PM' and h != 12:
                h += 12

            m = int(v['minutes'])

            # # assign to download item
            # d.sched = (h, m)

            response = h, m

        window.close()
        return response
    # endregion

    # region update
    def check_for_update(self):
        # check for update
        current_version = config.APP_VERSION
        info = update.get_changelog()

        if info:
            latest_version, version_description = info
            self.new_version_available = latest_version != current_version

            # updaet global values
            config.APP_LATEST_VERSION = latest_version
            self.new_version_description = version_description

    def update_app(self):
        """show changelog with latest version and ask user for update"""
        if not self.new_version_description:
            self.check_for_update()

        if not self.new_version_description:
            sg.popup_ok('couldnt check for update')
            return

        if config.APP_VERSION == config.APP_LATEST_VERSION:
            sg.popup_ok(f'{config.APP_NAME} is up-to-date!')
            return

        layout = [
            [sg.T('New version available:')],
            [sg.Multiline(self.new_version_description, size=(50, 10))],
            [sg.B('Update'), sg.Cancel()]
        ]
        window = sg.Window('Update Application', layout, finalize=True, keep_on_top=True)
        event, _ = window()
        if event == 'Update':
            update.update()

        window.close()

    def animate_update_note(self):
        # display word by word
        # values = 'new version available, click me for more info !'.split()
        # values = [' '.join(values[:i + 1]) for i in range(len(values))]

        # display character by character
        # values = [c for c in 'new version available, click me for more info !']
        # values = [''.join(values[:i + 1]) for i in range(len(values))]

        # normal on off display
        values = ['', 'new version available, click me for more info !']
        note = self.window['update_note']

        # add animation text property to note object
        if not hasattr(note, 'animation_index'):
            note.animation_index = 0

        if note.animation_index < len(values) - 1:
            note.animation_index += 1
        else:
            note.animation_index = 0

        new_text = values[note.animation_index]
        note(new_text)

    def check_for_ytdl_update(self):
        config.ytdl_LATEST_VERSION = update.check_for_ytdl_update()

    def update_ytdl(self):
        current_version = config.ytdl_VERSION
        latest_version = config.ytdl_LATEST_VERSION or update.check_for_ytdl_update()
        if latest_version:
            config.ytdl_LATEST_VERSION = latest_version
            log('youtube-dl update, latest version = ', latest_version, ' - current version = ', current_version)

            if latest_version != current_version:
                # select log tab
                self.select_tab('Log')

                response = sg.popup_ok_cancel(
                    f'Found new version of youtube-dl on github {latest_version}\n'
                    f'current version =  {current_version} \n'
                    'Install new version?',
                    title='youtube-dl module update')

                if response == 'OK':
                    try:
                        Thread(target=update.update_youtube_dl).start()
                    except Exception as e:
                        log('failed to update youtube-dl module:', e)
            else:
                sg.popup_ok(f'youtube_dl is up-to-date, current version = {current_version}')
    # endregion


class DownloadWindow:

    def __init__(self, d=None):
        self.d = d
        self.q = d.q
        self.window = None
        self.event = None
        self.values = None
        self.timeout = 10
        self.timer = 0

        self.create_window()

    def create_window(self):
        main_layout = [
            [sg.T('', size=(55, 7), key='out')],

            [sg.ProgressBar(max_value=100, key='progress_bar', size=(42, 15), border_width=3)],

            [sg.Column([[sg.Button('Hide', key='hide'), sg.Button('Cancel', key='cancel')]], justification='right')],

        ]

        log_layout = [[sg.T('Details events:')],
                      [sg.Multiline(default_text='', size=(70, 16), font='any 8', key='log', autoscroll=True)],
                      [sg.Button('Clear Log')]]

        layout = [[sg.TabGroup([[sg.Tab('Main', main_layout), sg.Tab('Log', log_layout)]])]]

        self.window = sg.Window(title=self.d.name, layout=layout, finalize=True, margins=(2, 2), size=(460, 240))
        self.window['progress_bar'].expand()

    def update_gui(self):
        # trim name and folder length
        name = truncate(self.d.name, 50)
        folder = truncate(self.d.folder, 50)

        out = (f"File: {name}\n"
               f"Folder: {folder}\n"
               f"Downloaded:    {size_format(self.d.downloaded)} out of"
               f" {size_format(self.d.size)} ----  {self.d.progress}%\n"
               f"speed: {size_format(self.d.speed, '/s')}\n"
               f"Time remaining: {time_format(self.d.time_left)}\n"
               f"Live Connections: {self.d.live_connections} - Remaining parts: {self.d.remaining_parts} x "
               f"({size_format(self.d.segment_size)})")

        # update log
        if self.d.q and self.d.q.d_window.qsize():
            k, v = self.d.q.d_window.get()
            # print(k, v)
            if k == 'log':
                try:
                    if len(self.window['log'].get()) > 3000:
                        self.window['log'](self.window['log'].get()[:2000])
                    self.window['log'](v, append=True)
                except:
                    pass


        try:
            self.window.Element('out').Update(value=out)
            self.window.Element('progress_bar').UpdateBar(self.d.progress)

            if self.d.status in (Status.completed, Status.cancelled):
                self.event = None
                self.window.Close()
        except:
            pass

    def run(self):
        self.event, self.values = self.window.Read(timeout=self.timeout)
        if self.event in ('cancel', None):
            self.d.q.brain.put(('status', Status.cancelled))
            self.close()

        elif self.event == 'hide':
            self.close()

        # update gui
        if time.time() - self.timer >= 1:
            self.timer = time.time()
            self.update_gui()

    def focus(self):
        self.window.BringToFront()

    def close(self):
        self.event = None
        self.window.Close()
