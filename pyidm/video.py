"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""
import copy
import os
import re
import zipfile
import time
from urllib.parse import urljoin

from . import config
from .downloaditem import DownloadItem, Segment
from .utils import log, validate_file_name, get_headers, size_format, run_command, size_splitter, get_seg_size, \
    delete_file, download, process_thumbnail

# youtube-dl
ytdl = None  # youtube-dl will be imported in a separate thread to save loading time


class Logger(object):
    """used for capturing youtube-dl stdout/stderr output"""

    def debug(self, msg):
        log(msg)

    def error(self, msg):
        log(msg)

    def warning(self, msg):
        log(msg)

    def __repr__(self):
        return "youtube-dl Logger"


def get_ytdl_options():
    ydl_opts = {'ignore_errors': True, 'prefer_insecure': False, 'no_warnings': False, 'logger': Logger()}
    if config.proxy:
        ydl_opts['proxy'] = config.proxy

    # set Referer website
    if config.referer_url:
        # this is not accessible via youtube-dl options, changing standard headers is the only way
        ytdl.utils.std_headers['Referer'] = config.referer_url

    # website authentication
    if config.username or config.password:
        ydl_opts['username'] = config.username
        ydl_opts['password'] = config.password

    # if config.log_level >= 3:
        # ydl_opts['verbose'] = True  # it make problem with Frozen PyIDM, extractor doesn't work
    # elif config.log_level <= 1:
    #     ydl_opts['quiet'] = True  # it doesn't work

    return ydl_opts


