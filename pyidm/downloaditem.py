"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""

# Download Item Class

import os
import mimetypes
import time
from collections import deque
from queue import Queue
from threading import Thread, Lock
from urllib.parse import urljoin
from .utils import validate_file_name, get_headers, translate_server_code, size_splitter, get_seg_size, log, \
    delete_file, delete_folder, save_json, load_json
from . import config

# lock used with downloaded property
lock = Lock()


# todo: cleanup required for this class
# define a class to hold all the required queues
class Communication:
    """it serve as communication between threads"""

    def __init__(self):
        # queues
        self.d_window = Queue()  # download window, required for log messages
        self.jobs = Queue()  # required for failed worker jobs

        # self.worker = []
        # self.data = []
        # self.brain = Queue()  # brain queue
        # self.thread_mngr = Queue()
        # self.completed_jobs = Queue()

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
        self.clear(self.d_window)
        self.clear(self.jobs)
        # self.clear(self.brain)
        # self.clear(self.thread_mngr)
        # self.clear(self.completed_jobs)

        # for q in self.worker:
        #     self.clear(q)
        #
        # for q in self.data:
        #     self.clear(q)

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


class Segment:
    def __init__(self, name=None, num=None, range=None, size=None, url=None, targetfile=None, tempfile=None):
        self.num = num
        self.name = name
        self.targetfile = targetfile
        self.tempfile = tempfile
        self.size = size
        self.range = range
        self.url = url
        self.downloaded = False
        self.completed = False  # done downloading and merging into tempfile
        self.headers = {}

    def get_size(self):
        self.headers = get_headers(self.url)
        try:
            self.size = int(self.headers.get('content-length', 0))
            print(self.num, 'done getting size')
        except:
            pass
        return self.size


