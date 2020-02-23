"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""

import os
import subprocess
import zipfile
import time
from urllib.parse import urljoin

from . import config
from .downloaditem import DownloadItem, Segment
from .utils import log, validate_file_name, get_headers, size_format, run_command, size_splitter, get_seg_size, \
    delete_file, download

# youtube-dl
ytdl = None  # youtube-dl will be imported in a separate thread to save loading time


class Logger(object):
    """used for capturing youtube-dl messages"""

    def debug(self, msg):
        log(msg)

    def error(self, msg):
        log('error: %s' % msg)

    def warning(self, msg):
        log('warning: %s' % msg)

    def __repr__(self):
        return "youtube-dl Logger"


def get_ytdl_options():
    ydl_opts = {'quiet': True, 'prefer_insecure': True, 'no_warnings': False, 'logger': Logger(), }
    if config.proxy:
        ydl_opts['proxy'] = config.proxy
    return ydl_opts


class Video(DownloadItem):
    """represent a youtube video object, interface for youtube-dl"""

    def __init__(self, url, vid_info=None, get_size=True):
        super().__init__(folder=config.download_folder)
        self.url = url
        self.resumable = True
        self.vid_info = vid_info  # a youtube-dl dictionary contains video information

        if self.vid_info is None:
            with ytdl.YoutubeDL(get_ytdl_options()) as ydl:
                self.vid_info = ydl.extract_info(self.url, download=False)

        self.webpage_url = url  # self.vid_info.get('webpage_url')
        self.title = validate_file_name(self.vid_info.get('title', f'video{int(time.time())}'))
        self.name = self.title

        # streams
        self.stream_names = []  # names in a list
        self.raw_stream_names = [] # names but without size
        self.stream_list = []  # streams in a list
        self.video_streams = {}
        self.mp4_videos = {}
        self.other_videos = {}
        self.audio_streams = {}
        self._streams = {}
        self.raw_streams = {}

        self.stream_menu = []  # it will be shown in video quality combo box != self.stream.names
        self.raw_stream_menu = [] # same as self.stream_menu but without size
        self._selected_stream = None

        # self.audio_url = None  # None for non dash videos
        # self.audio_size = 0

        self.setup()

    def setup(self):
        self._process_streams()

    def _process_streams(self):
        """ Create Stream object lists"""
        all_streams = [Stream(x) for x in self.vid_info['formats']]

        # prepare some categories
        normal_streams = {stream.raw_name: stream for stream in all_streams if stream.mediatype == 'normal'}
        dash_streams = {stream.raw_name: stream for stream in all_streams if stream.mediatype == 'dash'}

        # normal streams will overwrite same streams names in dash
        video_streams = {**dash_streams, **normal_streams}

        # sort streams based on quality
        video_streams = {k: v for k, v in sorted(video_streams.items(), key=lambda item: item[1].quality, reverse=True)}

        # sort based on mp4 streams first
        mp4_videos = {stream.name: stream for stream in video_streams.values() if stream.extension == 'mp4'}
        other_videos = {stream.name: stream for stream in video_streams.values() if stream.extension != 'mp4'}
        video_streams = {**mp4_videos, **other_videos}

        audio_streams = {stream.name: stream for stream in all_streams if stream.mediatype == 'audio'}

        # collect all in one dictionary of stream.name: stream pairs
        streams = {**video_streams, **audio_streams}

        stream_menu = ['● Video streams:                     '] + list(mp4_videos.keys()) + list(other_videos.keys()) \
                    + ['', '● Audio streams:                 '] + list(audio_streams.keys())

        # assign variables
        self.stream_list = list(streams.values())
        self.stream_names = [stream.name for stream in self.stream_list]
        self.raw_stream_names = [stream.raw_name for stream in self.stream_list]
        self.video_streams = video_streams
        self.mp4_videos = mp4_videos
        self.other_videos = other_videos
        self.audio_streams = audio_streams

        self._streams = streams
        self.raw_streams = {stream.raw_name: stream for stream in streams.values()}
        self.stream_menu = stream_menu
        self.raw_stream_menu = [x.rsplit(' -', 1)[0] for x in stream_menu]

    @property
    def streams(self):
        """ Returns dictionary of all streams sorted  key=stream.name, value=stream object"""
        if not self._streams:
            self._process_streams()

        return self._streams

    @property
    def selected_stream_index(self):
        return self.stream_list.index(self.selected_stream)

    @property
    def selected_stream(self):
        if not self._selected_stream:
            self._selected_stream = self.stream_list[0]  # select first stream

        return self._selected_stream

    @selected_stream.setter
    def selected_stream(self, stream):
        if type(stream) is not Stream:
            raise TypeError

        self._selected_stream = stream

        self.update_param()

    def update_param(self):
        # do some parameter updates
        stream = self.selected_stream
        self.name = self.title + '.' + stream.extension
        self.eff_url = stream.url
        self.type = stream.mediatype
        self.size = stream.size
        self.fragment_base_url = stream.fragment_base_url
        self.fragments = stream.fragments
        self.protocol = stream.protocol
        self.format_id = stream.format_id

        # select an audio to embed if our stream is dash video
        if stream.mediatype == 'dash':
            audio_stream = [audio for audio in self.audio_streams.values() if audio.extension == stream.extension
                            or (audio.extension == 'm4a' and stream.extension == 'mp4')][0]
            self.audio_url = audio_stream.url
            self.audio_size = audio_stream.size
            self.audio_fragment_base_url = audio_stream.fragment_base_url
            self.audio_fragments = audio_stream.fragments
            self.audio_format_id = audio_stream.format_id
        else:
            self.audio_url = None
            self.audio_fragment_base_url = None
            self.audio_fragments = None


