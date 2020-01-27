"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""

# Download Item Class

import os
import mimetypes
from threading import Thread, Lock
# from config import Status, SEGMENT_SIZE, MAX_CONNECTIONS
from .utils import validate_file_name, get_headers, translate_server_code
from . import config


class DownloadItem:
    # animation ['►►   ', '  ►►'] › ► ⤮ ⇴ ↹ ↯  ↮  ₡ ['⯈', '▼', '⯇', '▲']
    # ['⏵⏵', '  ⏵⏵'] ['›', '››', '›››', '››››', '›››››']
    animation_icons = {config.Status.downloading: ['❯', '❯❯', '❯❯❯', '❯❯❯❯'], config.Status.pending: ['⏳'],
                       config.Status.completed: ['✔'], config.Status.cancelled: ['-x-'],
                       config.Status.merging_audio: ['↯', '↯↯', '↯↯↯']}

    def __init__(self, id_=0, url='', name='', folder=''):
        self.id = id_
        self._name = name
        self._full_name = None  # containing path
        self.ext = ''

        self.folder = folder

        self.url = url
        self.eff_url = ''
        self.playlist_url = ''

        self.size = 0
        self.resumable = False
        self.type = ''

        self.Max_connections = config.max_connections
        self._segment_size = config.segment_sie

        self.live_connections = 0
        self.progress = 0
        self.speed = 0
        self.time_left = 0
        self._downloaded = 0
        self.status = config.Status.cancelled
        self.remaining_parts = 0

        self.q = None  # queue

        # connection status
        self.status_code = 0
        self.status_code_description = ''

        # animation
        self.animation_index = self.id % 2  # to give it a different start point than neighbour items

        # audio
        self.audio_url = None
        self.audio_size = 0
        self.is_audio = False

        # callback is a string represent any function name declared in module scope
        self.callback = ''

        # schedule download
        self.sched = None  # should be time in (hours, minutes) tuple for scheduling download

        # Lock
        # self.lock = Lock()

    @property
    def num(self):
        return self.id + 1 if isinstance(self.id, int) else self.id

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_value):
        # validate new name
        self._name = validate_file_name(new_value)

    @property
    def full_name(self):
        """return file name including path"""
        return os.path.join(self.folder, self.name)

    @property
    def temp_name(self):
        """return file name including path"""
        return f'_temp_{self.name}'

    @property
    def full_temp_name(self):
        """return temp file name including path"""
        return os.path.join(self.folder, self.temp_name)

    @property
    def audio_name(self):
        return f'audio_for_{self.name}'

    @property
    def full_audio_name(self):
        return os.path.join(self.folder, self.audio_name)

    @property
    def temp_folder(self):
        return os.path.join(self.folder, f'{self.temp_name}_parts_')

    @property
    def i(self):
        # This is where we put the animation letter
        if self.sched:
            selected_image = self.sched_string
        else:
            icon_list = self.animation_icons.get(self.status, [''])
            if self.animation_index >= len(icon_list):  self.animation_index = 0
            selected_image = icon_list[self.animation_index]
            self.animation_index += 1

        return selected_image

    @property
    def segment_size(self):
        return self._segment_size

    @segment_size.setter
    def segment_size(self, value):
        self._segment_size = value if value <= self.size else self.size
        print('segment size = ', self._segment_size)

    @property
    def sched_string(self):
        # t = time.localtime(self.sched)
        # return f"⏳({t.tm_hour}:{t.tm_min})"
        return f"{self.sched[0]:02}:{self.sched[1]:02}"

    @property
    def downloaded(self):
        return self._downloaded

    @downloaded.setter
    def downloaded(self, value):
        """this property might be set from threads, expecting int (number of bytes)"""
        if not isinstance(value, int):
            return

        # with self.lock:
        self._downloaded = value

    def update(self, url):
        """get headers and update properties (eff_url, name, ext, size, type, resumable, status code/description)"""
        print('update d parameters')

        if url in ('', None):
            return

        self.url = url
        headers = get_headers(url)

        # update headers only if no other update thread created with different url
        if url == self.url:
            self.eff_url = headers.get('eff_url')
            self.status_code = headers.get('status_code', '')
            self.status_code_description = f"{self.status_code} - {translate_server_code(self.status_code)}"

            # update file info

            # get file name
            name = ''
            if 'content-disposition' in headers:  # example content-disposition : attachment; filename=ffmpeg.zip
                name = headers['content-disposition'].split(';')[1]
                name = name.split('=')[1].strip()

            elif 'file-name' in headers:
                name = headers['file-name']
            else:
                clean_url = url.split('?')[0] if '?' in url else url
                name = clean_url.split('/')[-1]

            # file size
            size = int(headers.get('content-length', 0))

            # type
            content_type = headers.get('content-type', 'N/A').split(';')[0]
            # fallback, guess type from file name extension
            guessed_content_type = mimetypes.guess_type(name, strict=False)[0]
            if not content_type:
                content_type = guessed_content_type

            # file extension:
            if not guessed_content_type:  # None if no ext in file name
                ext = mimetypes.guess_extension(content_type, strict=False) if content_type not in ('N/A', None) else ''

                if ext:
                    name += ext
            else:
                _, ext = os.path.splitext(name)

            # check for resume support
            resumable = headers.get('accept-ranges', 'none') != 'none'

            self.name = name
            self.ext = ext
            self.size = size
            self.type = content_type
            self.resumable = resumable
        print('done', url)

    def reset(self):
        self.name = ''
        self.size = 0
        self.type = ''
        self.resumable = False

        # reset audio field
        self.audio_url = None

    def __repr__(self):
        """used with functions like print, it will return all properties in this object"""
        output = ''
        for k, v in self.__dict__.items():
            output += f"{k}: {v} \n"
        return output