class Video(DownloadItem):
    """represent a youtube video object, interface for youtube-dl"""

    def __init__(self, url, vid_info=None):
        super().__init__(folder=config.download_folder)
        self.url = url
        self.resumable = True
        self.vid_info = vid_info  # a youtube-dl dictionary contains video information

        # let youtube-dl fetch video info
        if self.vid_info is None:
            with ytdl.YoutubeDL(get_ytdl_options()) as ydl:
                self.vid_info = ydl.extract_info(self.url, download=False, process=True)

        self.webpage_url = url  # self.vid_info.get('webpage_url')
        self.title = validate_file_name(self.vid_info.get('title', f'video{int(time.time())}'))
        self.name = self.title

        # streams
        self.stream_names = []  # names in a list
        self.raw_stream_names = []  # names but without size
        self.stream_list = []  # streams in a list
        self.video_streams = {}
        self.mp4_videos = {}
        self.other_videos = {}
        self.audio_streams = {}
        self._streams = {}
        self.raw_streams = {}

        self.stream_menu = []  # it will be shown in video quality combo box != self.stream.names
        self.raw_stream_menu = []  # same as self.stream_menu but without size
        self._selected_stream = None

        # thumbnail
        self.thumbnail_url = ''

        # flag for processing raw video info by youtube-dl
        self.processed = False

        self.setup()

    def setup(self):
        url = self.vid_info.get('url', None) or self.vid_info.get('webpage_url', None) or self.vid_info.get('id', None)
        if url:
            self.url = url

        self.webpage_url = url  # self.vid_info.get('webpage_url')
        self.name = self.title = validate_file_name(self.vid_info.get('title', f'video{int(time.time())}'))

        # thumbnail
        self.thumbnail_url = self.vid_info.get('thumbnail', '')

        # build streams
        self._process_streams()

    def _process_streams(self):
        """ Create Stream object lists"""
        all_streams = [Stream(x) for x in self.vid_info['formats']]
        all_streams.reverse()  # get higher quality first

        # prepare some categories
        normal_streams = {stream.raw_name: stream for stream in all_streams if stream.mediatype == 'normal'}
        dash_streams = {stream.raw_name: stream for stream in all_streams if stream.mediatype == 'dash'}

        # normal streams will overwrite same streams names in dash
        video_streams = {**dash_streams, **normal_streams}

        # sort streams based on quality, "youtube-dl will provide a sorted list, this step is not necessary"
        video_streams = {k: v for k, v in sorted(video_streams.items(), key=lambda item: item[1].quality, reverse=True)}

        # sort based on mp4 streams first
        mp4_videos = {stream.name: stream for stream in video_streams.values() if stream.extension == 'mp4'}
        other_videos = {stream.name: stream for stream in video_streams.values() if stream.extension != 'mp4'}
        video_streams = {**mp4_videos, **other_videos}

        audio_streams = {stream.name: stream for stream in all_streams if stream.mediatype == 'audio'}

        # add another audio formats, mp3, aac, wav, ogg
        if audio_streams:
            audio = list(audio_streams.values())
            webm = [stream for stream in audio if stream.extension == 'webm']
            m4a = [stream for stream in audio if stream.extension in ('m4a')]

            aac = m4a[0] if m4a else audio[0]
            aac = copy.copy(aac)
            aac.extension = 'aac'

            ogg = webm[0] if webm else audio[0]
            ogg = copy.copy(ogg)
            ogg.extension = 'ogg'

            mp3 = copy.copy(aac)
            mp3.extension = 'mp3'
            mp3.abr = 128

            extra_audio = {aac.name: aac, ogg.name: ogg, mp3.name: mp3}
            extra_audio.update(**audio_streams)
            audio_streams = extra_audio

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
            raise TypeError('value must be a Stream object')

        self._selected_stream = stream
        self.selected_quality = stream.raw_name

        self.update_param()

    def get_thumbnail(self):
        if self.thumbnail_url and not self.thumbnail:
            self.thumbnail = process_thumbnail(self.thumbnail_url)

    def update_param(self, audio_stream=None):
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
        self.manifest_url = stream.manifest_url

        # select an audio to embed if our stream is dash video
        # audio streams in a list
        audio_streams_list = [stream for stream in self.stream_list if stream.mediatype == 'audio']

        # sort audio list
        audio_streams_list = sorted(audio_streams_list, key=lambda stream: stream.quality, reverse=True)

        if stream.mediatype == 'dash' and audio_streams_list:
            # auto select audio stream
            if not audio_stream:
                matching_stream = [audio for audio in audio_streams_list if audio.extension == stream.extension
                            or (audio.extension == 'm4a' and stream.extension == 'mp4')]
                # if failed to find a matching audio, choose any one
                if matching_stream:
                    audio_stream = matching_stream[0]
                else:
                    audio_stream = audio_streams_list[0]

            self.audio_stream = audio_stream
            self.audio_url = audio_stream.url
            self.audio_size = audio_stream.size
            self.audio_fragment_base_url = audio_stream.fragment_base_url
            self.audio_fragments = audio_stream.fragments
            self.audio_format_id = audio_stream.format_id
        else:
            self.audio_url = None
            self.audio_fragment_base_url = None
            self.audio_fragments = None

    def refresh(self):
        # update properties
        self.setup()


def process_video_info(vid, getthumbnail=True):
    try:
        with ytdl.YoutubeDL(get_ytdl_options()) as ydl:
            vid.vid_info = ydl.process_ie_result(vid.vid_info, download=False)
            vid.refresh()
            vid.processed = True

        if getthumbnail:
            vid.get_thumbnail()

        log('process_video_info()> processed url:', vid.url, log_level=3)
    except Exception as e:
        log('process_video_info()> error:', e)


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

        # hls stream specific
        self.manifest_url = stream_info.get('manifest_url', '')

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


def download_ffmpeg(destination=config.sett_folder):
    """it should download ffmpeg.exe for windows os"""

    # set download folder
    config.ffmpeg_download_folder = destination

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
    # print('config.sett_folder = ', config.sett_folder)
    d = DownloadItem(url=url, folder=config.ffmpeg_download_folder)
    d.update(url)
    d.name = 'ffmpeg.zip'  # must rename it for unzip to find it
    # print('d.folder = ', d.folder)

    # post download
    d.callback = 'unzip_ffmpeg'

    # send download request to main window
    config.main_window_q.put(('download', (d, False)))


