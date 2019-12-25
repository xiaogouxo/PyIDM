#!/usr/bin/env python
app_name = 'pyIDM'
version = '3.4.1.3' # GUI - apply margins = (2, 2)

# standard modules
import copy
import os, sys, platform
import py_compile
import shutil
import subprocess
import zipfile
from queue import Queue
from threading import Thread, Barrier, Timer, Lock
import re
import time
# import io
from collections import deque
import importlib.util


# external modules, should be kept updated.
ext_packages = "PySimpleGUI pyperclip plyer certifi mimetypes pycurl youtube_dl"

# installing missing packages
def install(package_name):
    # return False
    print('start installing', package_name)
    r = subprocess.run([sys.executable, "-m", "pip", "install", package_name, '--user'],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = r.stdout.decode('utf-8')
    if r.returncode != 0:
        print(package_name, 'failed to get installed')
        return False, log
    else:
        print(package_name, 'installed successfully')
        return True, log

missing_packages = [pkg for pkg in ext_packages.split() if importlib.util.find_spec(pkg) is None]

if 'PySimpleGUI' in missing_packages:
    print('PySimpleGUI is missing, will try to install it')
    install('PySimpleGUI')
    missing_packages.remove('PySimpleGUI')

if missing_packages:
    # try importing PySimpleGUI
    if 'PySimpleGUI' not in sys.modules.keys():
        import PySimpleGUI as sg
        sg.change_look_and_feel('Kayak')

    msg = (f"Looks like you have missing modules / packages:\n"
           f"\n"
           f"{missing_packages},\n"
           f"\n"
           f"will try to install them automatically,\n"
           f"proceed: go ahead and install missing modules,\n"
           f"cancel- terminate application")
    layout = [
        [sg.T(msg)],
        [sg.T('Installation status:')],
        [sg.Multiline('', key='missing_pkg_status', size=(50, 8), autoscroll=True)],
        [sg.Multiline('', key='log', size=(50, 8), autoscroll=True, )],
        [sg.B('Proceed', key='Proceed'), sg.Cancel()]
    ]

    window = sg.Window(title=f'{app_name} ... Missing packages installation', layout=layout)
    while True:
        event, values = window()

        if event in (None, 'Cancel'):
            window.Close()
            exit() # quit application
        if event == 'Proceed':
            if not missing_packages:
                window.Close()
                break

            failed_packages = []
            for package_name in missing_packages[:]:
                done, log = install(package_name)
                window['missing_pkg_status'](f"{package_name} .......... {'Done' if done else 'Failed'} \n", append=True)
                window['log'](log, append=True)
                window.Refresh()

                if done:
                    missing_packages.remove(package_name)
                else:
                    failed_packages.append(package_name)

            if failed_packages:
                window['missing_pkg_status'](f"\nFailed to install some packages, {failed_packages} 'press cancel to terminate application",
                                             append=True, text_color='red')
            else:
                window['missing_pkg_status']('\nAll - ok, click proceed to continue' , append=True, text_color='green')

# try importing PySimpleGUI
if 'PySimpleGUI' not in sys.modules.keys():
    import PySimpleGUI as sg

import pycurl
import certifi
import mimetypes
import pyperclip
import pickle, json
import plyer  # for os notification messages



test = False  # when active all exceptions will be re-raised

about_notes = f"""{app_name} is an open source multi-connections download manager based on python,
it downloads general files, also support downloading videos, and playlists from youtube.
Developed in Python, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

your feedback is most welcomed on

https://github.com/Aboghazala/{app_name}
email: mahmoud_elshahhat@yahoo.com

Thanks,
Mahmoud Elshahat
2019"""

# aliases
clipboard = pyperclip
clipboard.read = pyperclip.paste
clipboard.write = pyperclip.copy

# region public
ytdl = None  # youtube-dl will be imported in a separate thread to save loading time

current_directory = os.path.dirname(os.path.abspath(sys.argv[0]))  # get the directory of this script
os.chdir(current_directory)

app_title = f'{app_name} .. an open source download manager version {version}'
icon_name = 'icon.ico' if os.name == 'nt' else 'icon.png'
app_icon = os.path.join(current_directory, 'icons', icon_name)

themes = sorted(list(sg.LOOK_AND_FEEL_TABLE.keys()))
sg.SetOptions(font='Helvetica 11', auto_size_buttons=True, progress_meter_border_depth=0, border_width=1)

m_frame_q = Queue()  # queue for Main application window
clipboard_q = Queue()

monitor_clipboard = True
terminate = False  # application exit flag

active_downloads = set()  # indexes for active downloading items


class Logger(object):
    """used for capturing youtube-dl messages"""

    def debug(self, msg):
        log(msg)

    def error(self, msg):
        log('error: %s' % msg)

    def warning(self, msg):
        log('warning: %s' % msg)


ydl_opts = {'quiet': True, 'prefer_insecure': True, 'no_warnings': True, 'logger': Logger()}

server_codes = {

    # Informational.
    100: ('continue',),
    101: ('switching_protocols',),
    102: ('processing',),
    103: ('checkpoint',),
    122: ('uri_too_long', 'request_uri_too_long'),
    200: ('ok', 'okay', 'all_ok', 'all_okay', 'all_good', '\\o/', '✓'),
    201: ('created',),
    202: ('accepted',),
    203: ('non_authoritative_info', 'non_authoritative_information'),
    204: ('no_content',),
    205: ('reset_content', 'reset'),
    206: ('partial_content', 'partial'),
    207: ('multi_status', 'multiple_status', 'multi_stati', 'multiple_stati'),
    208: ('already_reported',),
    226: ('im_used',),

    # Redirection.
    300: ('multiple_choices',),
    301: ('moved_permanently', 'moved', '\\o-'),
    302: ('found',),
    303: ('see_other', 'other'),
    304: ('not_modified',),
    305: ('use_proxy',),
    306: ('switch_proxy',),
    307: ('temporary_redirect', 'temporary_moved', 'temporary'),
    308: ('permanent_redirect',),

    # Client Error.
    400: ('bad_request', 'bad'),
    401: ('unauthorized',),
    402: ('payment_required', 'payment'),
    403: ('forbidden',),
    404: ('not_found', '-o-'),
    405: ('method_not_allowed', 'not_allowed'),
    406: ('not_acceptable',),
    407: ('proxy_authentication_required', 'proxy_auth', 'proxy_authentication'),
    408: ('request_timeout', 'timeout'),
    409: ('conflict',),
    410: ('gone',),
    411: ('length_required',),
    412: ('precondition_failed', 'precondition'),
    413: ('request_entity_too_large',),
    414: ('request_uri_too_large',),
    415: ('unsupported_media_type', 'unsupported_media', 'media_type'),
    416: ('requested_range_not_satisfiable', 'requested_range', 'range_not_satisfiable'),
    417: ('expectation_failed',),
    418: ('im_a_teapot', 'teapot', 'i_am_a_teapot'),
    421: ('misdirected_request',),
    422: ('unprocessable_entity', 'unprocessable'),
    423: ('locked',),
    424: ('failed_dependency', 'dependency'),
    425: ('unordered_collection', 'unordered'),
    426: ('upgrade_required', 'upgrade'),
    428: ('precondition_required', 'precondition'),
    429: ('too_many_requests', 'too_many'),
    431: ('header_fields_too_large', 'fields_too_large'),
    444: ('no_response', 'none'),
    449: ('retry_with', 'retry'),
    450: ('blocked_by_windows_parental_controls', 'parental_controls'),
    451: ('unavailable_for_legal_reasons', 'legal_reasons'),
    499: ('client_closed_request',),

    # Server Error.
    500: ('internal_server_error', 'server_error', '/o\\', '✗'),
    501: ('not_implemented',),
    502: ('bad_gateway',),
    503: ('service_unavailable', 'unavailable'),
    504: ('gateway_timeout',),
    505: ('http_version_not_supported', 'http_version'),
    506: ('variant_also_negotiates',),
    507: ('insufficient_storage',),
    509: ('bandwidth_limit_exceeded', 'bandwidth'),
    510: ('not_extended',),
    511: ('network_authentication_required', 'network_auth', 'network_authentication'),
}


# endregion

def import_ytdl():
    # import youtube_dl using thread because it takes sometimes 20 seconds to get imported and delay the whole app start
    start = time.time()
    global ytdl
    import youtube_dl as ytdl
    load_time = time.time() - start
    log(f'youtube-dl load_time= {load_time}')


# region GUI
class MainWindow:
    def __init__(self):
        # current download_item
        self.d = DownloadItem()

        # main window
        self.window = None

        # download windows
        self.download_windows = {}  # {d.id: Download_Window()}

        # url
        self.url_timer = None  # usage: Timer(0.5, self.refresh_headers, args=[self.d.url])
        self.bad_headers = [0, range(400, 404), range(405, 418), range(500, 506)]  # response codes

        # connection
        self.max_connections = 10
        self.headers = None
        self.status_code = 0
        self._speed_limit = 0

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

        # download
        self.pending = deque()
        self.disabled = True  # for download button

        # download list
        self.d_headers = ['i', 'num', 'name', 'progress', 'speed', 'time_left', 'size', 'downloaded', 'status',
                          'resumable', 'folder', 'max_connections', 'live_connections', 'remaining_parts']
        self.d_list = list()  # list of DownloadItem() objects
        self.selected_row_num = None
        self.selected_d = DownloadItem()

        # settings
        self.setting = dict()
        self.max_concurrent_downloads = 3
        self.show_download_window = True
        self.theme = 'Green'  # default to Green

        # log
        self.log_text = ''

        # initial setup
        self.setup()

    def setup(self):
        """initial setup"""
        # get setting from disk
        self.load_setting()
        self.load_d_list()

        # theme
        sg.ChangeLookAndFeel(self.theme)

        # main window
        self.start_window()

        self.reset()
        self.disable_video_controls()

    # region gui design
    def create_window(self):
        col1 = [[sg.Combo(values=['Playlist'], size=(34, 1), key='pl_menu', enable_events=True)],
                [sg.ProgressBar(max_value=100, size=(20, 5), key='m_bar')]]

        col2 = [[sg.Combo(values=['Quality'], size=(34, 1), key='stream_menu', enable_events=True)],
                [sg.ProgressBar(max_value=100, size=(20, 5), key='s_bar')]]

        # main tab
        main_layout = [
                       [sg.Text(f'{app_name}', font='Helvetica 20', size=(37, 1), justification='center')],

                       # url
                       [sg.Text('URL:')],
                       [sg.Input('', enable_events=True, change_submits=True, key='url', size=(66, 1)),
                        sg.Button('Retry')],
                       [sg.Text('Status:', size=(70, 1), key='status')],

                       # spacer
                       [sg.T('', font='any 1')],

                       # youtube playlist
                       [sg.Frame('Youtube Playlist / videos:', key='youtube_frame', pad=(5, 5), layout=[
                            [sg.Column(col1, size=(300, 40),  element_justification='center', background_color=None),
                            sg.Button('⚡', disabled=False,  pad=(0, 0), tooltip='download this playlist', key='pl_download'),
                            sg.Column(col2, size=(300, 40), element_justification='center', background_color=None)]]
                                )
                        ],
                      

                       # file info
                       [sg.Text('File name:'), sg.Input('', size=(65, 1), key='name', enable_events=True)],
                       [sg.T('File size:'), sg.T('-' * 30, key='size'), sg.T('Type:'), sg.T('-' * 35, key='type'),
                        sg.T('Resumable:'), sg.T('-----', key='resumable')],
                       [sg.Text('Save To:'), sg.Input(self.d.folder, size=(55, 1), key='folder', enable_events=True),
                        sg.FolderBrowse(key='browse')], #initial_folder=self.d.folder,

                       # download button
                       [sg.T('', size=(29, 1)), sg.Button('Download', font='Helvetica 14', border_width=1)],

                       ]

        # downloads tab
        spacing = [' ' * 4, ' ' * 3, ' ' * 30, ' ' * 5, ' ' * 8, ' ' * 8, ' ' * 8, ' ' * 8, ' ' * 10, ' ' * 12, ' ' * 30, ' ',
                   ' ', ' ']  # setup initial column width

        downloads_layout = [[sg.Button('Resume'), sg.Button('Cancel'), sg.Button('Refresh'),
                             sg.Button('Folder'), sg.Button('D.Window'),
                             sg.T(' ' * 5), sg.T('Item:'),
                             sg.T('---', key='selected_row_num', text_color='white', background_color='red')],
                            [sg.Table(values=[spacing], headings=self.d_headers, size=(70, 13),
                                      vertical_scroll_only=False, key='table', enable_events=True)],
                            [sg.Button('Resume All'), sg.Button('Stop All'),
                             sg.Button('Delete', button_color=('white', 'red')),
                             sg.Button('Delete All', button_color=('white', 'red'))],
                            ]

        # setting tab
        setting_layout = [[sg.T('User Setting:'), sg.T(' ', size=(50,1)), sg.Button(' about ', key='about')],
                          [sg.Text('Select Theme:'),
                           sg.Combo(values=themes, default_value=self.theme, size=(15, 1), enable_events=True,
                                    key='themes'), sg.Text(f' Total of {len(themes)} Themes')],
                          [sg.T('Speed Limit:'), sg.Input('', size=(4, 1), key='speed_limit', enable_events=True),
                           sg.T('kb/s  *zero or blank means no limit')],
                          [sg.Checkbox('Monitor copied urls in clipboard', default=monitor_clipboard, key='monitor',
                                       enable_events=True)],
                          [sg.Checkbox("Show download window", key='show_download_window',
                                       default=self.show_download_window, enable_events=True)],
                          [sg.Text('Max concurrent downloads:'),
                           sg.Combo(values=[x for x in range(1, 101)], size=(5, 1), enable_events=True,
                                    key='max_concurrent_downloads', default_value=self.max_concurrent_downloads)],
                          [sg.Text('Max connections per download:'),
                           sg.Combo(values=[x for x in range(1, 101)], size=(5, 1), enable_events=True,
                                    key='max_connections', default_value=self.max_connections)],
                          [sg.Text('file part size:'), sg.Input(default_text=1024, size=(6, 1),
                                                                enable_events=True, key='part_size'),
                           sg.Text('KBytes   *affects new downloads only')],
                          [sg.T('')],
                          [sg.Button('update youtube-dl module', key='update_youtube_dl'),
                           sg.T('')]
                          ]

        log_layout = [[sg.T('Details events:')], [sg.Multiline(default_text=self.log_text, size=(70, 16), key='log',
                                                               autoscroll=True)],
                      [sg.Button('Clear Log')]]

        layout = [[sg.TabGroup(
            [[sg.Tab('Main', main_layout), sg.Tab('Downloads', downloads_layout), sg.Tab('Setting', setting_layout),
              sg.Tab('Log', log_layout)]],
            key='tab_group')],
            [sg.StatusBar('', size=(81, 1), font='Helvetica 11', key='status_bar')]
        ]

        # window
        window = sg.Window(title=app_title, icon=icon, layout=layout,
                           size=(700, 450),  margins = (2, 2))
        return window

    def start_window(self):
        self.window = self.create_window()
        self.window.Finalize()
        # expand elements to fit
        elements = ['url', 'name', 'folder', 'youtube_frame', 'm_bar', 's_bar', 'pl_menu', 'stream_menu', 'log'] # elements to be expanded
        for e in elements:
            self.window[e].expand(expand_x=True)

    def restart_window(self):
        try:
            self.window.Close()
        except:
            pass

        self.start_window()

    def select_tab(self, tab_name):
        try:
            self.window[tab_name].Select()
        except Exception as e:
            print(e)

    def update_gui(self):
        # read incoming messages from queue
        for _ in range(m_frame_q.qsize()):
            k, v = m_frame_q.get()
            if k == 'log':
                # add msg to log_txt
                # self.log_text = v + self.log_text
                # self.log_text = self.log_text[:20000]  # limit text size to save memory

                try:
                    if len(self.window['log'].get()) > 3000:
                        self.window['log'](self.window['log'].get()[:2000])
                    # self.window.Element('log').Update(self.log_text)
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

        # process pending jobs
        if self.pending and len(active_downloads) < self.max_concurrent_downloads:
            self.start_download(self.pending.popleft())

        # update Elements
        try:
            if self.window['name'].Get() != self.d.name:
                self.window['name'].Update(self.d.name)
            self.window.Element('size').Update(size_format(self.d.size))
            self.window.Element('type').Update(self.d.type)
            self.window.Element('resumable').Update('Yes' if self.d.resumable else 'No')

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
                f'Active downloads: {len(active_downloads)}, pending: {len(self.pending)}')


        except Exception as e:
            print('gui not updated:', e)

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
        timer1 = 0
        while True:
            event, values = self.window.Read(timeout=50)
            # if event != '__TIMEOUT__': print(event, values)

            if event is None:
                self.main_frameOnClose()
                break

            elif event == 'themes':
                self.theme = values['themes']
                sg.ChangeLookAndFeel(self.theme)

                # close all download windows if existed
                for win in self.download_windows.values():
                    win.window.Close()
                self.download_windows = {}

                self.restart_window()

            elif event == 'table':

                try:
                    item_num = values['table'][0]
                    self.selected_row_num = item_num
                    self.selected_d = self.d_list[self.selected_row_num]
                    self.window.Element('selected_row_num').Update('---' if item_num is None else item_num + 1)
                except:
                    pass

            elif event == 'url':
                self.url_text_change()

            elif event == 'Download':
                self.download_btn()

            elif event == 'folder':
                if values['folder']:
                    self.d.folder = values['folder']
                else: # in case of empty entries
                    self.window.Element('folder').Update(self.d.folder)
                # self.window['browse'](initial_folder=self.d.folder)

            elif event == 'name':
                self.d.name = validate_file_name(values['name'])

            elif event == 'Retry':
                self.retry()

            # downloads tab events
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
            elif event == 'speed_limit':
                self.speed_limit = values['speed_limit']

            elif event == 'max_concurrent_downloads':
                self.max_concurrent_downloads = int(values['max_concurrent_downloads'])

            elif event == 'max_connections':
                mc = int(values['max_connections'])
                if mc > 0: self.max_connections = mc

            elif event == 'monitor':
                global monitor_clipboard
                monitor_clipboard = values['monitor']
                clipboard_q.put(('monitor', monitor_clipboard))

            elif event == 'show_download_window':
                self.show_download_window = values['show_download_window']

            elif event == 'part_size':
                try:
                    self.d.part_size = int(values['part_size']) * 1024
                except:
                    pass

            elif event == 'update_youtube_dl':
                # select log tab
                self.select_tab('Log')

                response = sg.popup_ok_cancel(
                    'will try to download latest youtube-dl module from github and update this application\n'
                    'check log tab for progress \n'
                    'Proceed?',
                    title='youtube-dl module update')
                print(response)

                if response == 'OK':
                    try:
                        Thread(target=update_youtube_dl).start()
                    except Exception as e:
                        log('failed to update youtube-dl module:', e)



            # log
            elif event == 'Clear Log':
                self.log_text = ''
                try:
                    self.window.Element('log').Update('')
                except:
                    pass

            # about window
            elif event == 'about':
                sg.PopupNoButtons(about_notes, title=f'About {app_name} DM', non_blocking=True)

            # Run every n seconds
            if time.time() - timer1 >= 1:
                timer1 = time.time()

                # gui update
                self.update_gui()

            # run download windows if existed
            keys = list(self.download_windows.keys())
            for i in keys:
                win = self.download_windows[i]
                win.run()
                if win.event is None:
                    self.download_windows.pop(i, None)

    # region update info
    def update_info(self):

        # get file name
        name = ''
        if 'content-disposition' in self.headers:
            buffer = self.headers['content-disposition'].split(';')
            for w in buffer:
                if 'filename' in w:
                    w = w.replace('filename=', '')
                    w = w.replace('"', '')
                    w = w.replace("'", '')
                    name = w
        elif 'file-name' in self.headers:
            name = self.headers['file-name']
        else:
            clean_url = self.d.url.split('?')[0] if '?' in self.d.url else self.d.url
            name = clean_url.split('/')[-1]

        # file size
        size = int(self.headers.get('content-length', 0))

        # type
        mime_type = self.headers.get('content-type', 'N/A').split(';')[0]

        # file extension: if no extension already in file name
        if not mimetypes.guess_type(name, strict=False)[0]:
            ext = mimetypes.guess_extension(mime_type, strict=False) if mime_type not in ('N/A', None) else ''

            if ext:
                name += ext

        # check for resume support
        resumable = self.headers.get('accept-ranges', 'none') != 'none'

        # update current download item
        self.d.name = validate_file_name(name)
        print(self.d.name)
        self.d.size = size
        self.d.type = mime_type
        self.d.resumable = resumable

    # endregion

    # region connection
    @property
    def resume_support(self):
        return self._resumable == 'yes'

    @resume_support.setter
    def resume_support(self, value):
        self._resumable = 'yes' if value else 'no'
        try:
            self.window.Element('resumable').Update(self._resumable)
        except:
            pass

    @property
    def speed_limit(self):
        return self._speed_limit

    @speed_limit.setter
    def speed_limit(self, value):
        # validate value
        try:
            value = int(value)
        except:
            return

        self._speed_limit = value

    # endregion

    # region config files
    @property
    def sett_folder(self):
        home_folder = os.path.expanduser('~')

        if platform.system() == 'Windows':
            roaming = os.getenv('APPDATA')  # return APPDATA\Roaming\ under windows
            _sett_folder = os.path.join(roaming, f'.{app_name}')

        elif platform.system() == 'Linux':
            _sett_folder = f'{home_folder}/.config/{app_name}/'

        elif platform.system() == 'Darwin':
            _sett_folder = f'{home_folder}/Library/Application Support/{app_name}/'

        else:
            _sett_folder = current_directory

        if not os.path.exists(_sett_folder):
            try:
                os.mkdir(_sett_folder)
            except Exception as e:
                _sett_folder = current_directory
                print('setting folder error:', e)

        return _sett_folder

    def load_d_list(self):
        try:
            log('Load previous downloads items from', self.sett_folder)
            file = os.path.join(self.sett_folder, 'downloads.cfg')

            with open(file, 'r') as f:
                # expecting a list of dictionaries
                data = json.load(f)

            # converting list of dictionaries to list of DownloadItem() objects
            d_list = []
            for each_dictionary in data:
                d = update_object(DownloadItem(), each_dictionary)
                if d: # if update_object() returned an updated object not None
                    d_list.append(d)

            # clean d_list
            for d in d_list:
                status = Status.completed if d.progress >= 100 else Status.cancelled
                d.status = status

                d.time_left = '---'
                d.speed = '---'
                d.live_connections = 0

            # update self.d_list
            self.d_list = d_list

        except FileNotFoundError:
            log('downloads.cfg file not found')
        except Exception as e:
            handle_exceptions(f'load_d_list: {e}')
        finally:
            if type(self.d_list) is not list:
                self.d_list = []

    def save_d_list(self):
        try:
            data = []
            for d in self.d_list:
                d.q = None
                data.append(d.__dict__) # append object attributes dictionary to data list

            file = os.path.join(self.sett_folder, 'downloads.cfg')
        
            with open(file, 'w') as f:
                json.dump(data, f)
            log('list saved')
        except Exception as e:
            handle_exceptions(e)

    def load_setting(self):
        try:
            log('Load Application setting from', self.sett_folder)
            file = os.path.join(self.sett_folder, 'setting.cfg')
            with open(file, 'r') as f:
                self.setting = json.load(f)

        except FileNotFoundError:
            log('setting.cfg not found')
        except Exception as e:
            handle_exceptions(e)
        finally:
            if type(self.setting) is not dict:
                self.setting = {}

            # download folder
            folder = self.setting.get('folder', None)
            if folder and os.path.isdir(folder):
                self.d.folder = folder
            else:
                self.d.folder = os.path.join(os.path.expanduser("~"), 'Downloads')

            # clipboard monitor
            global monitor_clipboard
            monitor_clipboard = self.setting.get('monitor', True)
            clipboard_q.put(('monitor', monitor_clipboard))

            # max concurrent downloads
            self.max_concurrent_downloads = self.setting.get('max_concurrent_downloads', 3)

            # download window
            self.show_download_window = self.setting.get('show_download_window', True)

            # theme
            self.theme = self.setting.get('theme', 'Green')

    def save_setting(self):
        self.setting['folder'] = self.d.folder
        self.setting['monitor'] = monitor_clipboard
        self.setting['max_concurrent_downloads'] = self.max_concurrent_downloads
        self.setting['show_download_window'] = self.show_download_window
        self.setting['theme'] = self.theme

        try:
            file = os.path.join(self.sett_folder, 'setting.cfg')
            with open(file, 'w') as f:
                json.dump(self.setting, f)
                log('setting saved')
        except Exception as e:
            handle_exceptions(e)

    # endregion

    # region headers
    def refresh_headers(self, url):
        if self.d.url != '':
            self.changeCursor('busy')
            Thread(target=self.get_header, args=[url], daemon=True).start()

    def get_header(self, url):
        curl_headers = get_headers(url)

        # update headers only if no other curl thread created with different url
        if url == self.d.url:
            self.headers = curl_headers
            self.d.eff_url = curl_headers.get('eff_url')

            self.status_code = curl_headers.get('status_code', '')
            self.set_status(f"{self.status_code} - {server_codes.get(self.status_code, ' ')[0]}")

            # update file info
            self.update_info()

            # enable download button
            if self.status_code not in self.bad_headers and self.d.type != 'text/html':
                self.enable()

            # check if the link is html maybe it contains stream video
            if self.d.type == 'text/html':
                Thread(target=self.youtube_func, daemon=True).start()

            self.changeCursor('default')

    # endregion

    # region download
    def start_download(self, d, silent=None):
        if d is None:
            return

        # check for ffmpeg availability in case this is a video only stream
        if d.audio_url:
            cmd = 'where ffmpeg' if platform.system() == 'Windows' else 'which ffmpeg'
            error, output = run_command(cmd)
            if error:
                 sg.popup_error(self.d.name, 'The video stream has no audio, and "ffmpeg" is required to merge an audio stream with your video',
                'please install ffmpeg to your system and try again', 'https://www.ffmpeg.org/download.html', title='ffmpeg is missing')
                 return 'error'

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

        d.max_connections = self.max_connections if d.resumable else 1
        if silent is None:
            silent = not self.show_download_window

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
                os.unlink(d.full_name)

        # check if file already existed in download list
        i = self.file_in_d_list(d.name, d.folder)
        if i is not None:  # file already exist in d_list
            _d = self.d_list[i]
            log(f'start download fn> file exist in d_list, num {_d.num}')

            # if item in active downloads, quit or if status is downloading, quit
            if _d.id in active_downloads or self.d_list[d.id].status == Status.downloading:
                log('start download fn> file is being downloaded already, abort mission, taking no action')
                return
            else:
                # update url
                _d.eff_url = d.eff_url
                d = _d

        else:  # new file
            # generate unique id number for each download
            d.id = len(self.d_list)

            # add to download list
            self.d_list.append(d)

        # if max concurrent downloads exceeded download job will be added to pending deque
        if len(active_downloads) >= self.max_concurrent_downloads:
            d.status = Status.pending
            self.pending.append(d)
            return

        # start downloading
        if not silent:
            # create download window
            self.download_windows[d.id] = DownloadWindow(d)

        # create and start brain in a separate thread
        Thread(target=brain, daemon=True, args=(d, self.speed_limit)).start()

    def stop_all_downloads(self):
        # change status of pending items to cancelled
        for i, d in enumerate(self.d_list):
            if d.status == Status.pending:
                d.status = Status.cancelled

        # send cancelled status for all queues
        for i in active_downloads:
            d = self.d_list[i]
            d.q.brain.put(('status', Status.cancelled))
        # for _, q in self.active_qs.items():
        #     q.brain.put(('status', Status.cancelled))

        self.pending.clear()

    def resume_all_downloads(self):
        # change status of all non completed items to pending
        for i, d in enumerate(self.d_list):
            status = d.status

            if status == Status.cancelled:
                self.start_download(d, silent=True)

    def file_in_d_list(self, name, folder):
        for i, d in enumerate(self.d_list):
            if name == d.name and folder == d.folder:
                return i
        return None

    def download_btn(self):
        d = copy.deepcopy(self.d)

        if self.disabled: return

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
        if len(active_downloads) >= self.max_concurrent_downloads:
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
            active_downloads.pop(d.id)
        elif d.status == Status.downloading and d.q:
            d.q.brain.put(('status', Status.cancelled))

    def delete_btn(self):
        if self.selected_row_num is None:
            return

        # abort if there is items in progress or paused
        if active_downloads:
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
        if active_downloads:
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
        self.part_size = d.part_size
        self.d.folder = d.folder

        self.window['url'](d.url)
        self.url_text_change()

        # self.d = copy.deepcopy(d)
        self.window['folder'](self.d.folder)
        self.select_tab('Main')

    # endregion

    # region video

    @property
    def m_bar(self):
        return self._m_bar

    @m_bar.setter
    def m_bar(self, value):
        self._m_bar = value
        try:
            self.window.Element('m_bar').UpdateBar(value)
        except:
            pass

    @property
    def s_bar(self):
        return self._s_bar

    @s_bar.setter
    def s_bar(self, value):
        self._s_bar = value
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

    def enable_video_controls(self):
        try:
            pass # self.window.Element('pl_download').Update(disabled=False)
        except:
            pass

    def disable_video_controls(self):
        try:
            # self.window.Element('pl_download').Update(disabled=True)
            self.reset_progress_bar()
            self.pl_menu = ['Playlist']
            self.stream_menu = ['Video quality']
        except:
            pass

    def reset_progress_bar(self):
        self.m_bar = 0
        self.s_bar = 0

    def youtube_func(self):
        """get videos from youtube link consume time, if we start another func thread
        it should cancel the previous one
        """

        # validate youtube url
        pattern = r'^(http(s)?:\/\/)?((w){3}.)?youtu(be|.be)?(\.com)?\/.+'
        match = re.match(pattern, self.d.url)
        if not match:
            return  # quit if url is not a valid youtube watch url

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
        self.changeCursor('busy')

        # main progress bar
        self.m_bar = 10

        # assign playlist items
        self.playlist = []

        # quit if main window terminated
        if terminate: return

        try:
            # we import youtube-dl in separate thread to minimize startup time
            if ytdl is None:
                log('youtube-dl module still not loaded completely, please wait')
                while not ytdl:
                    time.sleep(0.1)  # wait until module get imported

            # youtube-dl process
            with ytdl.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(self.d.url, download=False, process=False)

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
                    s_bar_incr = 100 // len(pl_info) + 1

                    self.playlist = [None for _ in range(len(pl_info))]  # fill list so we can store videos in order
                    v_threads = []
                    for num, item in enumerate(pl_info):
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
            if terminate: return

            # quit if we couldn't extract any videos info (playlist or single video)
            if not self.playlist:
                self.disable_video_controls()
                self.disable()
                self.set_status('')
                self.changeCursor('default')
                self.reset()
                log('youtube func: quitting, can not extract videos')
                return

            # quit if url changed by user
            if url != self.d.url:
                self.disable_video_controls()
                self.changeCursor('default')
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

            self.enable_video_controls()
            self.enable()

            self.m_bar = 100

        except Exception as e:
            handle_exceptions(e)
            self.disable_video_controls()
            self.disable()

        finally:
            self.changeCursor('default')

    def get_video(self, num, vid_url, yt_id, s_bar_incr):
        try:
            video = Video(vid_url)

            # make sure no other youtube func thread started
            if yt_id != self.yt_id:
                print('get_video:> operation cancelled')
                return

            self.playlist[num] = video

        except Exception as e:
            print(e)
        finally:
            with self.s_bar_lock:
                self.s_bar += s_bar_incr

    def update_pl_menu(self):
        # set playlist label
        self.set_status(f'{len(self.playlist)} videos in Playlist: {self.pl_title}')

        # update playlist menu items
        self.pl_menu = [str(i + 1) + '- ' + video.title for i, video in enumerate(self.playlist)]

        # choose current item
        self.video = self.playlist[0]

    def update_video_param(self, stream_num=0):
        stream = self.video.allstreams[stream_num]
        self.video.name = self.video.title + '.' + stream.extension
        self.video.url = stream.url
        self.video.type = stream.extension
        self.video.size = stream.filesize

        # update file properties
        self.d.eff_url = self.video.url
        self.d.name = self.video.name
        self.d.size = self.video.size
        self.d.type = self.video.type
        self.d.resumable = True

        # check if video type has no audio
        if stream.mediatype == 'video':
            audio_stream = [a for a in self.video.audiostreams if a.extension == stream.extension
                            or (a.extension == 'm4a' and stream.extension == 'mp4')][0]
            self.d.audio_url = audio_stream.url
            self.d.audio_size = audio_stream.filesize
        else:
            # self.d.audio = None
            self.d.audio_url = None


    def update_stream_menu(self):
        self.stream_menu = [repr(stream) for stream in self.video.allstreams]

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

        index = self.stream_menu.index(selected_text)
        self.update_video_param(index)

    def download_playlist(self):
        # check if there is a playlist or quit
        # if self.pl_menu[0] = 'Playlist' and self.stream_menu[0] = 'Video quality':
        #     pass

        # ask user to choose videos quality
        streams = [repr(s) for s in self.video.allstreams]

        quality_window = sg.Window('Playlist download').Layout([
            [sg.T(f'{len(self.playlist)} videos will be downloaded \nChoose videos quality')],
            [sg.Listbox(streams, size=(50, 10))],
            [sg.Ok(), sg.Cancel()]])
        button, values = quality_window.Read()

        if button == 'Ok':
            choice = values[0][0]
            index = streams.index(choice)
            self.pl_quality = self.video.allstreams[index]  # as a chosen quality sample
            log('Selected quality:', choice)
            quality_window.Close()
            self.select_tab('Downloads')
        else:
            quality_window.Close()
            return

        for video in self.playlist:

            # get the best stream as a fallback in case we didn't find user selected stream
            if self.pl_quality.mediatype == 'normal':
                streams = video.streams
                best_stream = video.getbest(preftype='mp4', ftypestrict=False)
            elif self.pl_quality.mediatype == 'video':
                streams = video.videostreams
                best_stream = video.getbestvideo(preftype='mp4', ftypestrict=False)
            else:
                streams = video.audiostreams
                best_stream = video.getbestaudio(preftype='m4a', ftypestrict=False)

            stream = best_stream

            # search for stream match user selection
            for s in streams:
                if self.pl_quality.extension == s.extension and self.pl_quality.quality == s.quality:
                    stream = s
                    break

            video.name = video.title + '.' + stream.extension

            # check if video already exist
            if os.path.isfile(os.path.join(self.d.folder, video.name)):
                log(f'file name: {video.name} already exist, skip downloading this file')
                continue

            video.url = stream.url
            video.type = stream.extension
            video.size = stream.filesize

            resume_support = True if video.size else False

            log('download playlist fn>', 'stream', repr(stream))
            log(f'download playlist fn> media size= {video.size}, name= {video.name}')

            # start download
            d = DownloadItem(url=video.webpage_url, eff_url=video.url, name=video.name, size=video.size,
                             folder=self.d.folder, max_connections=self.max_connections, resumable=resume_support)
            self.start_download(d, silent=True)

    # endregion

    # region General
    def url_text_change(self):
        # Focus and select main app page in case text changed from script
        self.select_tab('Main')
        self.window.BringToFront()

        self.reset()
        try:
            self.d.eff_url = self.d.url = self.window.Element('url').Get().strip()

            # schedule refresh header func
            if type(self.url_timer) == Timer:
                self.url_timer.cancel()  # cancel previous timer

            self.url_timer = Timer(0.5, self.refresh_headers, args=[self.d.url])
            self.url_timer.start()  # start new timer

            # print('url text changed', self.d.url)
        except:
            pass

    def retry(self):
        self.url_text_change()

    def reset(self):
        # reset some values
        self.headers = {}
        self.d.name = ''
        self.d.size = 0
        self.d.type = ''
        self.d.resumable = False
        self.status_code = ''
        self.set_status('')

        # reset audio field
        self.d.audio_url = None

        # widgets
        self.disable()
        self.disable_video_controls()

    def changeCursor(self, cursor='busy'):
        pass

    def main_frameOnClose(self):
        global terminate
        terminate = True

        log('main frame closing')
        self.window.Close()

        # save config
        self.save_d_list()
        self.save_setting()

        # Terminate all downloads before quitting if any is a live
        try:
            for i in active_downloads:
                d = self.d_list[i]
                d.q.brain.put(('status', Status.cancelled))
        except:
            pass

        clipboard_q.put(('status', Status.cancelled))
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
        self.log_text = ''

        self.create_window()

    def create_window(self):
        main_layout = [
            [sg.T('', size=(55, 7), key='out')],

            [sg.ProgressBar(max_value=100, key='progress_bar', size=(35, 15), border_width=3)],

            [sg.T(' ' * 45), sg.Button('Hide', key='hide'), sg.Button('Cancel', key='cancel')],

        ]

        log_layout = [[sg.T('Details events:')],
                      [sg.Multiline(default_text=self.log_text, size=(70, 16), font='any 8', key='log', autoscroll=True)],
                      [sg.Button('Clear Log')]]

        layout = [[sg.TabGroup([[sg.Tab('Main', main_layout), sg.Tab('Log', log_layout)]])]]

        self.window = sg.Window(title=self.d.name, icon=icon, layout=layout,
                                size=(460, 240))

    def update_gui(self):
        # trim name and folder length
        length = 17
        name = self.d.name[:length] + ' ... ' + self.d.name[-length:] if len(self.d.name) > 40 else self.d.name
        folder = self.d.folder[:length] + ' ... ' + self.d.folder[-length:] if len(
            self.d.folder) > 40 else self.d.folder

        out = (f"File: {name}\n"
               f"Folder: {folder}\n"
               f"Downloaded:    {size_format(self.d.downloaded)} out of"
               f" {size_format(self.d.size)} ----  {self.d.progress}%\n"
               f"speed: {size_format(self.d.speed, '/s')}\n"
               f"Time remaining: {time_format(self.d.time_left)}\n"
               f"Live Connections: {self.d.live_connections} - Remaining parts: {self.d.remaining_parts} x "
               f"({size_format(self.d.part_size)})")

        # update log
        if self.d.q and self.d.q.d_window.qsize():
            k, v = self.d.q.d_window.get()
            print(k, v)
            if k == 'log':
                # self.log_text = v + self.log_text
                # self.log_text = self.log_text[:20000]  # limit text size to save memory
                try:
                    # self.window.Element('log').Update(self.log_text)
                    if len(self.window['log'].get()) > 3000:
                        self.window['log'](self.window['log'].get()[:2000])
                    # self.window.Element('log').Update(self.log_text)
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