# todo: remove target folder from segments, and remove audio folders
class DownloadItem:

    # animation ['►►   ', '  ►►'] › ► ⤮ ⇴ ↹ ↯  ↮  ₡ ['⯈', '▼', '⯇', '▲']
    # ['⏵⏵', '  ⏵⏵'] ['›', '››', '›››', '››››', '›››››']
    animation_icons = {config.Status.downloading: ['❯', '❯❯', '❯❯❯', '❯❯❯❯'], config.Status.pending: ['⏳'],
                       config.Status.completed: ['✔'], config.Status.cancelled: ['-x-'],
                       config.Status.merging_audio: ['↯', '↯↯', '↯↯↯'], config.Status.error: ['err']}

    def __init__(self, id_=0, url='', name='', folder=''):
        self.id = id_
        self._name = name
        self.ext = ''

        self.folder = os.path.abspath(folder)

        self.url = url
        self.eff_url = ''
        self.playlist_url = ''

        self.size = 0
        self.resumable = False
        self.type = ''

        self._segment_size = config.segment_size

        self.live_connections = 0
        self._downloaded = 0
        self._status = config.Status.cancelled
        self.remaining_parts = 0

        self.q = Communication()  # queue

        # connection status
        self.status_code = 0
        self.status_code_description = ''

        # animation
        self.animation_index = self.id % 2  # to give it a different start point than neighbour items

        # audio
        self.audio_url = None
        self.audio_size = 0
        self.is_audio = False

        # postprocessing callback is a string represent any function name need to be called after done downloading
        # this function must be available or imported in brain.py namespace
        self.callback = ''

        # schedule download
        self.sched = None  # should be time in (hours, minutes) tuple for scheduling download

        # speed
        self.speed_timer = 0
        self.speed_buffer = deque()  # store some speed readings for calculating average speed afterwards
        self.download_buffer = 0
        self.speed_refresh_rate = 1  # calculate speed every n time

        # segments
        self._segments = []

        # fragmented video parameters will be updated from video subclass object / update_param()
        self.fragment_base_url = None
        self.fragments = None

        # fragmented audio parameters will be updated from video subclass object / update_param()
        self.audio_fragment_base_url = None
        self.audio_fragments = None

        # protocol
        self.protocol = ''

        self.format_id = None
        self.audio_format_id = None

    def get_persistent_properties(self):
        """return a dict of important parameters to be saved in file"""
        a = dict(id=self.id, _name=self._name, folder=self.folder, url=self.url, eff_url=self.eff_url,
                 playlist_url=self.playlist_url, size=self.size, resumable=self.resumable,
                 _segment_size=self._segment_size, _downloaded=self._downloaded, _status=self._status,
                 remaining_parts=self.remaining_parts, audio_url=self.audio_url, audio_size=self.audio_size,
                 type=self.type, fragments=self.fragments, fragment_base_url=self.fragment_base_url,
                 audio_fragments=self.audio_fragments, audio_fragment_base_url=self.audio_fragment_base_url,
                 )
        return a

    def reset_segments(self):
        """reset each segment properties "downloaded and merged" """
        for seg in self._segments:
            seg.downloaded = False
            seg.completed = False

    @property
    def segments(self):
        if not self._segments:
            # handle fragmented video
            if self.fragments:
                # print(self.fragments)
                # example 'fragments': [{'path': 'range/0-640'}, {'path': 'range/2197-63702', 'duration': 9.985},]
                self._segments = [Segment(name=os.path.join(self.temp_folder, str(i)), num=i, range=None, size=0,
                                          url=urljoin(self.fragment_base_url, x['path']), targetfile=self.target_file,
                                          tempfile=self.temp_file)
                                  for i, x in enumerate(self.fragments)]

            else:
                if self.resumable and self.size:
                    # get list of ranges i.e. ['0-100', 101-2000' ... ] # should be '0-0' if size zero/unknown
                    range_list = size_splitter(self.size, self.segment_size)
                else:
                    range_list = [None]
                    # f'0-{self.size - 1 if self.size > 0 else 0}']

                self._segments = [
                    Segment(name=os.path.join(self.temp_folder, str(i)), num=i, range=x, size=get_seg_size(x),
                            url=self.eff_url, targetfile=self.target_file, tempfile=self.temp_file)
                    for i, x in enumerate(range_list)]

            # get an audio stream to be merged with dash video
            if self.type == 'dash':
                # handle fragmented audio
                if self.audio_fragments:
                    # example 'fragments': [{'path': 'range/0-640'}, {'path': 'range/2197-63702', 'duration': 9.985},]
                    audio_segments = [
                        Segment(name=os.path.join(self.temp_folder, str(i) + '_audio'), num=i, range=None, size=0,
                                url=urljoin(self.audio_fragment_base_url, x['path']), targetfile=self.audio_file,
                                tempfile=self.audio_file)
                        for i, x in enumerate(self.audio_fragments)]

                else:
                    range_list = size_splitter(self.audio_size, self.segment_size)

                    audio_segments = [
                        Segment(name=os.path.join(self.temp_folder, str(i) + '_audio'), num=i, range=x, size=get_seg_size(x),
                                url=self.audio_url, targetfile=self.audio_file, tempfile=self.audio_file)
                        for i, x in enumerate(range_list)]

                # append to main list
                self._segments += audio_segments

        return self._segments

    @segments.setter
    def segments(self, value):
        self._segments = value

    def save_progress_info(self):
        """save segments info to disk"""
        seg_list = [{'name': seg.name, 'downloaded':seg.downloaded, 'completed':seg.completed, 'size':seg.size} for seg in self.segments]
        file = os.path.join(self.temp_folder, 'info.txt')
        save_json(file, seg_list)

    def load_progress_info(self):
        """load saved progress info from disk"""
        file = os.path.join(self.temp_folder, 'info.txt')
        if os.path.isfile(file):
            seg_list = load_json(file)
            for seg, item in zip(self.segments, seg_list):
                if seg.name in item['name']:
                    seg.size = item['size']
                    seg.downloaded = item['downloaded']
                    seg.completed = item['completed']

    @property
    def total_size(self):
        if self.type == 'dash':
            size = self.size + self.audio_size
        else:
            size = self.size

        # estimate size based on size of downloaded fragments
        if not size and self._segments:
            sizes = [seg.size for seg in self.segments if seg.size]
            if sizes:
                avg_seg_size = sum(sizes)//len(sizes)
                size = avg_seg_size * len(self._segments)  # estimated

        return size

    @property
    def speed(self):
        """return an average of some speed values will give a stable speed reading"""
        if self.status != config.Status.downloading or not self.speed_buffer:
            return 0
        else:
            avg_speed = sum(self.speed_buffer) / len(self.speed_buffer)
            if len(self.speed_buffer) > 10:
                self.speed_buffer.popleft()
            return avg_speed

    @property
    def downloaded(self):
        return self._downloaded

    @downloaded.setter
    def downloaded(self, value):
        """this property might be set from threads, expecting int (number of bytes)"""
        if not isinstance(value, int):
            return

        with lock:
            self.download_buffer += value - self._downloaded  # add only the difference
            self._downloaded = value

            # todo: should move below to speed property
            # speed related triggers
            if time.time() - self.speed_timer > self.speed_refresh_rate:
                _speed = self.download_buffer / self.speed_refresh_rate
                self.speed_buffer.append(_speed)

                self.download_buffer = 0  # reset buffer
                self.speed_timer = time.time()  # reset timer

    @property
    def progress(self):
        if self.status == config.Status.completed:
            p = 100
        elif self.total_size == 0:
            # to handle fragmented files
            finished = len([seg for seg in self.segments if seg.completed])  if self.segments else 0 # len(self.segments) - self.remaining_parts
            p = round(finished * 100 / len(self.segments), 1)
        else:
            p = round(self.downloaded * 100 / self.total_size, 1)

        return p if p <= 100 else 100

    @property
    def time_left(self):
        if self.status == config.Status.downloading and self.size:
            return (self.total_size - self.downloaded) / self.speed if self.speed else -1
        else:
            return '---'

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

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
    def target_file(self):
        """return file name including path"""
        return os.path.join(self.folder, self.name)

    @property
    def temp_file(self):
        """return temp file name including path"""
        name = f'_temp_{self.name}'.replace(' ', '_')
        return os.path.join(self.folder, name)

    @property
    def audio_file(self):
        """return temp file name including path"""
        name = f'audio_for_{self.name}'.replace(' ', '_')
        return os.path.join(self.folder, name)

    @property
    def temp_folder(self):
        return f'{self.temp_file}_parts_'

    @property
    def temp_audio_folder(self):
        return f'{self.audio_file}_parts_'

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
        self._segment_size = config.segment_size
        return self._segment_size

    @segment_size.setter
    def segment_size(self, value):
        self._segment_size = value if value <= self.size else self.size
        # print('segment size = ', self._segment_size)

    @property
    def sched_string(self):
        # t = time.localtime(self.sched)
        # return f"⏳({t.tm_hour}:{t.tm_min})"
        return f"{self.sched[0]:02}:{self.sched[1]:02}"

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
                try:
                    name = headers['content-disposition'].split(';')[1]
                    name = name.split('=')[1].strip()
                except:
                    pass

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
        self.folder = None

        # reset audio field
        self.audio_url = None
        self.audio_size = 0

        # reset queues
        self.q.reset()

        # reset segments
        self.reset_segments()

    def __repr__(self):
        """used with functions like print, it will return all properties in this object"""
        output = ''
        for k, v in self.__dict__.items():
            output += f"{k}: {v} \n"
        return output

    def delete_tempfiles(self):
        """delete temp files and folder for a given download item"""
        delete_file(self.temp_file)
        delete_folder(self.temp_folder)

        if self.type == 'dash':
            delete_file(self.audio_file)
            # delete_folder(self.temp_audio_folder)

    def get_size(self):
        """fetch headers for all segments and get size, use with care it is a time / resource consumer task"""
        main_segments = [seg for seg in self.segments if seg.targetfile == self.target_file]
        audio_segments = [seg for seg in self.segments if seg.targetfile == self.audio_file]

        for seg in main_segments:
            self.size += seg.get_size()

        for seg in audio_segments:
            self.audio_size += seg.get_size()