def unzip_ffmpeg():
    log('unzip_ffmpeg:', 'unzipping')

    try:
        file_name = os.path.join(config.ffmpeg_download_folder, 'ffmpeg.zip')
        with zipfile.ZipFile(file_name, 'r') as zip_ref:  # extract zip file
            zip_ref.extractall(config.ffmpeg_download_folder)

        log('ffmpeg update:', 'delete zip file')
        delete_file(file_name)
        log('ffmpeg update:', 'ffmpeg .. is ready at: ', config.ffmpeg_download_folder)
    except Exception as e:
        log('unzip_ffmpeg: error ', e)


def check_ffmpeg():
    """check for ffmpeg availability, first: current folder, second config.global_sett_folder,
    and finally: system wide"""

    log('check ffmpeg availability?')
    found = False

    # search in current app directory then default setting folder
    try:
        for folder in [config.current_directory, config.global_sett_folder]:
            for file in os.listdir(folder):
                # print(file)
                if file == 'ffmpeg.exe':
                    found = True
                    config.ffmpeg_actual_path = os.path.join(folder, file)
                    break
            if found:  # break outer loop
                break
    except:
        pass

    # Search in the system
    if not found:
        cmd = 'where ffmpeg' if config.operating_system == 'Windows' else 'which ffmpeg'
        error, output = run_command(cmd, verbose=False)
        if not error:
            found = True

            # fix issue 47 where command line return \n\r with path
            output = output.strip()
            config.ffmpeg_actual_path = os.path.realpath(output)

    if found:
        log('ffmpeg checked ok! - at: ', config.ffmpeg_actual_path)
        return True
    else:
        log(f'can not find ffmpeg!!, install it, or add executable location to PATH, or copy executable to ',
            config.global_sett_folder, 'or', config.current_directory)


def merge_video_audio(video, audio, output, d):
    """merge video file and audio file into output file, d is a reference for current DownloadItem object"""
    log('merging video and audio')

    # ffmpeg file full location
    ffmpeg = config.ffmpeg_actual_path

    # very fast audio just copied, format must match [mp4, m4a] and [webm, webm]
    cmd1 = f'"{ffmpeg}" -y -i "{video}" -i "{audio}" -c copy "{output}"'

    # slow, mix different formats
    cmd2 = f'"{ffmpeg}" -y -i "{video}" -i "{audio}" "{output}"'

    verbose = True if config.log_level >= 2 else False

    # run command with shell=False if failed will use shell=True option
    error, output = run_command(cmd1, verbose=verbose, shell=True, d=d)

    # retry on error with cmd2
    if error:
        error, output = run_command(cmd2, verbose=verbose, shell=True, d=d)

    return error, output
            

def import_ytdl():
    # import youtube_dl using thread because it takes sometimes 20 seconds to get imported and impact app startup time
    start = time.time()
    global ytdl, ytdl_version
    try:
        import youtube_dl as ytdl

        # update version value
        config.ytdl_VERSION = ytdl.version.__version__

        # get a random user agent and update headers
        config.HEADERS['User-Agent'] = ytdl.utils.random_user_agent()

        # calculate loading time
        load_time = time.time() - start
        log(f'youtube-dl load_time= {int(load_time)} seconds')
    except Exception as e:
        log('import_ytdl()> error', e)