# endregion


# define a class to hold all the required queues
class Communication:
    """it serve as communication between threads"""

    def __init__(self):
        # queues
        self.worker = []
        self.data = []
        self.brain = Queue()  # brain queue
        self.d_window = Queue()  # download window
        self.thread_mngr = Queue()
        self.jobs = Queue()
        self.completed_jobs = Queue()

    @staticmethod
    def clear(q):
        """clear individual queue"""
        try:
            while True:
                q.get_nowait()  # it will raise an exception when empty
        except:
            pass

    def reset(self):
        """clear all queues"""
        self.clear(self.brain)
        self.clear(self.d_window)
        self.clear(self.thread_mngr)
        self.clear(self.jobs)
        self.clear(self.completed_jobs)

        for q in self.worker:
            self.clear(q)

        for q in self.data:
            self.clear(q)

    def log(self, *args):
        """print log msgs to download window"""
        s = ''
        for arg in args:
            s += str(arg)
            s += ' '
        s = s[:-1]  # remove last space

        if s[-1] != '\n':
            s += '\n'

        # print(s, end='')

        self.d_window.put(('log', s))


# worker class
class Connection:
    """worker connection, it will download individual segment and write it to disk"""

    def __init__(self, tag=0, url='', temp_folder='', q=None, resumable=False, report=True):
        self.url = url
        self.tag = tag  # instant number
        self.q = q
        self.temp_folder = temp_folder
        self.resumable = resumable

        # General parameters
        self.seg = '0-0'  # segment name
        self.seg_range = '0-0'  # byte range it must be formatted as 'start_byte-end_byte' example '100-600'
        self.target_size = 0  # target size calculated from segment name
        self.start_size = 0  # initial file size before start resuming

        # writing data parameters
        self.f_name = ''  # segment name with full path
        self.mode = 'wb'  # file opening mode default to new write binary
        self.file = None
        self.buff = 0

        # reporting parameters
        self.report = report
        self.done_before = False
        self.timer1 = 0
        self.reporting_rate = 0.5  # rate of reporting download progress every n seconds
        self.downloaded = 0

        # connection parameters
        self.c = pycurl.Curl()
        self.speed_limit = 0
        self.headers = {}

    @property
    def actual_size(self):
        return self.start_size + self.downloaded + self.buff

    def reuse(self, seg='0-0', speed_limit=0):
        """Recycle same object again, better for performance as recommended by curl docs"""
        self.reset()

        # assign new values
        self.seg = seg  # segment name
        self.seg_range = seg  # byte range it must be formatted as 'start_byte-end_byte' example '100-600'
        self.target_size = get_seg_size(seg)
        self.f_name = os.path.join(self.temp_folder, seg)  # segment name with full path
        self.speed_limit = speed_limit

        self.q.log('start worker', self.tag, 'seg', self.seg, 'range:', self.seg_range, 'SL=', self.speed_limit)

        # run
        if os.path.exists(self.f_name) and self.target_size and self.resumable:
            self.start_size = os.path.getsize(self.f_name)
            self.check_previous_download()

    def reset(self):
        # reset curl
        self.c.reset()

        # reset variables
        self.target_size = 0  # target size calculated from segment name
        self.start_size = 0
        self.mode = 'wb'  # file opening mode default to new write binary
        self.file = None
        self.done_before = False
        self.buff = 0
        self.timer1 = 0
        self.downloaded = 0

    def check_previous_download(self):
        if self.actual_size == self.target_size:  # segment is completed before
            self.report_completed()
            self.q.log('Thread', self.tag, ': File', self.seg, 'already completed before')

            # send downloaded value to brain, -1 means this data from local disk, not from server side
            # self.q.data[self.tag].put((-1, self.target_size))
            self.report_to_brain((-1, self.target_size))
            self.done_before = True

        # in case the server sent extra bytes from last session by mistake, truncate file
        elif self.actual_size > self.target_size:
            self.q.log(f'found seg {self.seg} oversized {self.actual_size}')
            # self.mode = 'wb'  # open file for re-write
            # self.start_size = 0
            # truncate file
            with open(self.f_name, 'rb+') as f:
                f.truncate(self.target_size)
            self.report_completed()

            # send downloaded value to brain, -1 means this data from local disk, not from server side
            # self.q.data[self.tag].put((-1, self.target_size))
            self.report_to_brain((-1, self.target_size))
            self.done_before = True

        else:  # should resume
            # set new range and file open mode
            a, b = [int(x) for x in self.seg.split('-')]
            # a, b = int(self.seg.split('-')[0]), int(self.seg.split('-')[1])
            self.seg_range = f'{a + self.actual_size}-{b}'
            self.mode = 'ab'  # open file for append

            # report
            self.q.log('Thread', self.tag, ': File', self.seg, 'resuming, new range:', self.seg_range,
                       'actual size:', self.actual_size)
            # self.q.data[self.tag].put((-1, self.actual_size))  # send downloaded value to brain
            self.report_to_brain((-1, self.actual_size))

    def report_to_brain(self, msg):
        # if self.report:
        self.q.data[self.tag].put(msg)

    def report_every(self, seconds=0.0):
        if time.time() - self.timer1 >= seconds:
            # self.q.data[self.tag].put((self.tag, self.buff))  # report the downloaded data length
            self.report_to_brain((self.tag, self.buff))
            self.downloaded += self.buff
            self.buff = 0
            self.timer1 = time.time()

    def report_now(self):
        self.report_every(seconds=0)  # report data remained in buffer now

    def verify(self):
        """check if segment completed"""
        return self.actual_size == self.target_size or self.target_size == 0

    def report_not_completed(self):
        self.q.log('worker', self.tag, 'did not complete', self.seg, 'downloaded',
                   self.actual_size, 'target size:', self.target_size, 'remaining:',
                   self.target_size - self.actual_size)

        self.report_now()  # report data remained in buffer now

        # remove the previously reported download size and put unfinished job back to queue
        # self.q.data[self.tag].put((-1, - self.actual_size))
        self.report_to_brain((-1, - self.actual_size))
        self.q.jobs.put(self.seg)

    def report_completed(self):
        if self.report:
            self.q.completed_jobs.put(self.seg)

    def set_options(self):
        agent = f"{app_name} Download Manager"
        self.c.setopt(pycurl.USERAGENT, agent)

        self.c.setopt(pycurl.URL, self.url)
        self.c.setopt(pycurl.RANGE, self.seg_range)  # download segment only not the whole file

        # re-directions
        self.c.setopt(pycurl.FOLLOWLOCATION, 1)
        self.c.setopt(pycurl.MAXREDIRS, 10)

        self.c.setopt(pycurl.NOSIGNAL, 1)  # option required for multithreading safety
        self.c.setopt(pycurl.NOPROGRESS, 0)  # will use a progress function
        self.c.setopt(pycurl.CAINFO, certifi.where())  # for https sites and ssl cert handling

        # set speed limit selected by user
        self.c.setopt(pycurl.MAX_RECV_SPEED_LARGE, self.speed_limit)  # cap download speed to n bytes/sec, 0=disabled

        # time out
        self.c.setopt(pycurl.CONNECTTIMEOUT, 30)  # limits the connection phase, it has no impact once it has connected.
        # self.c.setopt(pycurl.TIMEOUT, 300)  # limits the whole operation time

        # abort if download speed slower than 1 byte/sec during 60 seconds
        self.c.setopt(pycurl.LOW_SPEED_LIMIT, 1)
        self.c.setopt(pycurl.LOW_SPEED_TIME, 60)

        # verbose
        self.c.setopt(pycurl.VERBOSE, 0)

        # # it tells curl not to include headers with the body
        # self.c.setopt(pycurl.HEADEROPT, 0)

        # call back functions
        self.c.setopt(pycurl.HEADERFUNCTION, self.header_callback)
        self.c.setopt(pycurl.WRITEFUNCTION, self.write)
        self.c.setopt(pycurl.XFERINFOFUNCTION, self.progress)

    def header_callback(self, header_line):
        header_line = header_line.decode('iso-8859-1')
        header_line = header_line.lower()

        if ':' not in header_line:
            return

        name, value = header_line.split(':', 1)
        name = name.strip()
        value = value.strip()
        self.headers[name] = value

    def progress(self, *args):
        """it receives progress from curl and can be used as a kill switch
        Returning a non-zero value from this callback will cause curl to abort the transfer
        """

        # check termination by user
        n = self.q.worker[self.tag].qsize()
        for _ in range(n):
            k, v = self.q.worker[self.tag].get()
            if k == 'status':
                status = v
                if status in [Status.cancelled, Status.paused]:
                    return -1  # abort

    def worker(self):
        # check if file completed before and exit
        if self.done_before:
            return

        self.set_options()

        try:
            with open(self.f_name, self.mode) as self.file:
                self.c.perform()

            # after curl connection ended
            self.report_now()  # report data remained in buffer now

            completed = self.verify()
            if completed:
                self.report_completed()
            else:
                self.report_not_completed()

            response_code = self.c.getinfo(pycurl.RESPONSE_CODE)
            if response_code in range(400, 512):
                self.q.log('server refuse connection', response_code, 'cancel download and try to refresh link')
                self.q.brain.put(('server', ['error', response_code]))

        except Exception as e:
            if any(statement in repr(e) for statement in ('Failed writing body', 'Callback aborted')):
                error = f'worker {self.tag} terminated, {e}'
            else:
                error = repr(e)

            self.q.log('worker', self.tag, ': quitting ...', error)
            self.report_not_completed()

    def write(self, data):
        """write to file"""
        self.file.write(data)
        self.buff += len(data)

        self.report_every(seconds=self.reporting_rate)  # tell brain how much data received every n seconds

        # check if we getting over sized
        if self.actual_size > self.target_size > 0:
            return -1  # abort