class Stream:
    def __init__(self, stream_info):
        # fetch data from youtube-dl stream_info dictionary
        self.format_id = stream_info.get('format_id', None)
        self.url = stream_info.get('url', None)
        self.player_url = stream_info.get('player_url', None)
        self.extension = stream_info.get('ext', None)
        self.width = stream_info.get('width', None)
        self.fps = stream_info.get('fps', None)
        self.height = stream_info.get('height', 0)
        self.format_note = stream_info.get('format_note', None)
        self.acodec = stream_info.get('acodec', None)
        self.abr = stream_info.get('abr', 0)
        self.size = stream_info.get('filesize', None)
        self.tbr = stream_info.get('tbr', None)
        # self.quality = stream_info.get('quality', None)
        self.vcodec = stream_info.get('vcodec', None)
        self.res = stream_info.get('resolution', None)
        self.downloader_options = stream_info.get('downloader_options', None)
        self.format = stream_info.get('format', None)
        self.container = stream_info.get('container', None)

        # protocol
        self.protocol = stream_info.get('protocol', '')

        # calculate some values
        self.rawbitrate = stream_info.get('abr', 0) * 1024
        self._mediatype = None
        self.resolution = f'{self.width}x{self.height}' if (self.width and self.height) else ''

        # fragmented video streams
        self.fragment_base_url = stream_info.get('fragment_base_url', None)
        self.fragments = stream_info.get('fragments', None)

        # get missing size
        if self.fragments or 'm3u8' in self.protocol:
            # ignore fragmented streams, since the size coming from headers is for first fragment not whole file
            self.size = 0
        if not isinstance(self.size, int):
            self.size = self.get_size()

        # print(self.name, self.size, isinstance(self.size, int))

    def get_size(self):
        headers = get_headers(self.url)
        size = int(headers.get('content-length', 0))
        print('stream.get_size()>', self.name)
        return size

    @property
    def name(self):
        return f'      ›  {self.extension} - {self.quality} - {size_format(self.size)}'  # ¤ » ›

    @property
    def raw_name(self):
        return f'      ›  {self.extension} - {self.quality}'

    @property
    def quality(self):
        try:
            if self.mediatype == 'audio':
                return int(self.abr)
            else:
                return int(self.height)
        except:
            return 0

    def __repr__(self, include_size=True):
        return self.name

    @property
    def mediatype(self):
        if not self._mediatype:
            if self.vcodec == 'none':
                self._mediatype = 'audio'
            elif self.acodec == 'none':
                self._mediatype = 'dash'
            else:
                self._mediatype = 'normal'

        return self._mediatype