def pre_process_hls(d):
    """handle m3u8 list and build a url list of file segments"""

    log('pre_process_hls()> start processing', d.name)

    # get correct url of m3u8 file
    def get_correct_m3u8_url(master_m3u8_doc, media='video'):
        if not master_m3u8_doc:
            return False

        lines = master_m3u8_doc.splitlines()
        for i, line in enumerate(lines):

            if media == 'video' and (str(d.selected_stream.width) in line and str(
                    d.selected_stream.height) in line or d.format_id in line):
                correct_url = urljoin(d.manifest_url, lines[i + 1])
                return correct_url
            elif media == 'audio' and (str(d.audio_stream.abr) in line or str(
                    d.selected_stream.tbr) in line or d.format_id in line):
                correct_url = urljoin(d.manifest_url, lines[i + 1])
                return correct_url

    def extract_url_list(m3u8_doc):
        # url_list
        url_list = []
        keys = []  # for encrypted streams

        for line in m3u8_doc.splitlines():
            line.strip()
            if line and not line.startswith('#'):
                url_list.append(line)
            elif line.startswith('#EXT-X-KEY'):
                # '#EXT-X-KEY:METHOD=AES-128,URI="https://content-aus...62a9",IV=0x00000000000000000000000000000000'
                match = re.search(r'URI="(.*)"', line)
                if match:
                    url = match.group(1)
                    keys.append(url)

        # log('process hls> url list:', url_list)
        return url_list, keys

    def download_m3u8(url):
        # download the manifest from m3u8 file descriptor located at url
        buffer = download(url)  # get BytesIO object

        if buffer:
            # convert to string
            buffer = buffer.getvalue().decode()
            if '#EXT' in repr(buffer):
                return buffer

        log('pre_process_hls()> received invalid m3u8 file from server')
        if config.log_level >= 3:
            log('---------------------------------------\n', buffer, '---------------------------------------\n')
        return None

    # download m3u8 files
    master_m3u8 = download_m3u8(d.manifest_url)
    video_m3u8 = download_m3u8(d.eff_url)
    audio_m3u8 = download_m3u8(d.audio_url)

    if not video_m3u8:
        eff_url = get_correct_m3u8_url(master_m3u8, media='video')
        if not eff_url:
            log('pre_process_hls()> Failed to get correct video m3u8 url, quitting!')
            return False
        else:
            d.eff_url = eff_url
            video_m3u8 = download_m3u8(d.eff_url)

    if d.type == 'dash' and not audio_m3u8:
        eff_url = get_correct_m3u8_url(master_m3u8, media='audio')
        if not eff_url:
            log('pre_process_hls()> Failed to get correct audio m3u8 url, quitting!')
            return False
        else:
            d.audio_url = eff_url
            audio_m3u8 = download_m3u8(d.audio_url)

    # first lets handle video stream
    video_url_list, video_keys_url_list = extract_url_list(video_m3u8)

    # get absolute path from url_list relative path
    video_url_list = [urljoin(d.eff_url, seg_url) for seg_url in video_url_list]
    video_keys_url_list = [urljoin(d.eff_url, seg_url) for seg_url in video_keys_url_list]

    # create temp_folder if doesn't exist
    if not os.path.isdir(d.temp_folder):
        os.makedirs(d.temp_folder)

    # save m3u8 file to disk
    with open(os.path.join(d.temp_folder, 'remote_video.m3u8'), 'w') as f:
        f.write(video_m3u8)

    # build video segments
    d.segments = [Segment(name=os.path.join(d.temp_folder, str(i) + '.ts'), num=i, range=None, size=0,
                          url=seg_url, tempfile=d.temp_file, merge=True)
                  for i, seg_url in enumerate(video_url_list)]

    # add video crypt keys
    vkeys = [Segment(name=os.path.join(d.temp_folder, 'crypt' + str(i) + '.key'), num=i, range=None, size=0,
                          url=seg_url, seg_type='video_key', merge=False)
                  for i, seg_url in enumerate(video_keys_url_list)]

    # add to d.segments
    d.segments += vkeys

    # handle audio stream in case of dash videos
    if d.type == 'dash':
        audio_url_list, audio_keys_url_list = extract_url_list(audio_m3u8)

        # get absolute path from url_list relative path
        audio_url_list = [urljoin(d.audio_url, seg_url) for seg_url in audio_url_list]
        audio_keys_url_list = [urljoin(d.audio_url, seg_url) for seg_url in audio_keys_url_list]

        # save m3u8 file to disk
        with open(os.path.join(d.temp_folder, 'remote_audio.m3u8'), 'w') as f:
            f.write(audio_m3u8)

        # build audio segments
        audio_segments = [Segment(name=os.path.join(d.temp_folder, str(i) + '_audio.ts'), num=i, range=None, size=0,
                                  url=seg_url, tempfile=d.audio_file, merge=False)
                          for i, seg_url in enumerate(audio_url_list)]

        # audio crypt segments
        akeys = [Segment(name=os.path.join(d.temp_folder, 'audio_crypt' + str(i) + '.key'), num=i, range=None, size=0,
                                  url=seg_url, seg_type='audio_key', merge=False)
                          for i, seg_url in enumerate(audio_keys_url_list)]

        # add to video segments
        d.segments += audio_segments + akeys

    # load previous segment information from disk - resume download -
    d.load_progress_info()

    log('pre_process_hls()> done processing', d.name)

    return True