# status class as an Enum
class Status:
    """used to identify status, i don't like Enum"""
    downloading = 'downloading'
    paused = 'paused'
    cancelled = 'cancelled'
    completed = 'completed'
    pending = 'pending'
    merging_audio = 'merging_audio'


# Download Item Class
class DownloadItem:

    def __init__(self, d_id=0, name='', size=0, mime_type='', folder='', url='',
     eff_url='', pl_url='', max_connections=1, live_connections=0, resumable=False,
     progress=0, speed=0, time_left='', downloaded=0, status='cancelled',
     remaining_parts=0, part_size=1048576):
        self.q = None  # queue
        self._id = d_id
        self.num = d_id + 1 if d_id else ''
        self._name = name
        self.size = size
        self.type = mime_type
        self.folder = folder
        self._full_name = None  # containing path
        # self.temp_folder = ''
        self.url = url
        self.eff_url = eff_url
        self.pl_url = pl_url # playlist url
        self.Max_connections = max_connections
        self.live_connections = live_connections
        self.resumable = resumable
        self.progress = progress
        self.speed = speed
        self.time_left = time_left
        self.downloaded = downloaded
        self._status = status
        self.remaining_parts = remaining_parts
        # animation
        self.animation_icon = {Status.downloading: '►►', Status.pending: 'P', Status.completed: '✔',
                               Status.cancelled: '--'}
        self.i = ''  # animation image
        self._part_size = part_size

        # audio
        self.audio_url = None
        self.audio_size = 0
        self.is_audio = False


    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_value):
        # validate new name
        self._name = validate_file_name(new_value)

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, new_id):
        self._id = new_id
        self.num = new_id + 1 if type(new_id) is int else new_id

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        self.i = self.animation_icon.get(self._status, '')

    @property
    def part_size(self):
        return self._part_size

    @part_size.setter
    def part_size(self, value):
        self._part_size = value if value <= self.size else self.size
        print('part size = ', self._part_size)

    @property
    def full_name(self):
        """return file name including path"""
        return os.path.join(self.folder, self.name)

    @property
    def temp_folder(self):
        return self.full_name + '_parts'