def download_ffmpeg():
    """it should download ffmpeg.exe for windows os"""

    # first check windows 32 or 64
    import platform
    # ends with 86 for 32 bit and 64 for 64 bit i.e. Win7-64: AMD64 and Vista-32: x86
    if platform.machine().endswith('64'):
        # 64 bit link
        url = 'https://github.com/pyIDM/pyIDM/releases/download/extra/ffmpeg.zip'
    else:
        # 32 bit link
        url = 'https://github.com/pyIDM/pyIDM/releases/download/extra/ffmpeg_32bit.zip'

    log('downloading: ', url)

    # create a download object, will store ffmpeg in setting folder
    print('config.sett_folder = ', config.sett_folder)
    d = DownloadItem(url=url, folder=config.sett_folder)
    d.update(url)
    d.name = 'ffmpeg.zip'  # must rename it for unzip to find it
    print('d.folder = ', d.folder)

    # post download
    d.callback = 'unzip_ffmpeg'

    # send download request to main window
    config.main_window_q.put(('download', (d, False)))


def unzip_ffmpeg():
    log('unzip_ffmpeg:', 'unzipping')

    try:
        file_name = os.path.join(config.sett_folder, 'ffmpeg.zip')
        with zipfile.ZipFile(file_name, 'r') as zip_ref:  # extract zip file
            zip_ref.extractall(config.sett_folder)

        log('ffmpeg update:', 'delete zip file')
        delete_file(file_name)
        log('ffmpeg update:', 'ffmpeg .. is ready at: ', config.sett_folder)
    except Exception as e:
        log('unzip_ffmpeg: error ', e)


def check_ffmpeg():
    """check for ffmpeg availability, first: config.sett_folder, second: current folder,
    and finally: system wide"""

    log('check ffmpeg availability?')
    found = False

    # search in default installation folder then current directory
    for folder in [config.sett_folder, config.current_directory]:
        for file in os.listdir(folder):
            # print(file)
            if file == 'ffmpeg.exe':
                found = True
                config.ffmpeg_actual_path = os.path.join(folder, file)
                break
        if found:  # break outer loop
            break

    # Search in the system
    if not found:
        cmd = 'where ffmpeg' if config.operating_system == 'Windows' else 'which ffmpeg'
        error, output = run_command(cmd, verbose=False)
        if not error:
            found = True
            config.ffmpeg_actual_path = os.path.realpath(output)

    if found:
        log('ffmpeg checked ok! - at: ', config.ffmpeg_actual_path)
        return True
    else:
        log(f'can not find ffmpeg!!, install it, or add executable location to PATH, or copy executable to ',
            config.sett_folder, 'or', config.current_directory)


def merge_video_audio(video, audio, output):
    log('merging video and audio')
    # ffmpeg
    ffmpeg = config.ffmpeg_actual_path  # 'ffmpeg'  # os.path.join(current_directory, 'ffmpeg', 'ffmpeg')

    # very fast audio just copied, format must match [mp4, m4a] and [webm, webm]
    cmd1 = f'"{ffmpeg}" -i "{video}" -i "{audio}" -c copy "{output}"'

    # slow, mix different formats
    cmd2 = f'"{ffmpeg}" -i "{video}" -i "{audio}" "{output}"'

    # run command with shell=False if failed will use shell=True option
    error, output = run_command(cmd1, verbose=True, shell=False)

    if error:
        error, output = run_command(cmd1, verbose=True, shell=True)

    if error:
        error, output = run_command(cmd2, verbose=True, shell=True)

    return error, output
            