def post_process_hls(d):
    """ffmpeg will process m3u8 files"""

    log('post_process_hls()> start processing', d.name)

    def create_local_m3u8(remote_file, local_file, local_names, crypt_key_names=None):

        with open(remote_file, 'r') as f:
            lines = f.readlines()

        names = [f'{name}\n' for name in local_names]
        names.reverse()

        crypt_key_names.reverse()

        # log(len([a for a in lines if not a.startswith('#')]))

        for i, line in enumerate(lines[:]):
            if line and not line.startswith('#'):
                try:
                    name = names.pop()
                    lines[i] = name
                except:
                    pass
            elif line.startswith('#EXT-X-KEY'):
                # '#EXT-X-KEY:METHOD=AES-128,URI="https://content-aus...62a9",IV=0x00000000000000000000000000000000'
                match = re.search(r'URI="(.*)"', line)
                if match:
                    try:
                        key_name = crypt_key_names.pop()
                        key_name = key_name.replace('\\', '/')
                        lines[i] = line.replace(match.group(1), key_name)
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
        crypt_key_names = [seg.name for seg in d.segments if seg.seg_type == 'video_key']
        create_local_m3u8(remote_video_m3u8_file, local_video_m3u8_file, names, crypt_key_names)
    except Exception as e:
        log('post_process_hls()> error', e)
        return False

    if d.type == 'dash':
        # create local m3u8 version - audio
        remote_audio_m3u8_file = os.path.join(d.temp_folder, 'remote_audio.m3u8')
        local_audio_m3u8_file = os.path.join(d.temp_folder, 'local_audio.m3u8')

        try:
            names = [seg.name for seg in d.segments if seg.tempfile == d.audio_file]
            crypt_key_names = [seg.name for seg in d.segments if seg.seg_type == 'audio_key']
            create_local_m3u8(remote_audio_m3u8_file, local_audio_m3u8_file, names, crypt_key_names)
        except Exception as e:
            log('post_process_hls()> error', e)
            return False

    # now processing with ffmpeg
    # note: ffmpeg doesn't support socks proxy, also proxy must start with "http://"
    # currently will download crypto keys manually and use ffmpeg for merging only

    # proxy = f'-http_proxy "{config.proxy}"' if config.proxy else ''

    cmd = f'"{config.ffmpeg_actual_path}" -y -protocol_whitelist "file,http,https,tcp,tls,crypto"  ' \
          f'-allowed_extensions ALL -i "{local_video_m3u8_file}" -c copy -f mp4 "file:{d.temp_file}"'

    error, output = run_command(cmd, d=d)
    if error:
        log('post_process_hls()> ffmpeg failed:', output)
        return False

    if d.type == 'dash':
        cmd = f'"{config.ffmpeg_actual_path}" -y -protocol_whitelist "file,http,https,tcp,tls,crypto"  ' \
              f'-allowed_extensions ALL -i "{local_audio_m3u8_file}" -c copy -f mp4 "file:{d.audio_file}"'

        error, output = run_command(cmd, d=d)
        if error:
            log('post_process_hls()> ffmpeg failed:', output)
            return False

    log('post_process_hls()> done processing', d.name)

    return True


def convert_audio(d):
    # famous formats: mp3, aac, wav, ogg
    infile = d.temp_file
    outfile = d.target_file

    # look for compatible formats and use "copy" parameter for faster processing
    cmd1 = f'ffmpeg -y -i "{infile}" -acodec copy "{outfile}"'

    # general command, consume time
    cmd2 = f'ffmpeg -y -i "{infile}" "{outfile}"'

    # run command1
    error, _ = run_command(cmd1, verbose=True, shell=True)

    if error:
        error, _ = run_command(cmd2, verbose=True, shell=True)

    if error:
        return False
    else:
        return True





















