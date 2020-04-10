"""
    PyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""
import gc
import PySimpleGUI as sg
import os
import time
import copy
from threading import Thread, Timer, Lock
from collections import deque

from .utils import *
from . import config
from .config import Status
from . import update
from .brain import brain
from . import video
from .video import Video, check_ffmpeg, download_ffmpeg, unzip_ffmpeg, get_ytdl_options, process_video_info
from .about import about_notes
from .downloaditem import DownloadItem
from .iconsbase64 import *

# todo: this module needs some clean up

# gui Settings
config.all_themes = natural_sort(sg.ListOfLookAndFeelValues())
sg.SetOptions(icon=APP_ICON, font='Helvetica 10', auto_size_buttons=True, progress_meter_border_depth=0,
              border_width=1)  # Helvetica font is guaranteed to work on all operating systems

# transparent color for button which mimic current background, will be used as a parameter, ex. **transparent
transparent = {}


class MainWindow:
    def __init__(self, d_list):
        """This is the main application user interface window"""

        # current download_item
        self.d = DownloadItem()

        # main window
        self.window = None

        # active child windows
        self.active_windows = []  # list holds active_Windows objects

        # url
        self.url = ''  # current url in url input widget
        self.url_timer = None  # usage: Timer(0.5, self.refresh_headers, args=[self.d.url])
        self.bad_headers = [0, range(400, 404), range(405, 418), range(500, 506)]  # response codes

        # playlist/video
        self.video = None
        self.yt_id = 0  # unique id for each youtube thread
        self.playlist = []
        self.pl_title = ''
        self.pl_quality = None
        self._pl_menu = []
        self._stream_menu = []
        self.m_bar_lock = Lock()  # a lock to access a video quality progress bar from threads
        self._m_bar = 0  # main playlist progress par value
        self._s_bar = 0  # individual video streams progress bar value
        self.stream_menu_selection = ''

        # download
        self.pending = deque()
        self.disabled = True  # for download button

        # download list
        self.d_headers = ['i', 'name', 'progress', 'speed', 'time_left', 'downloaded', 'total_size', 'status']
        self.d_list = d_list  # list of DownloadItem() objects
        self.selected_row_num = None
        self._selected_d = None

        # update
        self.new_version_available = False
        self.new_version_description = None

        # thumbnail
        self.current_thumbnail = None

        # timers
        self.statusbar_timer = 0

        # side bar
        self.animate_bar = True

        # initial setup
        self.setup()

    def setup(self):
        """initial setup"""

        self.change_theme()

        # download folder
        if not self.d.folder:
            self.d.folder = config.download_folder

        # main window
        self.start_window()

        self.reset()
        self.reset_video_controls()

    def read_q(self):
        # read incoming messages from queue
        for _ in range(config.main_window_q.qsize()):
            k, v = config.main_window_q.get()
            if k == 'log':
                try:
                    contents = self.window['log'].get()
                    # print(size_format(len(contents)))
                    if len(contents) > config.max_log_size:
                        # delete 20% of contents to keep size under max_log_size
                        slice_size = int(config.max_log_size * 0.2)
                        self.window['log'](contents[slice_size:])

                    self.window['log'](v, append=True)
                except Exception as e:
                    print(e)

                self.set_status(v.strip('\n'))

                # parse youtube output while fetching playlist info with option "process=True"
                if '[download]' in v:  # "[download] Downloading video 3 of 30"
                    try:
                        b = v.rsplit(maxsplit=3)  # ['[download] Downloading video', '3', 'of', '30']
                        total_num = int(b[-1])
                        num = int(b[-3])

                        # get 50% of this value and the remaining 50% will be for other processing
                        percent = int(num * 100 / total_num)
                        percent = percent // 2

                        # update media progress bar
                        self.m_bar = percent

                        # update playlist frame title
                        self.window['playlist_frame'](
                            value=f'Playlist ({num} of {total_num} {"videos" if num > 1 else "video"}):')
                    except:
                        pass

            elif k == 'url':
                self.window['url'](v.strip())
                self.url_text_change()

            elif k == 'monitor':
                self.window.Element('monitor').Update(v)

            elif k == 'visibility' and v == 'show':
                self.window.BringToFront()
                sg.popup_ok('application is already running', title=config.APP_NAME)

            elif k == 'download':  # receive download requests
                self.start_download(*v)

            elif k == 'popup':
                type_ = v['type_']
                if type_ == 'popup_no_buttons':
                    sg.popup_no_buttons(v['msg'], title=v['title'])
                else:
                    sg.popup(v['msg'], title=v['title'])

            elif k == 'show_update_gui':  # show update gui
                self.show_update_gui()

    # region gui design

    def create_main_tab(self):
        # get current bg and text colors
        bg_color = sg.theme_background_color()
        text_color = sg.theme_text_color() if sg.theme_text_color() != "1234567890" else 'black'

        # column for playlist menu
        video_block = sg.Col([
                              [sg.Combo(values=self.pl_menu, size=(36, 1), key='pl_menu', enable_events=True, pad=(0, 5))],
                              [sg.Combo(values=self.stream_menu, size=(36, 1), key='stream_menu', enable_events=True, pad=(0, 5))],
                              [sg.ProgressBar(max_value=100, size=(15, 9), key='m_bar', pad=(0, 5)),
                               sg.ProgressBar(max_value=100, size=(5, 9), key='s_bar', pad=(0, 5))]], size=(290, 80))

        pl_button = sg.Button('', tooltip=' download playlist ', key='pl_download', image_data=playlist_icon, **transparent)

        layout = [
            # spacer
            [sg.T('', font='any 2')],

            # app icon and app name
            [sg.Image(data=APP_ICON), sg.Text(f'{config.APP_NAME}', font='any 20', justification='center', key='app_title'),
             sg.T('', size=(30, 1), justification='center', key='update_note', enable_events=True, font='any 9'),
             # sg.T('  !    ', key='about', font='any 8 bold', enable_events=True, tooltip=' about! ')
             ],

            # url entry
            [sg.T('Link:  '),
            sg.Input(self.d.url, enable_events=True, key='url', size=(49, 1),  right_click_menu=['url', ['copy url', 'paste url']]),
            sg.Button('', key='Retry', tooltip=' retry ', image_data=refresh_icon, **transparent)],

            # playlist/video block
            [sg.Col([[sg.T('       '), sg.Image(data=thumbnail_icon, key='main_thumbnail')]], size=(320, 110)),
             sg.Frame('Playlist/video:',
                      [[video_block]],
                      relief=sg.RELIEF_SUNKEN, key='playlist_frame'),
             sg.Column([
                 [sg.T('', font='any 2')],
                 [sg.Button('', tooltip=' download playlist ', key='pl_download', image_data=playlist_icon, **transparent)],
                 [sg.T('', font='any 2')],
                 [sg.Button('', tooltip=' subtitles ', key='subtitles', image_data=subtitle_icon, **transparent)]],
             pad=(0,0))
             ],

            # format code
            [sg.T(' ' * 300, key='format_code', font='any 9', pad=(5, 0))],

            # folder
            [sg.Image(data=folder_icon),
             sg.Input(config.download_folder, size=(55, 1), key='folder', enable_events=True, background_color=bg_color,
                      text_color=text_color, ),
             sg.B('', image_data=browse_icon, **transparent, key='browse',
                  button_type=sg.BUTTON_TYPE_BROWSE_FOLDER, target='folder')],

            # file name
            [sg.Text('File:', pad=(6, 0)),
             sg.Input('', size=(65, 1), key='name', enable_events=True, background_color=bg_color,
                      text_color=text_color), sg.Text('      ')],

            # file properties
            [sg.T('-' * 300, key='file_properties', font='any 9')],

            # download button
            [sg.Column([[sg.B('', tooltip='Main download Engine', image_data=download_icon, key='Download')]],
                       size=(166, 50), justification='center')],

        ]

        return layout

    def create_downloads_tab(self):

        # selected download item's preview panel, "si" = selected item
        si_layout = [sg.Image(data=thumbnail_icon, key='si_thumbnail'),
                     sg.Col([[sg.T('', size=(100, 5), key='si_out', font='any 8')],
                            [sg.ProgressBar(100, size=(20, 10), key='si_bar'), sg.T(' ', size=(10, 1), key='si_percent')]])]

        table_right_click_menu = ['Table', ['!Options for selected file:', '---', 'Open File', 'Open File Location',
                                            '▶ Watch while downloading', 'copy webpage url', 'copy download url',
                                            '⏳ Schedule download', '⏳ Cancel schedule!', 'properties']]
        headings = ['i', 'name', '%', 'speed', 'left', 'done', 'size', 'status']
        col_widths = [6, 30, 10, 10, 10, 10, 10, 10]

        layout = [[sg.Button('', key='Resume', tooltip=' Resume download ', image_data=resume_icon, **transparent),
                   sg.Button('', key='Cancel', tooltip=' Cancel download ', image_data=stop_icon, **transparent),
                   sg.Button('', key='Refresh', tooltip=' Refresh link ', image_data=refresh_icon, **transparent),
                   sg.Button('', key='Folder', tooltip=' open file location ', image_data=folder_icon, **transparent),
                   sg.Button('', key='D.Window', tooltip=' Show download window ', image_data=dwindow_icon, **transparent),
                   sg.Button('', key='Delete', tooltip=' Delete item from list ', image_data=delete_icon, **transparent),

                   sg.T(' ' * 60), sg.T(''),

                   sg.Button('', key='Resume All', tooltip=' Resume All ', image_data=resumeall_icon, **transparent),
                   sg.Button('', key='Stop All', tooltip=' Stop All ', image_data=stopall_icon, **transparent),
                   sg.B('', key='Schedule All', tooltip=' Schedule All ', image_data=sched_icon, **transparent),
                   sg.Button('', key='Delete All', tooltip=' Delete All items from list ', image_data=deleteall_icon, **transparent),

                   ],

                  # table
                  [sg.Table(values=headings, headings=headings, num_rows=9, justification='left', auto_size_columns=False,
                            vertical_scroll_only=False, key='table', enable_events=True, font='any 9',
                            right_click_menu=table_right_click_menu, max_col_width=100, col_widths=col_widths,
                            row_height=20
                            )],

                  si_layout
                  ]

        return layout

    def create_settings_tab(self):
        """settings tab with TabGroup"""

        proxy_tooltip = """proxy setting examples:
                - http://proxy_address:port
                - 157.245.224.29:3128

                or if authentication required: 
                - http://username:password@proxyserveraddress:port  

                then choose proxy type i.e. "http, https, socks4, or socks5"  
                """

        general = [
            [sg.T('', size=(60, 1)), sg.Button('', key='about', image_data=about_icon, pad=(5, 10), **transparent)],

            [sg.T('Settings Folder:'),
             sg.Combo(values=['Local', 'Global'],
                      default_value='Local' if config.sett_folder == config.current_directory else 'Global',
                      key='sett_folder', enable_events=True),
             sg.T(config.sett_folder, key='sett_folder_text', size=(100, 1), font='any 9')],

            [sg.Text('Select Theme:  '),
             sg.Combo(values=config.all_themes, default_value=config.current_theme, size=(15, 1),
                      enable_events=True, key='themes'),
             sg.Text(f' Total: {len(config.all_themes)} Themes')],

            [sg.Checkbox('Monitor copied urls in clipboard', default=config.monitor_clipboard,
                         key='monitor', enable_events=True)],

            [sg.Checkbox("Show download window", key='show_download_window',
                         default=config.show_download_window, enable_events=True)],
            [sg.Checkbox("Auto close download window after finish downloading", key='auto_close_download_window',
                         default=config.auto_close_download_window, enable_events=True)],

            [sg.Checkbox("Show video Thumbnail", key='show_thumbnail', default=config.show_thumbnail,
                         enable_events=True)],

            [sg.Text('Segment size:  '), sg.Input(default_text=size_format(config.segment_size), size=(10, 1),
                                                  enable_events=True, key='segment_size'),
             sg.Text(f'Current value: {size_format(config.segment_size)}', size=(30, 1), key='seg_current_value'),
             sg.T('*ex: 512 KB or 5 MB', font='any 8')],

            [sg.Checkbox('process big playlist info on demand', default=config.process_big_playlist_on_demand,
                         enable_events=True, key='process_big_playlist_on_demand')],

            [sg.Checkbox('Manually select audio format for dash videos', default=config.manually_select_dash_audio,
                         enable_events=True, key='manually_select_dash_audio')]
        ]

        network = [
            [sg.T('')],
            [sg.Checkbox('Speed Limit:', default=True if config.speed_limit else False,
                         key='speed_limit_switch', enable_events=True,
                         ),
             sg.Input(default_text=size_format(config.speed_limit) if config.speed_limit else '',
                      size=(10, 1), key='speed_limit',
                      disabled=False if config.speed_limit else True, enable_events=True),
             sg.T('0', size=(30, 1), key='current_speed_limit'),
             sg.T('*ex: 512 KB or 5 MB', font='any 8')],
            [sg.T('', font='any 1')],  # spacer
            [sg.Text('Max concurrent downloads:      '),
             sg.Combo(values=[x for x in range(1, 101)], size=(5, 1), enable_events=True,
                      key='max_concurrent_downloads', default_value=config.max_concurrent_downloads)],
            [sg.Text('Max connections per download:'),
             sg.Combo(values=[x for x in range(1, 101)], size=(5, 1), enable_events=True,
                      key='max_connections', default_value=config.max_connections)],
            [sg.T('', font='any 1')],  # spacer
            [sg.Checkbox('Proxy:', default=config.enable_proxy, key='enable_proxy',
                         enable_events=True),
             sg.I(default_text=config.raw_proxy, size=(25, 1), font='any 9', key='raw_proxy',
                  enable_events=True, disabled=not config.enable_proxy),
             sg.T('?', tooltip=proxy_tooltip, pad=(3, 1)),
             sg.Combo(['http', 'https', 'socks4', 'socks5'], default_value=config.proxy_type,
                      font='any 9',
                      enable_events=True, key='proxy_type'),
             sg.T(config.proxy if config.proxy else '_no proxy_', key='current_proxy_value',
                  size=(100, 1), font='any 9'),
             ],
            [sg.T('', font='any 1')],  # spacer

            [sg.Checkbox('Website Auth: ', default=config.use_web_auth, key='use_web_auth', enable_events=True),
             sg.T('    *user/pass will not be saved on disk', font='any 8')],
            [sg.T('        user: '),
             sg.I('', size=(25, 1), key='username', enable_events=True, disabled=not config.use_web_auth)],
            [sg.T('        Pass:'), sg.I('', size=(25, 1), key='password', enable_events=True,
                                         disabled=not config.use_web_auth, password_char='*')],
            [sg.T('', font='any 1')],  # spacer

            [sg.Checkbox('Referee url:', default=config.use_referer, key='use_referer', enable_events=True),
             sg.I(default_text=config.referer_url, size=(60, 1), font='any 9', key='referer_url',
                  enable_events=True, disabled=not config.use_referer)],


        ]

        update = [
            [sg.T(' ', size=(100, 1))],
            [sg.T('Check for update every:'),
             sg.Combo([1, 7, 30], default_value=config.update_frequency, size=(4, 1),
                      key='update_frequency', enable_events=True), sg.T('day(s).')],
            [
                sg.B('', key='update_pyIDM', image_data=refresh_icon, **transparent, tooltip='check for update'),
                sg.T(f'PyIDM version = {config.APP_VERSION}', size=(50, 1), key='pyIDM_version_note'),
            ],
            [
                sg.B('', key='update_youtube_dl', image_data=refresh_icon, **transparent,
                     tooltip=' check for update '),
                sg.T('Youtube-dl version = 00.00.00', size=(50, 1), key='youtube_dl_update_note'),
                sg.B('', key='rollback_ytdl_update', image_data=delete_icon, **transparent,
                     tooltip=' rollback update '),
            ],
            [sg.T('', size=(1, 12))]
        ]

        layout = [
            [sg.T('', size=(70, 1)), ],
            [sg.TabGroup([[sg.Tab('General ', general), sg.Tab('Network', network), sg.Tab('Update  ', update)]],
                         tab_location='lefttop')]
        ]

        return layout

    def create_window(self):
        # main tab layout
        main_layout = self.create_main_tab()

        # downloads tab -----------------------------------------------------------------------------------------
        downloads_layout = self.create_downloads_tab()

        # Settings tab -------------------------------------------------------------------------------------------
        settings_layout = self.create_settings_tab()

        # log tab ------------------------------------------------------------------------------------------------
        log_layout = [[sg.T('Details events:')],
                      [sg.Multiline(default_text='', size=(70, 22), key='log', font='any 8', autoscroll=True)],

                      [sg.T('Log Level:'), sg.Combo([1, 2, 3], default_value=config.log_level, enable_events=True,
                                                    size=(3, 1), key='log_level',
                                                    tooltip='*(1=Standard, 2=Verbose, 3=Debugging)'),
                       sg.T(f'*saved to {config.sett_folder}', font='any 8', size=(75, 1),
                            tooltip=config.current_directory),
                       sg.Button('Clear Log')]]

        layout = [[sg.TabGroup(
            [[sg.Tab('Main', main_layout), sg.Tab('Downloads', downloads_layout), sg.Tab('Settings', settings_layout),
              sg.Tab('Log', log_layout)]],
            key='tab_group')],
            [
             sg.T('', size=(73, 1), relief=sg.RELIEF_SUNKEN, font='any 8', key='status_bar'),
             sg.Text('', size=(10, 1), key='status_code', relief=sg.RELIEF_SUNKEN, font='any 8'),
             sg.T('5 ▼  |  6 ⏳', size=(12, 1), key='active_downloads', relief=sg.RELIEF_SUNKEN, font='any 8', tooltip=' active downloads | pending downloads '),
             sg.T('⬇350 bytes/s', font='any 8', relief=sg.RELIEF_SUNKEN, size=(12, 1), key='total_speed'),
            ]
        ]

        # window
        window = sg.Window(title=config.APP_TITLE, layout=layout, size=(700, 450), margins=(2, 2),
                           return_keyboard_events=True)
        return window

    def start_window(self):
        self.window = self.create_window()
        self.window.Finalize()

        # expand elements to fit
        elements = ['url', 'name', 'folder', 'm_bar', 'pl_menu', 'file_properties', 'update_note',
                    'stream_menu', 'log']  # elements to be expanded
        for e in elements:
            self.window[e].expand(expand_x=True)

        # bind keys events for table, it is tkinter specific
        self.window['table'].Widget.bind("<Button-3>", self.table_right_click)  # right click
        self.window['table'].bind('<Double-Button-1>', '_double_clicked')  # double click
        self.window['table'].bind('<Return>', '_enter_key')  # Enter key

        # log text, disable word wrap
        # use "undo='false'" disable tkinter caching to fix issue #59 "solve huge memory usage and app crash"
        self.window['log'].Widget.config(wrap='none', undo='false')

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
                self.select_row(int(id_) - 1)  # get count start from zero
                self.window['table']._RightClickMenuCallback(event)
        except:
            pass

    def select_row(self, row_num):
        try:
            self.selected_row_num = int(row_num)

            # get instant gui update, don't wait for scheduled update
            self.update_gui()

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
            # file name
            if self.window['name'].get() != self.d.name:  # it will prevent cursor jump to end when modifying name
                self.window['name'](self.d.name)

            file_properties = f'Size: {size_format(self.d.total_size)} - Type: {self.d.type} ' \
                              f'{", ".join(self.d.subtype_list)} - ' \
                              f'Protocol: {self.d.protocol} - Resumable: {"Yes" if self.d.resumable else "No"} ...'
            self.window['file_properties'](file_properties)

            # download list / table
            table_values = [[self.format_cell_data(key, getattr(d, key, '')) for key in self.d_headers] for d in
                            self.d_list]
            self.window.Element('table').Update(values=table_values[:])

            if self.d_list:
                # select first row by default if nothing previously selected
                if not self.selected_row_num:
                    self.selected_row_num = 0

                # re-select the previously selected row in the table
                self.window['table'](select_rows=(self.selected_row_num,))

            # update active and pending downloads
            self.window['active_downloads'](f' {len(self.active_downloads)} ▼  |  {len(self.pending)} ⏳')

            # Settings
            speed_limit = size_format(config.speed_limit) if config.speed_limit > 0 else "_no limit_"
            self.window['current_speed_limit'](f'Current value: {speed_limit}')

            self.window['youtube_dl_update_note'](
                f'Youtube-dl version = {config.ytdl_VERSION}, Latest version = {config.ytdl_LATEST_VERSION}')
            self.window['pyIDM_version_note'](
                f'PyIDM version = {config.APP_VERSION}, Latest version = {config.APP_LATEST_VERSION}')

            # update total speed
            total_speed = 0
            for i in self.active_downloads:
                d = self.d_list[i]
                total_speed += d.speed
            self.window['total_speed'](f'⬇ {size_format(total_speed, "/s")}')

            # thumbnail
            if self.video:
                if self.video.thumbnail:
                    self.show_thumbnail(thumbnail=self.video.thumbnail)
                else:
                    self.reset_thumbnail()

            # update selected download item's preview panel in downloads tab
            d = self.selected_d

            if d:
                speed = f"Speed: {size_format(d.speed, '/s') }  {time_format(d.time_left)} left" if d.speed else ''
                out = f"#{self.selected_row_num + 1}: {d.name}\n" \
                      f"Downloaded: {size_format(d.downloaded)} of {size_format(d.total_size)}\n" \
                      f"{speed} \n" \
                      f"Live connections: {d.live_connections} - Remaining parts: {d.remaining_parts}\n" \
                      f"{d.status}  {d.i}"

                # thumbnail
                if config.show_thumbnail and d.thumbnail:
                    self.window['si_thumbnail'](data=d.thumbnail)
                else:
                    self.window['si_thumbnail'](data=thumbnail_icon)

            else:
                out = f"File:\n" \
                      f"Downloaded:\n" \
                      f"Speed: \n" \
                      f"Live connections: \n" \
                      f"Status:"
                self.window['si_thumbnail'](data=thumbnail_icon)

            self.window['si_out'](out)
            self.window['si_bar'].update_bar(d.progress if d else 0)
            self.window['si_percent'](f'{d.progress}%' if d else '')

            # animate side bar
            if self.animate_bar and self.s_bar < 90:
                self.s_bar += 10

            # stop animate side bar
            if self.video and self.video.processed:
                self.s_bar = 100
                self.animate_bar = False

            # update stream menu
            if self.video and self.stream_menu != self.video.stream_menu:
                self.update_stream_menu()

        except Exception as e:
            log('MainWindow.update_gui() error:', e)

    def enable(self):
        self.disabled = False

    def disable(self):
        self.disabled = True

    def set_status(self, text):
        """update status bar text widget"""
        try:
            self.window['status_bar'](text)

            # reset timer, used to clear status bar
            self.statusbar_timer = time.time()
        except:
            pass

    def change_theme(self):
        # theme
        sg.ChangeLookAndFeel(config.current_theme)

        # transparent color for button which mimic current background, will be use as a parameter, ex. **transparent
        global transparent
        transparent = dict(button_color=('black', sg.theme_background_color()), border_width=0)

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

            # keyboard events ---------------------------------------------------
            if event.startswith('Up:'): # up arrow example "Up:38"
                # get current element with focus
                focused_elem = self.window.find_element_with_focus()

                # for table, change selected row
                if self.window['table'] == focused_elem and self.selected_row_num > 0:
                    self.select_row(self.selected_row_num - 1)

            if event.startswith('Down:'):  # down arrow example "Down:40"
                # get current element with focus
                focused_elem = self.window.find_element_with_focus()

                # for table, change selected row
                if self.window['table'] == focused_elem and self.selected_row_num < len(self.window['table'].Values)-1:
                    self.select_row(self.selected_row_num + 1)

            # Mouse events MouseWheel:Up, MouseWheel:Down -----------------------
            if event == 'MouseWheel:Up':
                pass
            if event == 'MouseWheel:Down':
                pass

            # Main Tab ----------------------------------------------------------------------------------------
            elif event == 'update_note':
                # if clicked on update notification text
                if self.new_version_available:
                    self.update_app(remote=False)

            elif event == 'url':
                self.url_text_change()

            elif event == 'copy url':
                url = values['url']
                if url:
                    clipboard_write(url)

            elif event == 'paste url':
                self.window['url'](clipboard_read().strip())
                self.url_text_change()

            # video events
            elif event == 'pl_download':
                self.window['pl_download'](disabled=True)
                self.download_playlist()
                self.window['pl_download'](disabled=False)

            elif event == 'pl_menu':
                self.playlist_OnChoice(values['pl_menu'])

            elif event == 'stream_menu':
                self.stream_OnChoice(values['stream_menu'])

            elif event == 'subtitles':
                try:
                    self.download_subtitles()
                except Exception as e:
                    log('download_subtitles()> error', e)

            elif event == 'Download':
                self.download_btn()

            elif event == 'folder':
                if values['folder']:
                    config.download_folder = os.path.abspath(values['folder'])
                else:  # in case of empty entries
                    self.window.Element('folder').Update(config.download_folder)

            elif event == 'name':
                self.d.name = validate_file_name(values['name'])

            elif event == 'Retry':
                self.retry()

            # downloads tab events -----------------------------------------------------------------------------------
            elif event == 'table':
                # todo: investigate this event keeps triggering
                # I think because update_gui() keeps updating table contents, it will trigger 'table' event continuously

                try:
                    row_num = values['table'][0]
                    if row_num != self.selected_row_num:  # this is a must here otherwise application will freeze [bug]
                        self.select_row(row_num)
                except Exception as e:
                    # log("MainWindow.run:if event == 'table': ", e)
                    pass

            elif event in ('table_double_clicked', 'table_enter_key', 'Open File', '▶ Watch while downloading') and \
                    self.selected_d:
                if self.selected_d.status == Status.completed:
                    open_file(self.selected_d.target_file)
                else:
                    open_file(self.selected_d.temp_file)

            # table right click menu event
            elif event == 'Open File Location':
                self.open_file_location()

            elif event == 'copy webpage url':
                clipboard_write(self.selected_d.url)

            elif event == 'copy download url':
                clipboard_write(self.selected_d.eff_url)

            elif event == 'properties':
                # right click properties
                try:
                    d = self.selected_d

                    if d:
                        text = f'Name: {d.name} \n' \
                               f'Folder: {d.folder} \n' \
                               f'Progress: {d.progress}% \n' \
                               f'Downloaded: {size_format(d.downloaded)} \n' \
                               f'Total size: {size_format(d.total_size)} \n' \
                               f'Status: {d.status} \n' \
                               f'Resumable: {d.resumable} \n' \
                               f'Type: {d.type} \n' \
                               f'Protocol: {d.protocol} \n' \
                               f'Webpage url: {d.url}'

                        sg.popup_scrolled(text, title='File properties')
                except Exception as e:
                    log('gui> properties>', e)

            elif event == '⏳ Schedule download':
                print('schedule clicked')
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
                if self.selected_d:
                    if config.auto_close_download_window and self.selected_d.status != Status.downloading:
                        sg.Popup('To open download window offline \n'
                                 'go to setting tab, then uncheck "auto close download window" option', title='info')
                    else:
                        d = self.selected_d
                        if d.id not in [win.d.id for win in self.active_windows]:
                            self.active_windows.append(DownloadWindow(d=d))
                        else:
                            win = [win for win in self.active_windows if win.d.id == d.id][0]
                            win.focus()

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

            # Settings tab -------------------------------------------------------------------------------------------
            elif event == 'about':  # about window
                self.window['about'](visible=False)
                sg.PopupOK(about_notes, title=f'About {config.APP_NAME}', keep_on_top=True)
                self.window['about'](visible=True)

            elif event == 'themes':
                config.current_theme = values['themes']
                self.change_theme()

                # close all active windows
                for win in self.active_windows:
                    win.window.Close()
                self.active_windows.clear()

                self.restart_window()
                self.select_tab('Settings')

            elif event == 'show_thumbnail':
                config.show_thumbnail = values['show_thumbnail']

                self.reset_thumbnail()

            elif event == 'monitor':
                config.monitor_clipboard = values['monitor']

            elif event == 'show_download_window':
                config.show_download_window = values['show_download_window']

            elif event == 'auto_close_download_window':
                config.auto_close_download_window = values['auto_close_download_window']

            elif event == 'process_big_playlist_on_demand':
                config.process_big_playlist_on_demand = values['process_big_playlist_on_demand']

            elif event == 'manually_select_dash_audio':
                config.manually_select_dash_audio = values['manually_select_dash_audio']

            elif event == 'segment_size':
                user_input = values['segment_size']

                # if no units entered will assume it KB
                try:
                    _ = int(user_input)  # will succeed if it has no string
                    user_input = f'{user_input} KB'
                except:
                    pass

                seg_size = parse_bytes(user_input)

                # set non valid values or zero to default
                if not seg_size:
                    seg_size = config.DEFAULT_SEGMENT_SIZE

                config.segment_size = seg_size
                self.window['seg_current_value'](f'current value: {size_format(config.segment_size)}')
                self.d.segment_size = seg_size

            elif event == 'sett_folder':
                selected = values['sett_folder']
                if selected == 'Local':
                    # choose local folder as a Settings folder
                    config.sett_folder = config.current_directory

                    # remove setting.cfg from global folder
                    delete_file(os.path.join(config.global_sett_folder, 'setting.cfg'))
                else:
                    # choose global folder as a setting folder
                    config.sett_folder = config.global_sett_folder

                    # remove setting.cfg from local folder
                    delete_file(os.path.join(config.current_directory, 'setting.cfg'))

                    # create global folder settings if it doesn't exist
                    if not os.path.isdir(config.global_sett_folder):
                        try:
                            choice = sg.popup_ok_cancel(f'folder: {config.global_sett_folder}\n'
                                                        f'will be created')
                            if choice != 'OK':
                                raise Exception('Operation Cancelled by User')
                            else:
                                os.mkdir(config.global_sett_folder)

                        except Exception as e:
                            log('global setting folder error:', e)
                            config.sett_folder = config.current_directory
                            sg.popup(f'Error while creating global settings folder\n'
                                     f'"{config.global_sett_folder}"\n'
                                     f'{str(e)}\n'
                                     f'local folder will be used instead')
                            self.window['sett_folder']('Local')
                            self.window['sett_folder_text'](config.sett_folder)

                # update display widget
                try:
                    self.window['sett_folder_text'](config.sett_folder)
                except:
                    pass

            # network------------------------------------------------
            elif event == 'speed_limit_switch':
                switch = values['speed_limit_switch']

                if switch:
                    self.window['speed_limit'](disabled=False)
                else:
                    config.speed_limit = 0
                    self.window['speed_limit']('', disabled=True)  # clear and disable

            elif event == 'speed_limit':
                sl = values['speed_limit']

                # if no units entered will assume it KB
                try:
                    _ = int(sl)  # will succeed if it has no string
                    sl = f'{sl} KB'
                except:
                    pass

                sl = parse_bytes(sl)
                config.speed_limit = sl

            elif event == 'max_concurrent_downloads':
                config.max_concurrent_downloads = int(values['max_concurrent_downloads'])

            elif event == 'max_connections':
                mc = int(values['max_connections'])
                if mc > 0:
                    config.max_connections = mc

            elif event in ('raw_proxy', 'http', 'https', 'socks4', 'socks5', 'proxy_type', 'enable_proxy'):
                self.set_proxy()

            elif event in ('use_referer', 'referer_url'):
                config.use_referer = values['use_referer']
                if config.use_referer:
                    self.window['referer_url'](disabled=False)
                    config.referer_url = self.window['referer_url'].get()
                else:
                    self.window['referer_url'](disabled=True)
                    config.referer_url = ''

            elif event in ('username', 'password', 'use_web_auth'):
                if values['use_web_auth']:
                    # enable widgets
                    self.window['username'](disabled=False)
                    self.window['password'](disabled=False)

                    config.username = values['username']
                    config.password = values['password']
                else:
                    config.username = ''
                    config.password = ''

                    # disable widgets
                    self.window['username'](disabled=True)
                    self.window['password'](disabled=True)

                # log('user, pass:', config.username, config.password)

            # update -------------------------------------------------
            elif event == 'update_frequency':
                selected = values['update_frequency']
                config.update_frequency = selected  # config.update_frequency_map[selected]

            elif event == 'update_youtube_dl':
                self.update_ytdl()

            elif event == 'rollback_ytdl_update':
                Thread(target=update.rollback_ytdl_update).start()
                self.select_tab('Log')

            elif event in ['update_pyIDM']:
                Thread(target=self.update_app, daemon=True).start()

            # log ---------------------------------------------------------------------------------------------------
            elif event == 'log_level':
                config.log_level = int(values['log_level'])
                log('Log Level changed to:', config.log_level)

            elif event == 'Clear Log':
                try:
                    self.window['log']('')
                except:
                    pass

            # Run every n seconds -----------------------------------------------------------------------------------
            if time.time() - timer1 >= 0.5:
                timer1 = time.time()

                # gui update
                self.update_gui()

                # read incoming requests and messages from queue
                self.read_q()

                # scheduled downloads
                self.check_scheduled()

                # process pending jobs
                if self.pending and len(self.active_downloads) < config.max_concurrent_downloads:
                    self.start_download(self.pending.popleft(), silent=True)

            # run active windows
            for win in self.active_windows:
                win.run()
            self.active_windows = [win for win in self.active_windows if win.active]  # update active list

            # run one time, reason this is here not in setup, is to minimize gui loading time
            if one_time:
                one_time = False
                
                # check availability of ffmpeg in the system or in same folder with this script
                self.ffmpeg_check()

                # check_for_update
                t = time.localtime()
                today = t.tm_yday  # today number in the year range (1 to 366)

                try:
                    days_since_last_update = today - config.last_update_check
                    log('days since last check for update:', days_since_last_update, 'day(s).')

                    if days_since_last_update >= config.update_frequency:
                        Thread(target=self.check_for_update, daemon=True).start()
                        Thread(target=self.check_for_ytdl_update, daemon=True).start()
                        config.last_update_check = today
                except Exception as e:
                    log('MainWindow.run()>', e)

            if time.time() - timer2 >= 1:
                timer2 = time.time()
                # update notification
                if self.new_version_available:
                    self.animate_update_note()
                else:
                    self.window['update_note']('')

            # reset statusbar periodically
            if time.time() - self.statusbar_timer >= 10:
                self.statusbar_timer = time.time()
                self.set_status('')

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

            # update status code widget
            try:
                self.window['status_code'](f'status: {self.d.status_code}')
            except:
                pass

            # enable download button
            if self.d.status_code not in self.bad_headers and self.d.type != 'text/html':
                self.enable()

            # check if the link contains stream videos by youtube-dl
            Thread(target=self.youtube_func, daemon=True).start()
        self.change_cursor('default')

    # endregion

    # region download
    @property
    def active_downloads(self):
        # update active downloads
        _active_downloads = set(d.id for d in self.d_list if d.status == config.Status.downloading)
        config.active_downloads = _active_downloads

        return _active_downloads

    def start_download(self, d, silent=False, downloader=None):
        """
        Receive a DownloadItem and pass it to brain
        :param bool silent: True or False, show a warninig dialogues
        :param DownloadItem d: DownloadItem() object
        :param downloader: name of alternative  downloader
        """

        if d is None:
            return

        # check for ffmpeg availability in case this is a dash video
        if 'dash' in d.subtype_list or 'hls' in d.subtype_list:
            # log('Dash video detected')
            if not self.ffmpeg_check():
                log('Download cancelled, FFMPEG is missing')
                return 'cancelled'

        # validate destination folder for existence and permissions
        # in case of missing download folder value will fallback to current download folder
        folder = d.folder or config.download_folder
        try:
            with open(os.path.join(folder, 'test'), 'w') as test_file:
                test_file.write('0')
            os.unlink(os.path.join(folder, 'test'))

            # update download item
            d.folder = folder
        except FileNotFoundError:
            sg.Popup(f'destination folder {folder} does not exist', title='folder error')
            return 'error'
        except PermissionError:
            sg.Popup(f"you don't have enough permission for destination folder {folder}", title='folder error')
            return 'error'
        except Exception as e:
            sg.Popup(f'problem in destination folder {repr(e)}', title='folder error')
            return 'error'

        # validate file name
        if d.name == '':
            sg.popup("File name can't be empty!!", title='invalid file name!!')
            return 'error'

        # check if file with the same name exist in destination
        if os.path.isfile(d.target_file):
            #  show dialogue
            msg = 'File with the same name already exist in ' + d.folder + '\n Do you want to overwrite file?'
            response = sg.PopupYesNo(msg)

            if response != 'Yes':
                log('Download cancelled by user')
                return 'cancelled'
            else:
                delete_file(d.target_file)

        # ------------------------------------------------------------------
        # search current list for previous item with same name, folder
        found_index = self.file_in_d_list(d.target_file)
        if found_index is not None:  # might be zero, file already exist in d_list
            log('download item', d.num, 'already in list, check resume availability')
            # get download item from the list
            d_from_list = self.d_list[found_index]
            d.id = d_from_list.id

            # default
            response = 'Resume'

            if not silent:
                #  show dialogue
                msg = f'File with the same name: \n{self.d.name},\n already exist in download list\n' \
                      'Do you want to resume this file?\n' \
                      'Resume ==> continue if it has been partially downloaded ... \n' \
                      'Overwrite ==> delete old downloads and overwrite existing item... \n' \
                      'note: "if you need fresh download, you have to change file name \n' \
                      'or target folder or delete same entry from download list'
                window = sg.Window(title='', layout=[[sg.T(msg)], [sg.B('Resume'), sg.B('Overwrite'), sg.B('Cancel')]])
                response, _ = window()
                window.close()

            #
            if response == 'Resume':
                log('check resuming?')

                # to resume, size must match, otherwise it will just overwrite
                if d.size == d_from_list.size and d.selected_quality == d_from_list.selected_quality:
                    log('resume is possible')
                    # get the same segment size
                    d.segment_size = d_from_list.segment_size
                    d.downloaded = d_from_list.downloaded
                else:
                    log('file:', d.name, 'has different properties and will be downloaded from beginning')
                    d.delete_tempfiles()

                # replace old item in download list
                self.d_list[found_index] = d

            elif response == 'Overwrite':
                log('overwrite')
                d.delete_tempfiles()

                # replace old item in download list
                self.d_list[found_index] = d

            else:
                log('Download cancelled by user')
                d.status = Status.cancelled
                return 'cancelled'

        # ------------------------------------------------------------------

        else:  # new file
            print('new file')
            # generate unique id number for each download
            d.id = len(self.d_list)

            # add to download list
            self.d_list.append(d)

        # if max concurrent downloads exceeded, this download job will be added to pending queue
        if len(self.active_downloads) >= config.max_concurrent_downloads:
            d.status = Status.pending
            self.pending.append(d)
            return

        # start downloading
        if config.show_download_window and not silent:
            # create download window and append to active list
            self.active_windows.append(DownloadWindow(d))

        # create and start brain in a separate thread
        Thread(target=brain, daemon=True, args=(d, downloader)).start()

        # select row in downloads table
        self.select_row(d.id)

    def stop_all_downloads(self):
        # change status of pending items to cancelled
        for d in self.d_list:
            d.status = Status.cancelled

        self.pending.clear()

    def resume_all_downloads(self):
        # change status of all non completed items to pending
        for d in self.d_list:
            if d.status == Status.cancelled:
                self.start_download(d, silent=True)

    def file_in_d_list(self, target_file):
        for i, d in enumerate(self.d_list):
            if d.target_file == target_file:
                return i
        return None

    def download_btn(self, downloader=None):

        if self.disabled:
            sg.popup_ok('Nothing to download', 'it might be a web page or invalid url link',
                        'check your link or click "Retry"')
            return

        # make sure video streams loaded successfully before start downloading
        if self.video and not self.video.stream_list:
            if 0 < self.m_bar < 100:
                msg = 'Video still loading streams, \nplease wait until loading and select a proper video quality'
            else:
                msg = 'Video does not have any streams, and can not be downloaded'

            sg.PopupOK(msg)
            return

        # get copy of current download item
        d = copy.copy(self.d)
        d.folder = config.download_folder

        # dash audio
        if 'dash' in d.subtype_list and config.manually_select_dash_audio:
            # manually select dash audio
            self.select_dash_audio()

        r = self.start_download(d, downloader=downloader)

        if r not in ('error', 'cancelled', False):
            self.select_tab('Downloads')

    # endregion

    # region downloads tab
    @property
    def selected_d(self):
        self._selected_d = self.d_list[self.selected_row_num] if self.selected_row_num is not None else None
        return self._selected_d

    @selected_d.setter
    def selected_d(self, value):
        self._selected_d = value

    @staticmethod
    def format_cell_data(k, v):
        """take key, value and prepare it for display in cell"""
        if k in ['size', 'total_size', 'downloaded']:
            v = size_format(v)
        elif k == 'speed':
            v = size_format(v, '/s')
        elif k in ('percent', 'progress'):
            v = f'{v}%' if v else '---'
        elif k == 'time_left':
            v = time_format(v)
        elif k == 'resumable':
            v = 'yes' if v else 'no'
        elif k == 'name':
            v = validate_file_name(v)

        return v

    def resume_btn(self):
        if self.selected_row_num is None:
            return

        # print_object(self.selected_d)

        self.start_download(self.selected_d, silent=True)

    def cancel_btn(self):
        if self.selected_row_num is None:
            return

        d = self.selected_d
        if d.status == Status.completed:
            return

        d.status = Status.cancelled

        if d.status == Status.pending:
            self.pending.pop(d.id)

    def delete_btn(self):
        if self.selected_row_num is None:
            return

        # todo: should be able to delete items anytime by making download item id unique and number changeable
        # abort if there is items in progress or paused
        if self.active_downloads:
            msg = "Can't delete items while downloading.\nStop or cancel all downloads first!"
            sg.Popup(msg)
            return

        # confirm to delete
        msg = f"Warning!!!\nAre you sure you want to delete!\n{self.selected_d.name}\n"
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
                if self.selected_row_num > last_num:
                    self.selected_row_num = last_num

            # delete temp folder on disk
            d.delete_tempfiles()

        except:
            pass

    def delete_all_downloads(self):
        # abort if there is items in progress or paused
        if self.active_downloads:
            msg = "Can't delete items while downloading.\nStop or cancel all downloads first!"
            sg.Popup(msg)
            return

        # warning / confirmation dialog, user has to write ok to proceed
        msg = 'Delete all items and their progress temp files\n' \
              'Type the word "delete" and hit ok\n'
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

        # delete temp files
        for i in range(n):
            d = self.d_list[i]
            Thread(target=d.delete_tempfiles, daemon=True).start()

        self.d_list.clear()

    def open_file_location(self):
        if self.selected_row_num is None:
            return

        d = self.selected_d

        try:
            folder = os.path.abspath(d.folder)
            file = d.target_file

            if config.operating_system == 'Windows':
                if not os.path.isfile(file):
                    os.startfile(folder)
                else:
                    cmd = f'explorer /select, "{file}"'
                    run_command(cmd)
            else:
                # linux
                cmd = f'xdg-open "folder"'
                # os.system(cmd)
                run_command(cmd)
        except Exception as e:
            handle_exceptions(e)

    def refresh_link_btn(self):
        if self.selected_row_num is None:
            return

        d = self.selected_d
        config.download_folder = d.folder

        self.window['url'](d.url)
        self.url_text_change()

        self.window['folder'](config.download_folder)
        self.select_tab('Main')

    # endregion

    # region video

    @property
    def m_bar(self):
        """playlist progress bar"""
        return self._m_bar

    @m_bar.setter
    def m_bar(self, value):
        """playlist progress bar"""
        self._m_bar = value if value <= 100 else 100
        try:
            self.window['m_bar'].UpdateBar(value)
        except:
            pass

    @property
    def s_bar(self):
        """playlist progress bar"""
        return self._s_bar

    @s_bar.setter
    def s_bar(self, value):
        """playlist progress bar"""
        self._s_bar = value if value <= 100 else 100
        try:
            self.window['s_bar'].UpdateBar(value)
        except:
            pass

    @property
    def pl_menu(self):
        """video playlist menu"""
        return self._pl_menu

    @pl_menu.setter
    def pl_menu(self, rows):
        """video playlist menu"""
        self._pl_menu = rows
        try:
            self.window['pl_menu'](values=rows)
        except:
            pass

    @property
    def stream_menu(self):
        """video streams menu"""
        return self._stream_menu

    @stream_menu.setter
    def stream_menu(self, rows):
        """video streams menu"""
        self._stream_menu = rows
        try:
            self.window['stream_menu'](values=rows)
        except:
            pass

    def reset_video_controls(self):
        try:
            self.reset_progress_bar()
            self.pl_menu = ['Playlist']
            self.stream_menu = ['Video quality']
            self.window['playlist_frame'](value='Playlist/video:')
            self.window['format_code']('')

            # reset thumbnail
            self.reset_thumbnail()

            # animate bar
            self.animate_bar = False
        except:
            pass

    def reset_progress_bar(self):
        self.m_bar = 0
        self.animate_bar = False
        self.s_bar = 0

    def reset_thumbnail(self):
        """show a blank thumbnail background"""
        self.show_thumbnail(thumbnail=None)

    def show_thumbnail(self, thumbnail=None):
        """show video thumbnail in thumbnail image widget in main tab, call without parameter reset thumbnail"""

        try:
            if thumbnail is None:
                # reset thumbnail
                self.window['main_thumbnail'](data=thumbnail_icon)

            elif thumbnail != self.current_thumbnail and config.show_thumbnail:
                # new thumbnail
                self.window['main_thumbnail'](data=thumbnail)

            self.current_thumbnail = thumbnail
        except Exception as e:
            log('show_thumbnail()>', e)

    def youtube_func(self):
        """fetch metadata from youtube and other stream websites"""

        def cancel_flag():
            # quit if main window terminated
            if config.terminate:
                return True

            # quit if url changed by user
            if url != self.url:
                self.reset_video_controls()
                self.reset()
                log('youtube func: quitting, url changed by user')
                return True

            # quit if new youtube func thread started
            if yt_id != self.yt_id:
                log('youtube func: quitting, new instance has started')
                return True

            else:
                return False

        # getting videos from youtube is time consuming, if another thread starts, it should cancel the previous one
        # create unique identification for this thread
        self.yt_id += 1 if self.yt_id < 1000 else 0
        yt_id = self.yt_id
        url = self.d.url

        msg = f'looking for video streams ... Please wait'
        log(msg)
        log('youtube_func()> processing:', self.d.url)

        # reset video controls
        self.reset_video_controls()

        # main progress bar initial indication
        self.m_bar = 10
        self.change_cursor('busy')

        # reset playlist
        self.playlist = []

        # check cancel flag
        if cancel_flag(): return

        try:
            # we import youtube-dl in separate thread to minimize startup time, will wait in loop until it gets imported
            if video.ytdl is None:
                log('youtube-dl module still not loaded completely, please wait')
                while not video.ytdl:
                    time.sleep(0.1)  # wait until module gets imported

            # youtube-dl process
            timer1 = time.time()
            log(get_ytdl_options())
            with video.ytdl.YoutubeDL(get_ytdl_options()) as ydl:
                # process=False is faster and youtube-dl will not download every videos webpage in the playlist
                info = ydl.extract_info(self.d.url, download=False, process=False)
                log('Media info:', info, log_level=3)

                # set playlist / video title
                self.pl_title = info.get('title', '')

                # 50% done
                self.m_bar = 50

                # check results if _type is a playlist / multi_video
                if info.get('_type') == 'playlist' or 'entries' in info:
                    log('youtube-func()> start processing playlist')

                    # videos info
                    pl_info = list(info.get('entries'))

                    # create initial playlist with un-processed video objects
                    for num, item in enumerate(pl_info):
                        item['formats'] = []
                        vid = Video(item.get(url, ''), item)
                        vid.playlist_title = info.get('title', '')
                        vid.playlist_url = self.url
                        self.playlist.append(vid)

                    # increment to media progressbar to complete last 50%
                    playlist_length = len(self.playlist)
                    m_bar_incr = 50 / playlist_length

                    # update playlist title widget: show how many videos
                    self.window['playlist_frame'](
                        value=f'Playlist ({playlist_length} {"videos" if playlist_length > 1 else "video"}):')

                    # update playlist menu, only videos names, there is no videos qualities yet
                    self.update_pl_menu()

                    # user notification for big playlists
                    if playlist_length > config.big_playlist_length and config.process_big_playlist_on_demand:
                        popup(f'Big playlist detected with {playlist_length} videos \n'
                              f'To avoid wasting time and resources, videos info will be processed only when \n'
                              f'selected in main Tab or playlist window\n\n'
                              f'You can override this behaviour and fetch all videos information in advance by \n'
                              f'disabling "process big playlist info on demand" option in settings\n',
                              title='big playlist detected')

                    # process videos info
                    num = 0
                    v_threads = []
                    processed_videos = 0

                    if self.playlist:
                        while True:
                            # big playlist
                            if config.process_big_playlist_on_demand and playlist_length > config.big_playlist_length:
                                break

                            time.sleep(0.01)

                            # create threads
                            if processed_videos < playlist_length:
                                t = Thread(target=process_video_info, daemon=True, args=(self.playlist[num],))
                                v_threads.append(t)
                                t.start()
                                print('processed video:', num + 1)
                                processed_videos += 1

                            # check for finished threads
                            for t in v_threads[:]:
                                if not t.is_alive():
                                    v_threads.pop()
                                    self.m_bar += m_bar_incr

                            # check cancel flag
                            if cancel_flag():
                                return

                            # check if done
                            if processed_videos == playlist_length and not v_threads:
                                break

                            if num < playlist_length - 1:
                                num += 1

                else:
                    # one video, not a playlist, processing info
                    vid = Video(self.d.url, vid_info=info)
                    self.playlist = [vid]
                    # process_video_info(vid)  # will be called from playlist_on_choice()

                    # update playlist menu
                    self.update_pl_menu()

            # quit if we couldn't extract any videos info (playlist or single video)
            if not self.playlist:
                self.reset()
                log('youtube func: quitting, can not extract videos')
                return

            # check cancel flag
            if cancel_flag(): return

            # enable download button
            self.enable()

            # job completed
            self.m_bar = 100
            log(f'youtube_func()> done fetching information in {round(time.time() - timer1, 1)} seconds .............')

        except Exception as e:
            log('youtube_func()> error:', e)
            self.reset_video_controls()

        finally:
            self.change_cursor('default')

    def update_pl_menu(self):
        try:
            # set playlist label
            num = len(self.playlist)

            self.window['playlist_frame'](value=f'Playlist ({num} {"videos" if num > 1 else "video"}):')

            # update playlist menu items
            self.pl_menu = [str(i + 1) + '- ' + video.title for i, video in enumerate(self.playlist)]

            # choose first item in playlist by triggering playlist_onchoice
            self.playlist_OnChoice(self.pl_menu[0])
        except Exception as e:
            log('update_pl_menu()> error', e)

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

        try:
            index = self.pl_menu.index(selected_text)
            self.video = self.playlist[index]

            # set current download item as self.video
            self.d = self.video

            self.update_stream_menu()

            # instant widgets update
            self.update_gui()

            # fetch video info if not available and animate side bar
            if self.video and not self.video.processed:
                self.s_bar = 0
                self.animate_bar = True  # let update_gui() start a fake progress

                # process video
                Thread(target=process_video_info, daemon=True, args=(self.video, )).start()
            else:
                self.s_bar = 100
                self.animate_bar = False

        except Exception as e:
            log('playlist_OnChoice()> error', e)

    def stream_OnChoice(self, selected_text):

        try:
            self.stream_menu_selection = selected_text
            self.video.selected_stream = self.video.streams[selected_text]

            # display format code
            self.window['format_code']('Format code: ' + self.video.selected_stream.format_id + ' - ' +
                                       self.video.selected_stream.format_note)

            # update gui
            self.update_gui()
        except:
            pass

    def download_playlist(self):
        # check if playlist is ready
        if not self.playlist:
            sg.popup_ok('Playlist is empty, nothing to download :(', title='Playlist download')
            return

        # technical limitation of tkinter, can not show more than 1000 item without glitches, or pl_window will not show
        if len(self.playlist) > 1000:
            sg.popup_ok('Playlist is more than 1000 videos, \n'
                        'due to technical limitations will show only first 1000 videos', title='Playlist download')
            playlist = self.playlist[:1000]
        else:
            playlist = self.playlist

        # fix repeated video names in playlist --------------------------------------------------------------------
        vid_names = []
        for num, vid in enumerate(playlist):
            if vid.name in vid_names:
                name, ext = os.path.splitext(vid.name)
                name = f'{name}_{num}{ext}'
                vid.name = name

            vid_names.append(vid.name)
        del vid_names  # no longer needed, free memory

        # prepare a list for master stream menu, --------------------------------------------------------------------
        mp4_videos = {}
        other_videos = {}
        audio_streams = {}

        # will use raw stream names which doesn't include size ex: {quality: raw_name}
        for video in playlist:
            mp4_videos.update({stream.quality: stream.raw_name for stream in video.mp4_videos.values()})
            other_videos.update({stream.quality: stream.raw_name for stream in video.other_videos.values()})
            audio_streams.update({stream.quality: stream.raw_name for stream in video.audio_streams.values()})

        # make lists of raw names,  sorted list of "stream qualities" starting with higher values
        mp4_list = [mp4_videos[x] for x in sorted(mp4_videos.keys(), reverse=True)]
        other_list = [other_videos[x] for x in sorted(other_videos.keys(), reverse=True)]
        audio_list = [audio_streams[x] for x in sorted(audio_streams.keys(), reverse=True)]

        master_stream_menu = ['● Video streams:                     '] + mp4_list + other_list + \
                             ['', '● Audio streams:                 '] + audio_list

        # gui layout ------------------------------------------------------------------------------------------------
        video_checkboxes = []
        progress_bars = []
        stream_combos = []

        general_options_layout = [sg.Checkbox('Select All', enable_events=True, key='Select All'),
                                  sg.T('', size=(15, 1)),
                                  sg.T('Choose quality for all videos:'),
                                  sg.Combo(values=master_stream_menu, default_value=master_stream_menu[0], size=(28, 1),
                                           key='master_stream_combo', enable_events=True)]

        video_layout = []

        # build layout widgets
        for num, video in enumerate(playlist):
            # set selected stream
            if video.stream_list:
                video.selected_stream = video.stream_list[0]

            # video names with check boxes
            video_checkbox = sg.Checkbox(truncate(video.title, 65), size=(65, 1), tooltip=video.title, font='any 8',
                                         key=f'video {num}', enable_events=True)
            video_checkboxes.append(video_checkbox)

            # hidden progress bars works only while loading streams
            progress_bar = sg.ProgressBar(100, size=(10, 5), pad=(5, 1), key=f'bar {num}')
            progress_bars.append(progress_bar)

            # streams / quality menu
            stream_combo = sg.Combo(values=video.raw_stream_menu, default_value=video.raw_stream_menu[1], font='any 8',
                                    size=(22, 1), key=f'stream {num}', enable_events=True, pad=(5, 0))
            stream_combos.append(stream_combo)

            # build one row from the above
            row = [video_checkbox, sg.Col([[stream_combo], [progress_bar]]),
                   sg.T(size_format(video.total_size), size=(10, 1), font='any 8', key=f'size_text {num}')]

            # add row to video_layout
            video_layout.append(row)

        video_layout = [sg.Column(video_layout, scrollable=True, vertical_scroll_only=True, size=(650, 250), key='col')]

        layout = [
            [sg.T(f'Total Videos: {len(playlist)}')],
            general_options_layout,
            [sg.T('*note: select videos first to load streams menu if not available!!', font='any 8')],
            [sg.Frame(title='Videos:', layout=[video_layout])],
            [sg.Col([[sg.OK(), sg.Cancel()]], justification='right')]
        ]

        # create window ---------------------------------------------------------------------------------------------
        window = sg.Window(title='Playlist download window', layout=layout, finalize=True, margins=(2, 2))

        # set progress bar properties
        for bar in progress_bars:
            bar.Widget.config(mode='indeterminate')
            bar.expand(expand_x=True)

        chosen_videos = []
        active_threads = {}  # {video.name: thread}

        def update_video(num):
            # update some parameters for a selected video
            video = playlist[num]
            stream_widget = window[f'stream {num}']
            video_checkbox = window[f'video {num}']
            size_widget = window[f'size_text {num}']

            selected = video_checkbox.get()
            stream_text = stream_widget.get()

            # process video
            if selected and not video.processed and not active_threads.get(video.name, None):
                t = Thread(target=process_video_info, daemon=True, args=(video,))
                active_threads[video.name] = t
                t.start()

            # first check if video has streams
            if not video.stream_list:
                return

            # correct chosen stream values
            if stream_text not in video.raw_stream_names:
                stream_widget(video.selected_stream.raw_name)
            else:
                video.selected_stream = video.raw_streams[stream_text]

            size_widget(size_format(video.size))

        # event loop -------------------------------------------------------------------------------------------------
        while True:
            event, values = window.read(timeout=100)
            if event in (None, 'Cancel'):
                window.close()
                return

            if event == 'OK':
                chosen_videos.clear()
                null_videos = []
                for num, video in enumerate(playlist):
                    # check if video is selected
                    if values[f'video {num}'] is True:

                        # get selected text from stream menu
                        selected_text = values[f'stream {num}']

                        # get selected stream
                        selected_stream = video.raw_streams.get(selected_text, None)

                        # check if video has streams or not
                        if not selected_stream:
                            null_videos.append(video.name)
                        else:
                            video.selected_stream = selected_stream

                            # append to chosen videos list
                            chosen_videos.append(video)
                            # print('video.selected_stream:', video.selected_stream)
                if null_videos:
                    vid_names = "\n".join(null_videos)
                    sg.popup_ok(f'videos: \n'
                                f'{vid_names}\n'
                                f'have no streams, please wait until finish loading '
                                f'or un-select this video and try again')
                else:
                    window.close()
                    break

            elif event == 'Select All':
                checked = values['Select All']

                # process all other check boxes
                for num, checkbox in enumerate(video_checkboxes):
                    checkbox(checked)
                    update_video(num)

            elif event == 'master_stream_combo':
                selected_text = values['master_stream_combo']
                # if True:  # selected_text in raw_streams:

                # update all videos stream menus from master stream menu
                for num, stream_combo in enumerate(stream_combos):
                    video = playlist[num]
                    if selected_text in video.raw_streams:
                        stream_combo(selected_text)
                        update_video(num)
                        # video.selected_stream = video.raw_streams[selected_text]
                        # window[f'size_text {num}'](size_format(video.size))

            elif event.startswith('stream') or event.startswith('video'):
                num = int(event.split()[-1])
                update_video(num)

            # update stream menu for processed videos
            for num, video in enumerate(playlist):
                stream_combo = window[f'stream {num}']
                if video.stream_list:
                    if stream_combo.Values != video.raw_stream_menu:
                        stream_combo(values=video.raw_stream_menu)
                        master_stream_text = values['master_stream_combo']
                        stream_text = master_stream_text if master_stream_text in video.raw_stream_names else video.selected_stream.raw_name
                        stream_combo(stream_text)
                        update_video(num)

            # animate progress bars while loading streams
            for num, bar in enumerate(progress_bars):
                video = playlist[num]
                if video.name in active_threads and not video.processed:
                    bar(visible=True)
                    bar.expand(expand_x=True)
                    bar.Widget['value'] += 10
                else:
                    bar(visible=False)

            # check terminate flag
            if config.terminate:
                window.close()
                return

        # After closing playlist window, select downloads tab -------------------------------------------------------
        self.select_tab('Downloads')

        # start downloading chosen videos ---------------------------------------------------------------------------
        def download_selected_videos():
            # will send videos to self.download() with paused intervals to prevent cpu surge

            for video in chosen_videos:
                log(f'download playlist fn> {repr(video.selected_stream)}, title: {video.name}')
                video.folder = config.download_folder

                # send video to download method
                self.start_download(video, silent=True)

                # give a small pause
                time.sleep(0.5)

        # create a separate thread to prevent gui freeze
        Thread(target=download_selected_videos).start()

    def download_subtitles(self):
        if not (self.d.subtitles or self.d.automatic_captions):
            sg.PopupOK('No Subtitles available')
            return

        if self.d.id not in self.active_windows:
            subtitle_window = SubtitleWindow(self.d)
            self.active_windows.append(subtitle_window)

    def ffmpeg_check(self):
        if not check_ffmpeg():
            if config.operating_system == 'Windows':
                layout = [[sg.T('"ffmpeg" is missing!! and need to be downloaded:\n')],
                          [sg.T('destination:')],
                          [sg.Radio(f'recommended: {config.global_sett_folder}', group_id=0, key='radio1', default=True)],
                          [sg.Radio(f'Local folder: {config.current_directory}', group_id=0, key='radio2')],
                          [sg.B('Download'), sg.Cancel()]]

                window = sg.Window('ffmpeg is missing', layout)

                event, values = window()
                window.close()
                selected_folder = config.global_sett_folder if values['radio1'] else config.current_directory
                if event == 'Download':
                    download_ffmpeg(destination=selected_folder)
            else:
                sg.popup_error(
                    '"ffmpeg" is required to merge an audio stream with your video',
                    'executable must be copied into PyIDM folder or add ffmpeg path to system PATH',
                    '',
                    'you can download it manually from https://www.ffmpeg.org/download.html',
                    title='ffmpeg is missing')

            return False
        else:
            return True

    def select_dash_audio(self):
        """prompt user to select dash audio manually"""
        if 'dash' not in self.d.subtype_list:
            log('select_dash_audio()> this function is available only for a dash video, ....')
            return

        if not self.d.audio_streams:
            log('select_dash_audio()> there is no audio streams available, ....')
            return

        streams_menu = list(self.d.audio_streams.keys())
        layout = [
            [sg.T('Select audio stream to be merged with dash video:')],
            [sg.Combo(streams_menu, default_value=self.d.audio_stream.name, key='stream')],
            [sg.T('please note:\n'
                  'Selecting different audio/video formats takes longer time "several minutes" while merging')],
            [sg.T('')],
            [sg.Ok(), sg.Cancel()]
        ]

        window = sg.Window('Select dash audio', layout, finalize=True)

        # while True:
        event, values = window()

        if event == 'Ok':
            selected_stream_name = values['stream']
            selected_stream = self.d.audio_streams[selected_stream_name]

            # set audio stream
            self.d.update_param(audio_stream=selected_stream)
            # print(self.d.audio_stream.name)
        window.close()

        # print(event, values)
    # endregion

    # region General
    def url_text_change(self):
        url = self.window.Element('url').get().strip()

        if url == self.url:
            return

        self.url = url

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
        self.url = ''
        self.url_text_change()

    def reset(self):
        # create new download item, the old one will be garbage collected by python interpreter
        self.d = DownloadItem()

        # reset some values
        self.set_status('')  # status bar
        self.playlist = []
        self.video = None

        # widgets
        self.disable()
        self.reset_video_controls()
        self.window['status_code']('')

        # Force python garbage collector to free up memory
        gc.collect()

    def change_cursor(self, cursor='default'):
        # return
        # todo: check if we can set cursor  for window not individual tabs
        if cursor == 'busy':
            cursor_name = 'watch'
        else:  # default
            cursor_name = 'arrow'

        self.window['Main'].set_cursor(cursor_name)
        self.window['Settings'].set_cursor(cursor_name)

    def main_frameOnClose(self):
        # config.terminate = True

        log('main frame closing')
        self.window.Close()

        # Terminate all downloads before quitting if any is a live
        try:
            for i in self.active_downloads:
                d = self.d_list[i]
                d.status = Status.cancelled
        except:
            pass

        # config.clipboard_q.put(('status', Status.cancelled))

    def check_scheduled(self):
        t = time.localtime()
        c_t = (t.tm_hour, t.tm_min)
        for d in self.d_list:
            if d.sched and d.sched[0] <= c_t[0] and d.sched[1] <= c_t[1]:
                self.start_download(d, silent=True)  # send for download
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

    def set_proxy(self):
        enable_proxy = self.values['enable_proxy']
        config.enable_proxy = enable_proxy

        # enable disable proxy entry text
        self.window['raw_proxy'](disabled=not enable_proxy)

        if not enable_proxy:
            config.proxy = ''
            self.window['current_proxy_value']('_no proxy_')
            return

        # set raw proxy
        raw_proxy = self.values.get('raw_proxy', '')
        config.raw_proxy = raw_proxy

        # proxy type
        config.proxy_type = self.values['proxy_type']

        if raw_proxy and isinstance(raw_proxy, str):
            raw_proxy = raw_proxy.split('://')[-1]
            proxy = config.proxy_type + '://' + raw_proxy

            config.proxy = proxy
            self.window['current_proxy_value'](config.proxy)
        # print('config.proxy = ', config.proxy)

    # endregion

    # region update
    def check_for_update(self):
        self.change_cursor('busy')

        # check for update
        current_version = config.APP_VERSION
        info = update.get_changelog()

        if info:
            latest_version, version_description = info

            # compare with current application version
            newer_version = compare_versions(current_version, latest_version)  # return None if both equal
            # print(newer_version, current_version, latest_version)

            if not newer_version or newer_version == current_version:
                self.new_version_available = False
                log("check_for_update() --> App. is up-to-date, server version=", latest_version)
            else:  # newer_version == latest_version
                self.new_version_available = True

            # updaet global values
            config.APP_LATEST_VERSION = latest_version
            self.new_version_description = version_description
        else:
            self.new_version_description = None
            self.new_version_available = False

        self.change_cursor('default')

    def update_app(self, remote=True):
        """show changelog with latest version and ask user for update
        :param remote: bool, check remote server for update"""
        if remote:
            self.check_for_update()

        if self.new_version_available:
            config.main_window_q.put(('show_update_gui', ''))
        else:
            if self.new_version_description:
                popup(f"App. is up-to-date, Local version: {config.APP_VERSION} \n"
                      f"Remote version:  {config.APP_LATEST_VERSION}", title='App update', )
            else:
                popup("couldn't check for update")

    def show_update_gui(self):
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
                    f'Found new version of youtube-dl on github \n'
                    f'new version     =  {latest_version}\n'
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
        self.active = True
        self.event = None
        self.values = None
        self.timeout = 10
        self.timer = 0
        self._progress_mode = 'determinate'

        self.create_window()

    @property
    def progress_mode(self):
        return self._progress_mode

    @progress_mode.setter
    def progress_mode(self, mode):
        """change progressbar mode (determinate / undeterminate)"""
        if self._progress_mode != mode:
            try:
                self.window['progress_bar'].Widget.config(mode=mode)
                self._progress_mode = mode
            except:
                pass

    def create_window(self):
        layout = [
            [sg.T('', size=(55, 4), key='out')],

            [sg.T(' ' * 120, key='percent')],

            [sg.ProgressBar(max_value=100, key='progress_bar', size=(42, 15), border_width=3)],

            # [sg.Column([[sg.Button('Hide', key='hide'), sg.Button('Cancel', key='cancel')]], justification='right')],
            [sg.T(' ', key='status', size=(42, 1)), sg.Button('Hide', key='hide'), sg.Button('Cancel', key='cancel')],
            [sg.T(' ', font='any 1')],
            [sg.T('', size=(100, 1),  font='any 8', key='log2', relief=sg.RELIEF_RAISED)],
        ]

        self.window = sg.Window(title=self.d.name, layout=layout, finalize=True, margins=(2, 2), size=(460, 205))
        self.window['progress_bar'].expand()
        self.window['percent'].expand()

        # log text, disable word wrap
        # self.window['log2'].Widget.config(wrap='none')

    def update_gui(self):
        # trim name and folder length
        name = truncate(self.d.name, 50)
        # folder = truncate(self.d.folder, 50)

        out = f"File: {name}\n" \
              f"downloaded: {size_format(self.d.downloaded)} out of {size_format(self.d.total_size)}\n" \
              f"speed: {size_format(self.d.speed, '/s') }  {time_format(self.d.time_left)} left \n" \
              f"live connections: {self.d.live_connections} - remaining parts: {self.d.remaining_parts}\n"

        try:
            self.window.Element('out').Update(value=out)

            # progress bar mode depend on available downloaditem progress property
            if self.d.progress:
                self.progress_mode = 'determinate'
                self.window['progress_bar'].update_bar(self.d.progress)
            else:  # size is zero, will make random animation
                self.progress_mode = 'indeterminate'
                self.window['progress_bar'].Widget['value'] += 5

            if self.d.status in (Status.completed, Status.cancelled, Status.error) and config.auto_close_download_window:
                self.close()

            # change cancel button to done when completed
            if self.d.status == Status.completed:
                self.window['cancel'](text='Done', button_color=('black', 'green'))

            # log
            self.window['log2'](config.log_entry)

            # percentage value to move with progress bar
            position = int(self.d.progress)
            self.window['percent'](f"{' ' * position} {self.d.progress}%")

            # status update
            self.window['status'](f"{self.d.status}  {self.d.i}")
        except:
            pass

    def run(self):
        self.event, self.values = self.window.Read(timeout=self.timeout)
        if self.event in ('cancel', None):
            if self.d.status not in (Status.error, Status.completed):
                self.d.status = Status.cancelled
            self.close()

        elif self.event == 'hide':
            self.close()

        # update gui
        if time.time() - self.timer >= 0.5:
            self.timer = time.time()
            self.update_gui()

    def focus(self):
        self.window.BringToFront()

    def close(self):
        self.event = None
        self.active = False
        self.window.Close()


class SubtitleWindow:

    def __init__(self, d):
        self.d = d
        self.window = None
        self.active = True
        self.subtitles = {}
        self.selected_subs = {}
        self.threads = []
        self.threads_num = 0

        self.setup()

    def setup(self):
        # build subtitles from self.d.subtitles and self.d.automatic_captions, and rename repeated keys
        subtitles = {}
        for k, v in self.d.subtitles.items():
            if k in subtitles:
                k = k + '_2'
            subtitles[k] = v

        for k, v in self.d.automatic_captions.items():
            if k in subtitles:
                k = k + '_2'
            subtitles[k] = v

        # build gui layout
        layout = [[sg.T('Subtitles for:')], [sg.T(self.d.name, tooltip=self.d.name)]]

        for i, lang in enumerate(subtitles.keys()):
            extensions = [entry.get('ext', '-') for entry in subtitles[lang]]

            # choose default extension
            if 'srt' in extensions:
                default_ext = 'srt'
            elif 'vtt' in extensions:
                default_ext = 'vtt'
            else:
                default_ext = extensions[0]

            layout.append([sg.Checkbox(lang, key=f'lang_{i}', size=(15, 1)), sg.T(' - Extension:'),
                           sg.Combo(values=extensions, default_value=default_ext, key=f'ext_{i}', size=(10, 1)),
                           sg.T('*sub' if lang in self.d.subtitles else '*caption')])

        layout = [[sg.Column(layout, scrollable=True, vertical_scroll_only=True, size=(400, 195), key='col')],
                  [sg.Button('Download'), sg.Button('Close'), sg.ProgressBar(100, size=(25, 10), key='bar')]]

        window = sg.Window('Subtitles window', layout)
        self.window = window
        self.subtitles = subtitles

    @staticmethod
    def download_subtitle(url, file_name):
        try:
            download(url, file_name)
            name, ext = os.path.splitext(file_name)

            # create 'srt' subtitle format from 'vtt' file
            if ext == '.vtt':
                # ffmpeg file full location
                ffmpeg = config.ffmpeg_actual_path

                output = name + '.srt'

                # very fast audio just copied, format must match [mp4, m4a] and [webm, webm]
                cmd = f'"{ffmpeg}" -y -i "{file_name}" "{output}"'

                error, _ = run_command(cmd, verbose=False, shell=True)
                if not error:
                    log('created ".srt" subtitle:', output)
        except Exception as e:
            log('download_subtitle() error', e)

    def run(self):

        event, values = self.window.read(timeout=10, timeout_key='_TIMEOUT_')

        if event != '_TIMEOUT_': print(event)

        if event in ('Close', None):
            self.window.close()
            self.active = False
            return

        if event == 'Download':
            # disable download button
            self.window['Download'](disabled=True)

            # reset selected subtitles
            self.selected_subs.clear()

            # get selected subs
            for i, k in enumerate(self.subtitles):
                if values[f'lang_{i}']:  # selected language checkbox, true if selected
                    # get selected extension
                    ext = values[f'ext_{i}']
                    url = [dict_['url'] for dict_ in self.subtitles[k] if dict_['ext'] == ext][0]
                    name = f'{os.path.splitext(self.d.target_file)[0]}_{k}.{ext}'

                    self.selected_subs[name] = url

            # download selected self.subtitles in separate threads
            self.threads = []
            for file_name, url in self.selected_subs.items():
                log('downloading subtitle', file_name)
                t = Thread(target=self.download_subtitle, args=(url, file_name))
                self.threads.append(t)
                t.start()
            self.threads_num = len(self.threads)

        # check download threads and update progress bar
        if self.threads:
            self.threads = [t for t in self.threads if t.is_alive()]
            percent = (self.threads_num - len(self.threads)) * 100 // self.threads_num
            self.window['bar'].update_bar(percent)
            if percent >= 100:
                sg.popup_ok('done downloading subtitles at:', self.d.folder)

        else:
            # enable download button again
            self.window['Download'](disabled=False)