def import_ytdl():
    # import youtube_dl using thread because it takes sometimes 20 seconds to get imported and impact app startup time
    start = time.time()
    global ytdl, ytdl_version
    import youtube_dl as ytdl
    config.ytdl_VERSION = ytdl.version.__version__

    load_time = time.time() - start
    log(f'youtube-dl load_time= {load_time}')


def youtube_dl_downloader(d=None, extra_options=None):
    """download with youtube_dl"""
    options = {}
    downloaded = {}

    def progress_hook(progress_dict):
        print(progress_dict)

        # when downloading 2 streams "i.e. dash video and audio" downloaded_bytes will be reset to zero and report
        # wrong total downloaded bytes, fix >> use  a dictionary to store every stream progress
        downloaded_bytes = progress_dict.get('downloaded_bytes', 0)
        file_name = progress_dict.get('filename', 'unknown')
        downloaded[file_name] = downloaded_bytes
        d.downloaded = sum(downloaded.values())

        total_bytes = progress_dict.get('total_bytes', 0)

        if file_name == d.temp_file:
            d.size = total_bytes

        elif file_name == d.audio_file:
            d.audio_size = total_bytes

        # monitor cancel flag
        if d.status == config.Status.cancelled:
            log('youtube-dl cancelled download')
            raise KeyboardInterrupt

    options.update(**get_ytdl_options())

    if isinstance(extra_options, dict):
        options.update(**extra_options)

    options['progress_hooks'] = [progress_hook]
    options['quiet'] = False
    options['verbose'] = True
    options['hls-prefer-native'] = True
    options['format'] = d.format_id
    options['outtmpl'] = d.temp_file

    # start downloading
    try:
        with ytdl.YoutubeDL(options) as ydl:
            ydl.download([d.url])
    except Exception as e:
        log('youtube_dl_downloader()> ', e)
        # raise e
        return False

    # audio file -------------------------------------
    if d.type == 'dash':
        options['format'] = f'{d.audio_format_id}/bestaudio'
        options['outtmpl'] = d.audio_file

        # start downloading
        try:
            with ytdl.YoutubeDL(options) as ydl:
                ydl.download([d.url])
        except Exception as e:
            log('youtube_dl_downloader()> ', e)
            # raise e
            return False

    # mux audio/video
    if d.type == 'dash':
        audio, video = d.audio_file, d.temp_file  # file_names.pop(), file_names.pop()

        # set status to merge
        d.status = config.Status.merging_audio

        error, output = merge_video_audio(video, audio, d.target_file)
        if error:
            log('failed to merge', d.target_file, output)
            return False
        else:
            delete_file(video)
            delete_file(audio)

    return True


def hls_downloader(d):
    cmd = f'"ffmpeg" -y -i "{d.eff_url}" -c copy -f mp4 "file:{d.temp_file}"'
    error, output = run_command(cmd)
    if error:
        return False
    else:
        return True