# region video classes
class Video:
    """represent a youtube video object, interface for youtube-dl, inspired from pafy"""

    def __init__(self, url, vid_info=None, size=True):
        self.watch_url = url
        self.vid_info = vid_info  # a youtube-dl dictionary contains video information

        if self.vid_info is None:
            with ytdl.YoutubeDL(ydl_opts) as ydl:
                self.vid_info = ydl.extract_info(self.watch_url, download=False)

        self.webpage_url = self.vid_info.get('webpage_url')
        self.title = validate_file_name(self.vid_info.get('title', f'video{int(time.time())}'))

        self._streams = []
        self._oggstreams = []
        self._m4astreams = []

        self._allstreams = []
        self._videostreams = []
        self._audiostreams = []

        if size:
            for s in self.allstreams:
                s.get_filesize()

    def _process_streams(self):
        """ Create Stream object lists"""
        self._allstreams = [Stream(x) for x in self.vid_info['formats']]
        self._allstreams.reverse()

        self._streams = [i for i in self._allstreams if i.mediatype == 'normal']
        self._audiostreams = [i for i in self._allstreams if i.mediatype == 'audio']
        self._videostreams = [i for i in self._allstreams if i.mediatype == 'video']

        self._mp4streams = [i for i in self._allstreams if i.extension == 'm4a']

    @property
    def streams(self):
        """ The streams for a video. Returns list."""
        if not self._streams:
            self._process_streams()

        return self._streams

    @property
    def allstreams(self):
        """ All stream types for a video. Returns list. """
        if not self._allstreams:
            self._process_streams()

        return self._allstreams

    @property
    def audiostreams(self):
        """ Return a list of audio Stream objects. """
        if not self._audiostreams:
            self._process_streams()

        return self._audiostreams

    @property
    def videostreams(self):
        """ The video streams for a video. Returns list. """
        if not self._videostreams:
            self._process_streams()

        return self._videostreams

    @property
    def mp4streams(self):
        """ Return a list of m4a encoded Stream objects. """
        if not self._mp4streams:
            self._process_streams()

        return self._mp4streams

    def _getbest(self, preftype="any", ftypestrict=True, vidonly=False):
        """
        Return the highest resolution video available.

        Select from video-only streams if vidonly is True
        """
        streams = self.videostreams if vidonly else self.streams

        if not streams:
            return None

        def _sortkey(x, key3d=0, keyres=0, keyftype=0):
            """ sort function for max(). """
            key3d = "3D" not in x.resolution
            keyres = int(x.resolution.split("x")[0])
            keyftype = preftype == x.extension
            strict = (key3d, keyftype, keyres)
            nonstrict = (key3d, keyres, keyftype)
            return strict if ftypestrict else nonstrict

        r = max(streams, key=_sortkey)

        if ftypestrict and preftype != "any" and r.extension != preftype:
            return None

        else:
            return r

    def getbestvideo(self, preftype="any", ftypestrict=True):
        """
        Return the best resolution video-only stream.

        set ftypestrict to False to return a non-preferred format if that
        has a higher resolution
        """
        return self._getbest(preftype, ftypestrict, vidonly=True)

    def getbest(self, preftype="any", ftypestrict=True):
        """
        Return the highest resolution video+audio stream.

        set ftypestrict to False to return a non-preferred format if that
        has a higher resolution
        """
        return self._getbest(preftype, ftypestrict, vidonly=False)

    def getbestaudio(self, preftype="any", ftypestrict=True):
        """ Return the highest bitrate audio Stream object."""
        if not self.audiostreams:
            return None

        def _sortkey(x, keybitrate=0, keyftype=0):
            """ Sort function for max(). """
            keybitrate = int(x.rawbitrate)
            keyftype = preftype == x.extension
            strict, nonstrict = (keyftype, keybitrate), (keybitrate, keyftype)
            return strict if ftypestrict else nonstrict

        r = max(self.audiostreams, key=_sortkey)

        if ftypestrict and preftype != "any" and r.extension != preftype:
            return None

        else:
            return r


