"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""

from .config import Status, active_downloads, main_window_q, APP_NAME
from .utils import (log, size_format, size_splitter, get_seg_size, translate_server_code, popup,
                   handle_exceptions, notify, append_parts, delete_folder)
from threading import Thread, Barrier, Timer, Lock
from queue import Queue
import os
import pickle
from collections import deque
import time
from .downloaditem import DownloadItem
from .worker import Worker
from .video import Video, check_ffmpeg, download_ffmpeg, unzip_ffmpeg, merge_video_audio


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
            if q is main_window_q:
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
        seg_list = size_splitter(d.size, d.segment_size)
    else:
        # will use only one connection because remote server doesn't support chunk download
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
                        msg = f'server refuse connection {code} {translate_server_code(code)}, try to refresh link'
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
                    return True  # as indication of success

                # if this is a dash video, will try to get its audio
                if d.audio_url:
                    d.status = Status.merging_audio
                    d.progress = 99

                    # create a DownloadItem() object for audio
                    audio = DownloadItem()
                    audio.name = d.audio_name
                    audio.size = d.audio_size
                    audio.max_connections = d.max_connections
                    audio.resumable = True
                    audio.url = audio.eff_url = d.audio_url
                    audio.folder = d.folder
                    audio.is_audio = True
                    audio.id = f'{d.num}_audio'
                    audio.max_connections = d.max_connections

                    video_file = d.full_name
                    audio_file = audio.full_name
                    out_file = os.path.join(d.folder, f'out_{d.name}')

                    log('start downloading ', audio.name)

                    done = brain(audio)
                    if done:  # an audio file already downloaded and ready for merge
                        log('start merging video and audio files')
                        error, output = merge_video_audio(video_file, audio_file, out_file)
                        if error:
                            msg = f'Failed to merge {audio.name} \n {output}'
                            log(msg)
                            popup(f'Failed to merge {audio.name}', title='Merge error')
                            status = d.status = Status.cancelled
                            print('d.id:', d.id)
                            active_downloads.remove(d.id)

                        else:

                            log('finished merging video and audio files')
                            try:
                                os.unlink(video_file)
                                os.unlink(audio_file)

                                # Rename main file name
                                os.rename(out_file, video_file)
                            except Exception as e:
                                handle_exceptions(f'brain.merge.delete&rename: {e}')

                            status = d.status = Status.completed
                    else:
                        msg = 'Failed to download ' + audio.name
                        log(msg)
                        # sg.popup_error(msg, title='audio file download error')
                        status = d.status = Status.cancelled

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
                notify(notification, title=f'{APP_NAME} - Download completed')
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
    try:
        print(d.id, active_downloads)
        active_downloads.remove(d.id)
    except:
        pass
    log(f'\nbrain {d.num}: removed item from active downloads')

    # callback, a method or func to call if download completed
    if d.callback and d.status == Status.completed:
        # d.callback()
        globals()[d.callback]()

    # report quitting
    q.log('brain: quitting')
    log(f'\nbrain {d.num}: quitting')


def thread_manager(d, barrier, speed_limit):
    q = d.q
    # create worker/connection list
    connections = [Worker(tag=i, url=d.eff_url, temp_folder=d.temp_folder, q=q, resumable=d.resumable) for i in
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

    use_range = d.resumable and d.size > 0

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
            conn.reuse(seg=seg, speed_limit=worker_sl, use_range=use_range)
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
    all_segments = set(seg_list)
    completed_segments = set()

    # read pickled file contains completed parts names
    cfg_file = os.path.join(d.temp_folder, 'completed.cfg')
    if os.path.isfile(cfg_file):
        with open(cfg_file, 'rb') as f:
            completed_segments = pickle.load(f)

    # target file
    target_file = d.full_name  # os.path.join(d.folder, d.name)

    # check / create temp file
    temp_file = d.full_temp_name
    if not os.path.isfile(temp_file):
        with open(temp_file, 'wb') as f:
            # f.write(b'')
            pass
    # d.temp_file = temp_file
    # d.target_file = target_file

    segments = []

    while True:
        time.sleep(0.1)

        # read queue, expecting segment name i.e. '100-25000'
        if q.completed_jobs.qsize():
            msg = q.completed_jobs.get()
            if msg == 'exit':
                break
            else:
                segments.append(msg)

        if segments:
            # append the completed segments into temp file
            failed_segments = append_parts(segment_names=segments[:], src_folder=d.temp_folder, target_file=temp_file,
                                           target_folder=d.folder)
            if failed_segments != segments:
                done = [x for x in segments if x not in failed_segments]
                segments = failed_segments
                for seg_name in done:
                    os.remove(os.path.join(d.temp_folder, seg_name))

                    # update the set
                    completed_segments.add(seg_name)

                # write completed list on disk
                with open(cfg_file, 'wb') as f:
                    pickle.dump(completed_segments, f)

        # check if all parts already finished
        if completed_segments == all_segments:
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