def pre_process_hls(d):
    """handle m3u8 list and build a url list of file segments"""
    def get_url_list(url):
        # url_list
        url_list = []

        # download the manifest from m3u8 file descriptor located at url
        print('process hls> process url:', url)
        buffer = download(url)  # get BytesIO object

        if buffer:
            # convert to string
            buffer = buffer.getvalue().decode()
            for line in buffer.splitlines():
                line.strip()
                if line and not line.startswith('#'):
                    url_list.append(line)

            # get absolute path from url_list relative path
            url_list = [urljoin(url, seg_url) for seg_url in url_list]

        # print('process hls> url list:', url_list)
        return buffer, url_list

    # todo: need to validate the buffer if it really a valid m3u8 file, not just any junk
    # if video_m3u8 is not valid m3u8 file return False

    # first lets handle video stream
    video_m3u8, video_url_list = get_url_list(d.eff_url)

    # save m3u8 file to disk
    # create temp_folder if doesn't exist
    if not os.path.isdir(d.temp_folder):
        os.makedirs(d.temp_folder)

    with open(os.path.join(d.temp_folder, 'remote_video.m3u8'), 'w') as f:
        f.write(video_m3u8)

    # build video segments
    d.segments = [Segment(name=os.path.join(d.temp_folder, str(i) + '.ts'), num=i, range=None, size=0,
                          url=seg_url, tempfile=d.temp_file)
                  for i, seg_url in enumerate(video_url_list)]

    # handle audio stream in case of dash videos
    if d.type == 'dash':
        audio_m3u8, audio_url_list = get_url_list(d.audio_url)

        # save m3u8 file to disk
        with open(os.path.join(d.temp_folder, 'remote_audio.m3u8'), 'w') as f:
            f.write(audio_m3u8)

        # build audio segments
        audio_segments = [Segment(name=os.path.join(d.temp_folder, str(i) + '_audio.ts'), num=i, range=None, size=0,
                                  url=seg_url, tempfile=d.audio_file)
                          for i, seg_url in enumerate(audio_url_list)]

        # add to video segments
        d.segments += audio_segments

    # load previous segment information from disk - resume download -
    d.load_progress_info()

    return True


def post_process_hls(d):
    """ffmpeg will process m3u8 files"""

    def create_local_m3u8(remote_file, local_file, local_names):

        with open(remote_file, 'r') as f:
            lines = f.readlines()

        names = [f'{name}\n' for name in local_names]
        names.reverse()

        # print(len([a for a in lines if not a.startswith('#')]))

        for i, line in enumerate(lines):
            if line and not line.startswith('#'):
                try:
                    lines[i] = names.pop()
                    print(lines[i])
                except:
                    pass

        with open(local_file, 'w') as f:
            f.writelines(lines)
            # print(lines)

    # create local m3u8 version - video
    remote_video_m3u8_file = os.path.join(d.temp_folder, 'remote_video.m3u8')
    local_video_m3u8_file = os.path.join(d.temp_folder, 'local_video.m3u8')

    try:
        names = [seg.name for seg in d.segments if seg.tempfile == d.temp_file]
        # print('names = ', names)
        create_local_m3u8(remote_video_m3u8_file, local_video_m3u8_file, names)
    except Exception as e:
        log('post_process_hls()> error', e)
        return False

    if d.type == 'dash':
        # create local m3u8 version - audio
        remote_audio_m3u8_file = os.path.join(d.temp_folder, 'remote_audio.m3u8')
        local_audio_m3u8_file = os.path.join(d.temp_folder, 'local_audio.m3u8')

        try:
            create_local_m3u8(remote_audio_m3u8_file, local_audio_m3u8_file,
                              [seg.name for seg in d.segments if seg.tempfile == d.audio_file])
        except Exception as e:
            log('post_process_hls()> error', e)
            return False

    # now processing with ffmpeg
    cmd = f'"{config.ffmpeg_actual_path}" -y -protocol_whitelist "file,http,https,tcp,tls,crypto"  -i ' \
          f'"{local_video_m3u8_file}" -c copy -f mp4 "file:{d.temp_file}"'

    error, output = run_command(cmd)
    if error:
        log('post_process_hls()> ffmpeg failed:', output)
        return False

    if d.type == 'dash':
        cmd = f'"{config.ffmpeg_actual_path}" -y -protocol_whitelist "file,http,https,tcp,tls,crypto"  -i ' \
              f'"{local_audio_m3u8_file}" -c copy -f mp4 "file:{d.audio_file}"'

        error, output = run_command(cmd)
        if error:
            log('post_process_hls()> ffmpeg failed:', output)
            return False

    return True

