class Stream:
    def __init__(self, stream_info):
        # fetch data from youtube-dl stream_info dictionary
        self.format_id = stream_info.get('format_id', None)
        self.url = stream_info.get('url', None)
        self.player_url = stream_info.get('player_url', None)
        self.extension = stream_info.get('ext', None)
        self.width = stream_info.get('width', None)
        self.fps = stream_info.get('fps', None)
        self.height = stream_info.get('height', None)
        self.format_note = stream_info.get('format_note', None)
        self.acodec = stream_info.get('acodec', None)
        self.abr = stream_info.get('abr', None)
        self._filesize = stream_info.get('filesize', None)
        self.tbr = stream_info.get('tbr', None)
        self.quality = stream_info.get('quality', None)
        self.vcodec = stream_info.get('vcodec', None)
        self.res = stream_info.get('resolution', None)
        self.downloader_options = stream_info.get('downloader_options', None)
        self.format = stream_info.get('format', None)
        self.container = stream_info.get('container', None)

        # calculate some values
        self.rawbitrate = stream_info.get('abr', 0) * 1024
        self.mediatype = self.get_type()
        self.resolution = f'{self.width}x{self.height}' if (self.width and self.height) else ''

    @property
    def filesize(self):
        if self._filesize:
            return self._filesize
        else:
            self.get_filesize()

    def get_filesize(self):
        if self._filesize:
            return self._filesize
        else:
            headers = get_headers(self.url)
            self._filesize = int(headers.get('content-length', 0))
            return self._filesize

    def __repr__(self):
        if self.mediatype == 'audio':
            r = f'{self.mediatype}: {self.extension} - abr {self.abr} - {size_format(self.filesize)} '
        else:
            r = f'{self.mediatype}: {self.extension} - {self.height}p - {self.resolution} ' \
                f'- {size_format(self.filesize)}'
        return r

    def get_type(self):
        if self.vcodec == 'none':
            return 'audio'
        elif self.acodec == 'none':
            return 'video'
        else:
            return 'normal'


# endregion


# region brain, thread manager, file manager
def brain(d=None, speed_limit=0):
    """main brain for a single download, it controls thread manger, file manager, and get data from workers
    and communicate with download window Gui, Main frame gui"""

    # initiate queue
    d.q = Communication()  # create new com queue
    q = d.q

    # set status
    if d.status == Status.downloading:
        log('another brain thread may be running')
        return
    else:
        d.status = Status.downloading

    # add item index to active downloads
    if d.is_audio == False:
        active_downloads.add(d.id)

    # define barrier used by brain to make sure file manager and thread manager exit first
    barrier = Barrier(3)


    def send_msg(*qs, **kwargs):
        """add msgs to queues"""
        for q in qs:
            if q is m_frame_q:
                # kwargs['id'] = d.id
                q.put(('brain', kwargs))
            else:
                for key, value in kwargs.items():
                    q.put((key, value))

    q.log(f'start downloading file: {d.name}, size: {size_format(d.size)}')

    # region Setup

    # temp folder to store file segments
    if not os.path.exists(d.temp_folder):
        os.mkdir(d.temp_folder)

    # divide the main file into ranges of bytes (segments) and add it to the job queue list
    if d.resumable:
        seg_list = size_splitter(d.size, d.part_size)
    else:
        seg_list = [f'0-{d.size - 1 if d.size > 0 else 0}']  # should be '0-0' if size zero/unknown

    # getting previously completed list, by reading 'completed.cfg' file from temp folder
    completed_parts = set()
    file = os.path.join(d.temp_folder, 'completed.cfg')
    # read pickled file contains completed parts names
    if os.path.isfile(file):
        with open(file, 'rb') as f:
            completed_parts = pickle.load(f)

    # calculate previously downloaded size and add non-completed jobs to jobs' queue
    downloaded = 0
    for seg in seg_list:
        if seg in completed_parts:
            # get size of completed parts
            downloaded += get_seg_size(seg)
        else:
            q.jobs.put(seg)

    # communicator part
    sample = 0
    status = Status.downloading
    old_status = None
    start_timer = 0
    live_threads = 0
    num_jobs = q.jobs.qsize()
    progress = avg_speed = buff = 0
    time_left = ''

    speed_buffer = deque()  # used for avg speed calc. "deque is faster than list"
    server_error = 0

    # endregion

    # run file manager in a separate thread
    Thread(target=file_mngr, daemon=True, args=(d, barrier, seg_list)).start()

    # create queue for each worker
    q.worker = [Queue() for _ in range(d.max_connections)]  # make a queue for each worker.
    q.data = [Queue() for _ in range(d.max_connections)]  # data from workers

    # run thread manager in a separate thread
    Thread(target=thread_manager, daemon=True, args=(d, barrier, speed_limit)).start()

    while True:
        # a sleep time to make the program responsive
        time.sleep(0.1)

        # read brain queue
        for _ in range(q.brain.qsize()):
            k, v = q.brain.get()
            if k == 'status':
                status = v
            elif k == 'live_threads':
                live_threads = v
            elif k == 'num_jobs':
                num_jobs = v
            elif k == 'speed_limit':
                speed_limit = v
                q.log('brain received speed limit:', speed_limit)
                send_msg(q.thread_mngr, speed_limit=speed_limit)
            elif k == 'server':
                if v[0] == 'error':
                    code = v[1]
                    server_error += 1
                    if code == 429:
                        d.max_connections = d.max_connections - 1 or 1
                        send_msg(q.thread_mngr, max_connections=d.max_connections)
                    if server_error >= 30:
                        msg = f'server refuse connection {code} {server_codes[code][0]}, try to refresh link'
                        q.log(msg)
                        # send_msg(q.d_window, speed=0, live_threads=0, time_left='-', command=['stop', msg])
                        status = Status.cancelled

        # read downloaded data lengths
        for i in range(d.max_connections):
            if q.data[i].qsize() > 0:
                data_code, temp = q.data[i].get()  # get messages from threads
                buff += temp  # used for "downloaded" calc

                if data_code >= 0:  # while download resume, we receive -1 "data obtained from disk not the server"
                    sample += temp  # used for "speed" calc

                if buff > 0 or (downloaded >= d.size > 0):
                    downloaded += buff
                    buff = 0

                # reset previous server errors if we receive data from other connections
                server_error = 0

        # periodic update
        delta_time = (time.time() - start_timer)
        if delta_time >= 0.2:  # update every n seconds,
            speed = sample / delta_time if sample >= 0 else 0  # data length / delta time in seconds

            # calculate average speed based on 50 readings
            speed_buffer.append(speed)
            if status != Status.downloading: speed_buffer.clear()

            avg_speed = sum(speed_buffer) / len(speed_buffer) or 1 if status == Status.downloading else 0
            if len(speed_buffer) > 50: speed_buffer.popleft()  # remove the oldest value

            progress = round(downloaded * 100 / d.size, 1) if d.size else 0

            time_left = (d.size - downloaded) / avg_speed if avg_speed else -1

            # update download item "d"
            d.progress = progress
            d.speed = avg_speed
            d.downloaded = round(downloaded, 2)
            d.live_connections = live_threads
            d.remaining_parts = num_jobs
            d.time_left = time_left
            d.status = status

            # reset sample and timer
            sample = 0
            start_timer = time.time()

        # status check
        if status != old_status:
            log(f'brain {d.num}: received', status)
            # update queues
            send_msg(q.thread_mngr, status=status)
            d.status = status

            # check for user termination
            if status == Status.cancelled:
                q.log('brain: received', status)

                # update download item "d"
                d.progress = progress
                d.speed = '---'
                d.downloaded = round(downloaded, 2)
                d.live_connections = 0
                d.remaining_parts = num_jobs
                d.time_left = '---'
                break

            # check if jobs completed
            elif status == Status.completed:
                # log('d.id, d.isaudio:', d.id, d.is_audio)
                if d.is_audio:  # an audio file ready for merge, should quit here
                    log('done downloading', d.name)
                    return True # as indication of success

                # now video file completed and check for audio file
                if d.audio_url: # this means a video file needs an audio file to be downloaded
                    # correct status because operation not finished yet
                    d.status = Status.merging_audio
                    d.progress = 99

                    # create a DownloadItem() object for audio
                    audio = DownloadItem()
                    audio.name = f'audio_for_{d.name}'
                    audio.size = d.audio_size
                    audio.max_connections = d.max_connections
                    audio.resumable = True
                    audio.url = audio.eff_url = d.audio_url
                    audio.folder = d.folder
                    audio.is_audio = True
                    audio.id = f'{d.num}_audio'# (d.id + 1 ) * 1000 - 1

                    video_file = d.full_name
                    audio_file = audio.full_name #os.path.join(d.folder, d.audio.name)
                    out_file = os.path.join(d.folder, f'out_{d.name}')

                    log('start downloading ', audio.name)
                    # brain(d.audio)
                    done = brain(audio)

                    if done: # d.audio.ready_for_merge:  # an audio file already downloaded and ready for merge
                        log('start merging video and audio files')
                        error, output = merge_video_audio(video_file, audio_file, out_file)
                        if error:
                           msg = f'Failed to merge {audio.name} \n {output}'
                           log(msg)
                           # sg.popup_error(msg, title='Merge error')
                           status == Status.cancelled
                        else:

                            log('finished merging video and audio files')

                            os.unlink(video_file)
                            os.unlink(audio_file)

                            # Rename main file name
                            os.rename(out_file, video_file)

                            status = d.status = Status.completed
                    else:
                        msg = 'Failed to download ' + audio.name
                        log(msg)
                        # sg.popup_error(msg, title='audio file download error')
                        status == Status.cancelled

            if status == Status.completed:
                # getting remaining buff value
                downloaded += buff

                # update download item "d"
                d.progress = 100
                d.speed = '---'
                d.downloaded = round(downloaded, 2)
                d.live_connections = 0
                d.remaining_parts = 0
                d.time_left = '---'

                # os notification popup
                notification = f"File: {d.name} \nsaved at: {d.folder}"
                notify(notification, title=f'{app_name} - Download completed')
                break

        old_status = status

    # quit file manager
    q.completed_jobs.put('exit')

    # wait for thread manager and file manager to quit first
    try:
        barrier.wait()
        time.sleep(0.1)
    except Exception as e:
        log(f'brain {d.num} error!, bypassing barrier... {e}')
        handle_exceptions(e)

    # reset queue and delete un-necessary data
    d.q.reset()

    # remove item index from active downloads
    if d.is_audio == False:
        active_downloads.remove(d.id)
    log(f'\nbrain {d.num}: removed item from active downloads')

    # report quitting
    q.log('brain: quitting')
    log(f'\nbrain {d.num}: quitting')


def thread_manager(d, barrier, speed_limit):
    q = d.q
    # create worker/connection list
    connections = [Connection(tag=i, url=d.eff_url, temp_folder=d.temp_folder, q=q, resumable=d.resumable) for i in
                   range(d.max_connections)]

    def stop_all_workers():
        # send message to worker threads
        for worker_num in busy_workers:
            q.worker[worker_num].put(('status', Status.cancelled))

    status = Status.downloading
    worker_sl = old_worker_sl = 0  # download speed limit for each worker
    timer1 = 0
    free_workers = [i for i in range(d.max_connections)]
    free_workers.reverse()
    busy_workers = []
    live_threads = []  # hold reference to live threads
    job_list = []
    track_num = 0  # to monitor any change in live threads

    while True:
        time.sleep(0.1)  # a sleep time to while loop to make the app responsive

        # getting jobs
        for _ in range(d.q.jobs.qsize()):
            job_list.append(d.q.jobs.get())

        # sort job list "small will be last" to finish segment in order, better for video files partially play
        job_list.sort(key=lambda seg: int(seg.split('-')[0]), reverse=True)

        # reading incoming messages
        for _ in range(q.thread_mngr.qsize()):
            k, v = q.thread_mngr.get()
            if k == 'status':
                status = v
                if status == Status.paused:
                    q.log('thread_mng: pausing ... ')
                    stop_all_workers()
                elif status in (Status.cancelled, Status.completed):
                    stop_all_workers()
                    status = 'cleanup'

            elif k == 'speed_limit':
                speed_limit = v
                q.log('Thread manager received speed limit:', speed_limit)

            elif k == 'max_connections':
                max_connections = v

        # speed limit
        worker_sl = speed_limit * 1024 // min(d.max_connections, (len(job_list) or 1))

        # speed limit dynamic update every 3 seconds
        if worker_sl != old_worker_sl and time.time() - timer1 > 3:
            q.log('worker_sl', worker_sl, ' - old wsl', old_worker_sl)
            old_worker_sl = worker_sl
            timer1 = time.time()
            stop_all_workers()  # to start new workers with new speed limit

        # reuse a free worker to handle a job from job_list
        if len(busy_workers) < d.max_connections and free_workers and job_list and status == Status.downloading:
            worker_num, seg = free_workers.pop(), job_list.pop()  # get available tag # get a new job
            busy_workers.append(worker_num)  # add number to busy workers

            # create new threads
            conn = connections[worker_num]
            conn.reuse(seg=seg, speed_limit=worker_sl)
            t = Thread(target=conn.worker, daemon=True, name=str(worker_num))
            live_threads.append(t)
            t.start()

        # Monitor active threads and add the offline to a free_workers
        for t in live_threads:
            if not t.is_alive():
                worker_num = int(t.name)
                live_threads.remove(t)
                busy_workers.remove(worker_num)
                free_workers.append(worker_num)

        # update brain queue
        if len(live_threads) != track_num:
            track_num = len(live_threads)
            q.brain.put(('live_threads', track_num))
            q.brain.put(('num_jobs', track_num + len(job_list) + q.jobs.qsize()))

        # in case no more jobs and no live threads, report to brain and wait for instructions
        if track_num == 0 and q.jobs.qsize() == 0 and len(job_list) == 0:
            q.brain.put(('num_jobs', 0))

        # wait for threads to quit first
        if len(live_threads) == 0 and status == 'cleanup':  # only achieved if get status = cancelled from brain
            q.log('thread_manager: cleanup')
            break

    # wait for brain and file manager to quit
    try:
        barrier.wait()
    except Exception as e:
        log(f'thread_manager {d.num} error!, bypassing barrier... {e}')
        handle_exceptions(e)

    log(f'thread_manager {d.num}: quitting')


def file_mngr(d, barrier, seg_list):
    q = d.q
    all_parts = set(seg_list)

    # read pickled file contains completed parts names
    cfg_file = os.path.join(d.temp_folder, 'completed.cfg')
    if os.path.isfile(cfg_file):
        with open(cfg_file, 'rb') as f:
            completed_parts = pickle.load(f)
    else:
        completed_parts = set()

    # target file
    d.folder = os.path.abspath(d.folder)
    target_file = os.path.join(d.folder, d.name)

    # check / create temp file
    temp_file = os.path.join(d.folder, '__downloading__' + d.name)
    if not os.path.isfile(temp_file):
        with open(temp_file, 'wb') as f:
            # f.write(b'')
            pass
    d.temp_file = temp_file
    d.target_file = target_file

    parts = []

    while True:
        time.sleep(0.1)

        if q.completed_jobs.qsize():
            msg = q.completed_jobs.get()
            if msg == 'exit':
                break
            else:
                parts.append(msg)

        if parts:
            # append the completed parts into temp file
            failed_parts = append_parts(parts=parts[:], src_folder=d.temp_folder, target_file=temp_file,
                                        target_folder=d.folder)
            if failed_parts != parts:
                done = [x for x in parts if x not in failed_parts]
                parts = failed_parts
                for part_name in done:
                    os.remove(os.path.join(d.temp_folder, part_name))

                    # update the set
                    completed_parts.add(part_name)

                # write completed list on disk
                with open(cfg_file, 'wb') as f:
                    pickle.dump(completed_parts, f)

        # check if all parts already finished
        if completed_parts == all_parts:

            # Rename main file name
            os.rename(temp_file, target_file)

            # delete temp files
            delete_folder(d.temp_folder)

            # inform brain
            q.brain.put(('status', Status.completed))
            break


    # wait for thread manager and brain to quit
    try:
        barrier.wait()
    except Exception as e:
        log(f'file manager {d.num} error!, bypassing barrier... {e}')
        handle_exceptions(e)
    log(f'file_manager {d.num}: quitting')


# endregion


# region clipboard, singleApp, and Taskbaricon
def clipboard_listener():
    old_data = ''
    monitor = True

    while True:

        new_data = clipboard.read()

        if new_data == 'any one there?': # a possible message comming from new inistace of this script
            clipboard.write('yes') # it will be read by singleApp() as an exit signal
            m_frame_q.put(('visibility', 'show')) # restore main window if minimized

        if monitor and new_data != old_data:
            if new_data.startswith('http') and ' ' not in new_data:
                m_frame_q.put(('url', new_data))

            old_data = new_data

        if clipboard_q.qsize() > 0:
            k, v = clipboard_q.get()
            if k == 'status' and v == Status.cancelled: break
            elif k == 'monitor': monitor = v

        time.sleep(0.2)


def singleApp():
    """send a message thru clipboard to check if an app instance already running"""
    original = clipboard.read() # get original clipboard value
    clipboard.write('any one there?')
    time.sleep(0.3)
    answer = clipboard.read()
    clipboard.write(original) # restore clipboard original value

    if answer == 'yes':
        print('previous instance already running')
        return False
    else:
        return True


# endregion


# region helper functions
def notify(msg, title=f'{app_name}', timeout=5):
    # show os notification at tray icon area
    try:
      plyer.notification.notify(title=title, message=msg, app_name=app_title)
    except Exception as e:
      handle_exceptions(f'plyer notification: {e}')


def handle_exceptions(error):
    if test:
        raise error
    else:
        log(error)


def append_parts(parts=None, src_folder=None, target_file=None, target_folder=None):
    """expect list of parts names like '100-30000'"""

    target_file = os.path.join(target_folder, target_file)

    try:
        with open(target_file, 'rb+') as target:
            for part_name in parts[:]:
                start = int(part_name.split('-')[0])
                part_file = os.path.join(src_folder, part_name)
                with open(part_file, 'rb') as part:
                    # # get current size of open target file by f.tell()
                    # target.seek(0, 2)  # go to the end of the file
                    # size = target.tell()
                    #
                    # # seek right position
                    # if start > size:
                    #     # fill zeros
                    #     target.write((start-size) * b'0')
                    # elif start < size:
                    #     target.seek(start)

                    target.seek(start)  # no need to fill zeros "if start > size" since seek/write do it automatically

                    # write part file
                    target.write(part.read())

                    # remove part name from list
                    parts.remove(part_name)

    except Exception as e:
        log(f'append part:> {repr(e)}')

    finally:
        return parts


def get_headers(url):
    """return dictionary of headers"""
    curl_headers = {}

    def header_callback(header_line):
        # quit if main window terminated
        if terminate: return

        header_line = header_line.decode('iso-8859-1')
        header_line = header_line.lower()

        if ':' not in header_line:
            return

        name, value = header_line.split(':', 1)
        name = name.strip()
        value = value.strip()
        curl_headers[name] = value
        print(name, ':', value)

    def write_callback(data):
        return -1  # send terminate flag

    def debug_callback(handle, type, data, size=0, userdata=''):
        """it takes output from curl verbose and pass it to my log function"""
        try:
            log(data.decode("utf-8"))
        except:
            pass
        return 0

    # region curl options
    agent = f"{app_name} Download Manager"
    c = pycurl.Curl()
    c.setopt(pycurl.URL, url)
    c.setopt(pycurl.FOLLOWLOCATION, 1)
    c.setopt(pycurl.MAXREDIRS, 10)
    c.setopt(pycurl.CONNECTTIMEOUT, 30)
    c.setopt(pycurl.TIMEOUT, 300)
    c.setopt(pycurl.NOSIGNAL, 1)
    c.setopt(pycurl.CAINFO, certifi.where())  # for https sites and ssl cert handling
    c.setopt(pycurl.USERAGENT, agent)
    c.setopt(pycurl.AUTOREFERER, 1)
    c.setopt(pycurl.WRITEFUNCTION, write_callback)
    c.setopt(pycurl.HEADERFUNCTION, header_callback)
    # endregion

    try:
        c.perform()
    except Exception as e:
        if 'Failed writing body' not in str(e):
            handle_exceptions(e)

    # add status code and effective url to headers
    curl_headers['status_code'] = c.getinfo(pycurl.RESPONSE_CODE)
    curl_headers['eff_url'] = c.getinfo(pycurl.EFFECTIVE_URL)

    # return headers
    return curl_headers


def download(url, file_name):
    """simple file download, return False if failed"""
    with open(file_name, 'wb') as file:
        c = pycurl.Curl()
        c.setopt(c.URL, url)
        c.setopt(c.WRITEDATA, file)

        # re-directions
        c.setopt(pycurl.FOLLOWLOCATION, 1)
        c.setopt(pycurl.MAXREDIRS, 10)

        c.setopt(pycurl.NOSIGNAL, 1)  # option required for multithreading safety
        c.setopt(pycurl.NOPROGRESS, 0)  # will use a progress function
        c.setopt(pycurl.CAINFO, certifi.where())  # for https sites and ssl cert handling
        try:
            c.perform()
            log(file_name, 'downloaded')
        except Exception as e:
            log(e)
            return False
        finally:
            c.close()


def size_format(size, tail=''):
    # 1 kb = 1024 byte, 1MB = 1024 KB, 1GB = 1024 MB
    # 1 MB = 1024 * 1024 = 1_048_576 bytes
    # 1 GB = 1024 * 1024 * 1024 = 1_073_741_824 bytes

    try:
        if size == 0: return '---'
        """take size in num of byte and return representation string"""
        if size < 1024:  # less than KB
            s = f'{round(size)} bytes'

        elif 1_048_576 > size >= 1024:  # more than or equal 1 KB and less than MB
            s = f'{round(size / 1024)} KB'
        elif 1_073_741_824 > size >= 1_048_576:  # MB
            s = f'{round(size / 1_048_576, 1)} MB'
        else:  # GB
            s = f'{round(size / 1_073_741_824, 2)} GB'
        return f'{s}{tail}'
    except:
        return size


def time_format(t, tail=''):
    if t == -1:
        return '---'

    try:
        if t <= 60:
            s = f'{round(t)} seconds'
        elif 60 < t <= 3600:
            s = f'{round(t / 60)} minutes'
        elif 3600 < t <= 86400:
            s = f'{round(t / 3600, 1)} hours'
        elif 86400 < t <= 2592000:
            s = f'{round(t / 86400, 1)} days'
        elif 2592000 < t <= 31536000:
            s = f'{round(t / 2592000, 1)} months'
        else:
            s = f'{round(t / 31536000, 1)} years'

        return f'{s}{tail}'
    except:
        return t


def log(*args):
    s = ''
    for arg in args:
        s += str(arg)
        s += ' '
    s = s[:-1]  # remove last space
    s = '>> ' + s

    try:
        print(s)
    except Exception as e:
        print(e)

    try:
        m_frame_q.put(('log', '\n' + s))
    except Exception as e:
        print(e)


def validate_file_name(f_name):
    # filter for tkinter safe character range
    f_name = ''.join([c for c in f_name if ord(c) in range(65536)])
    safe_string = str()
    char_count = 0
    for c in str(f_name):
        if c in ['\\', '/', ':', '?', '<', '>', '"', '|', '*']:
            safe_string += '_'
        else:
            safe_string += c

        if char_count > 100:
            break
        else:
            char_count += 1
    return safe_string


def size_splitter(size, part_size):
    """Receive file size and return a list of size ranges"""
    result = []

    if size == 0:
        result.append('0-0')
        return result

    # decide num of parts
    span = part_size if part_size <= size else size
    print(f'span={span}, part size = {part_size}')
    parts = max(size // span, 1)  # will be one part if size < span

    x = 0
    size = size - 1  # when we start counting from zero the last byte number should be size - 1
    for i in range(parts):
        y = x + span - 1
        if size - y < span:  # last remaining bytes
            y = size
        result.append(f'{x}-{y}')
        x = y + 1

    return result


def delete_folder(folder):
    try:
        shutil.rmtree(folder)
    except Exception as e:
        log(e)


def get_seg_size(seg):
    # calculate segment size from segment name i.e. 200-1000  gives 801 byte
    a, b = int(seg.split('-')[0]), int(seg.split('-')[1])
    size = b - a + 1 if b > 0 else 0
    return size


def merge_video_audio(video, audio, output):

    # ffmpeg
    ffmpeg = 'ffmpeg' #os.path.join(current_directory, 'ffmpeg', 'ffmpeg')

    # very fast audio just copied, format must match [mp4, m4a] and [webm, webm]
    cmd1 = f'{ffmpeg} -i "{video}" -i "{audio}" -c copy "{output}"'

    # slow, mix different formats
    cmd2 = f'{ffmpeg} -i "{video}" -i "{audio}" "{output}"'

    error, output = run_command(cmd1, shell=True, verbose=True)

    return error, output


def update_youtube_dl():
    """This block for updating youtube-dl module in the freezed application folder in windows"""
    # check if the application runs from a windows cx_freeze executable "folder contains lib subfolder"
    # if run from source code, we will update system installed package and exit
    if 'lib' not in os.listdir(current_directory):
        log('running command: python -m pip install youtube_dl --upgrade')
        r = subprocess.run([sys.executable, "-m", "pip", "install", 'youtube_dl', '--upgrade'],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log(r.stdout.decode('utf-8'))
        return

    # make temp folder
    log('making temp folder in:', current_directory)
    if 'temp' not in os.listdir(current_directory):
        os.mkdir(os.path.join(current_directory, 'temp'))

    # paths
    old_module = os.path.join(current_directory, 'lib/youtube_dl')
    new_module = os.path.join(current_directory, 'temp/youtube-dl-master/youtube_dl')

    def compile_file(file):
        if file.endswith('.py'):
            py_compile.compile(file, cfile=file + 'c')
            os.remove(file)
        else:
            print(file, 'not .py file')

    def compile_all():
        for item in os.listdir(new_module):
            item = os.path.join(new_module, item)

            if os.path.isfile(item):
                file = item
                compile_file(file)
            else:
                folder = item
                for file in os.listdir(folder):
                    file = os.path.join(folder, file)
                    compile_file(file)
        log('new youtube-dl module compiled to .pyc files')

    def overwrite_module():
        delete_folder(old_module)
        shutil.move(new_module, old_module)
        log('new module copied to:', new_module)

    # download from github
    log('start downloading youtube-dl module from github')
    url = 'https://github.com/ytdl-org/youtube-dl/archive/master.zip'
    response = download(url, 'temp/youtube-dl.zip')
    if response is False:
        log('failed to download youtube-dl, abort update')
        return

    # extract zip file
    with zipfile.ZipFile('temp/youtube-dl.zip', 'r') as zip_ref:
        zip_ref.extractall(path=os.path.join(current_directory, 'temp'))

    log('youtube-dl.zip extracted to: ', current_directory + '/temp')

    # compile files from py to pyc
    log('compile files')
    compile_all()

    # delete old youtube-dl module and replace it with new one
    overwrite_module()

    # clean old files
    delete_folder('temp')
    log('delete temp folder')
    log('youtube_dl module ..... done updating')


def run_command(cmd, verbose=True, shell=False):
    if verbose: log('running command:', cmd)
    error, output = True, f'error running command {cmd}'
    try:
        if shell==True:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        else:
            r = subprocess.run(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        error = True if r.returncode != 0 else False
        output = r.stdout.decode('utf-8')
        if verbose: log(output)

    except Exception as e:
        log('error running command {cmd}', e)
        pass

    return error, output


def print_object(obj):
    if obj is None:
        print(obj, 'is None')
        return
    for k, v in vars(obj).items():
        try:
            print(k, '=', v)
        except:
            pass

def update_object(obj, new_values):
    """update an object attributes from a supplied dictionary"""
    # avoiding obj.__dict__.update(new_values) as it will set a new attribute if it doesn't exist

    try:
        for k, v in new_values.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj
    except Exception as e:
        log(f'update_object(): error, {e}')


# endregion


if __name__ == '__main__':
    icon = app_icon #image_file_to_bytes(app_icon, (50, 50))
    print('starting application')
    if singleApp():
        Thread(target=import_ytdl, daemon=True).start()
        Thread(target=clipboard_listener, daemon=True).start()
        main_window = MainWindow()
        main_window.run()
