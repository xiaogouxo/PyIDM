"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""
import os
import time
from threading import Thread
from .video import (merge_video_audio, youtube_dl_downloader, unzip_ffmpeg,
                    hls_downloader, process_hls)  # unzip_ffmpeg required here for ffmpeg callback
from . import config
from .config import Status, active_downloads, APP_NAME
from .utils import (log, size_format, popup, notify, delete_folder, delete_file, rename_file, load_json, save_json)
from .worker import Worker
from .downloaditem import Segment


def brain(d=None):
    """main brain for a single download, it controls thread manger, file manager, and get data from workers
    and communicate with download window Gui, Main frame gui"""

    q = d.q

    # in case of re-downloading a completed file will reset segment flags
    if d.status == Status.completed:
        d.reset_segments()
        d.downloaded = 0

    # set status
    if d.status == Status.downloading:
        log('another brain thread may be running')
        return
    else:
        d.status = Status.downloading

    # add item index to active download set
    active_downloads.add(d.id)

    q.log(f'start downloading file: {d.name}, size: {size_format(d.size)}')

    # todo: more testing required, move part of this code to gui.start_download() asking user to proceed
    # # use youtube-dl native downloader to download unsupported protocols
    # # problem now is when youtube-dl use ffmpeg to download streams we get no progress at all
    # if d.protocol in config.non_supported_protocols:
    #     log('unsupported protocol detected use native youtube-dl downloader')
    #     # popup('using native youtube-dl downloader, please check progress on log tab')
    #     try:
    #         done = hls_downloader(d)  # youtube_dl_downloader(d)
    #         if done:
    #             d.status = Status.completed
    #         else:
    #             d.status = Status.error
    #     except:
    #         if d.status != Status.cancelled:  # if not cancelled by user
    #             d.status = Status.error
    #     return

    # experimental m3u8 protocols
    if 'm3u8' in d.protocol:
        video_url_list = process_hls(d.eff_url)

        if not video_url_list:
            d.status = Status.error
            return

        # build segments
        d.segments = [Segment(name=os.path.join(d.temp_folder, str(i)), num=i, range=None, size=0,
                              url=seg_url, targetfile=d.target_file, tempfile=d.temp_file)
                      for i, seg_url in enumerate(video_url_list)]

        if d.type == 'dash':
            audio_url_list = process_hls(d.audio_url)

            # build segments
            audio_segments = [Segment(name=os.path.join(d.temp_folder, str(i) + '_audio'), num=i, range=None, size=0,
                                      url=seg_url, targetfile=d.audio_file, tempfile=d.audio_file)
                              for i, seg_url in enumerate(audio_url_list)]
            d.segments += audio_segments

    # run file manager in a separate thread
    Thread(target=file_manager, daemon=True, args=(d,)).start()

    # run thread manager in a separate thread
    Thread(target=thread_manager, daemon=True, args=(d,)).start()

    while True:
        time.sleep(0.1)  # a sleep time to make the program responsive

        if d.status == Status.completed:
            # os notification popup
            notification = f"File: {d.name} \nsaved at: {d.folder}"
            notify(notification, title=f'{APP_NAME} - Download completed')
            break
        elif d.status == Status.cancelled:
            log(f'brain {d.num}: Cancelled download')
            break
        elif d.status == Status.error:
            log(f'brain {d.num}: download error')
            break

    # todo: check if reset queues is required here since it is done from DownloadItem.reset()
    # reset queue and delete un-necessary data
    d.q.reset()

    # remove item id from active downloads
    try:
        # print(d.id, active_downloads)
        active_downloads.remove(d.id)
        log(f'brain {d.num}: removed item from active downloads')
    except:
        pass

    # todo: should find a better way to handle callback.
    # callback, a method or func "name" to call if download completed, it is stored as a string to be able to save it
    # on disk with other downloaditem parameters
    if d.callback and d.status == Status.completed:
        # d.callback()
        globals()[d.callback]()

    # report quitting
    log(f'brain {d.num}: quitting')


def thread_manager(d):
    q = d.q

    # create worker/connection list
    workers = [Worker(tag=i, d=d) for i in range(config.max_connections)]

    free_workers = [i for i in range(config.max_connections)]
    free_workers.reverse()
    busy_workers = []
    live_threads = []  # hold reference to live threads

    # load downloaded list from disk if exists
    file = os.path.join(d.temp_folder, 'downloaded.txt')
    downloaded = []
    if os.path.isfile(file):
        downloaded = load_json(file)

    if downloaded:
        for seg in d.segments:
            if seg.name in downloaded:
                seg.downloaded = True

    # job_list
    job_list = [seg for seg in d.segments if not seg.downloaded]

    # reverse job_list to process segments in proper order use pop()
    job_list.reverse()

    while True:
        time.sleep(0.1)  # a sleep time to while loop to make the app responsive

        # getting jobs which might be returned from workers as failed
        for _ in range(q.jobs.qsize()):
            job_list.append(q.jobs.get())

        # todo: test speed limit
        # speed limit
        if busy_workers:
            worker_sl = config.speed_limit * 1024 // len(busy_workers)
        else:
            worker_sl = 0

        # reuse a free worker to handle a job from job_list
        if len(busy_workers) < config.max_connections and free_workers and job_list and d.status == Status.downloading:
            worker_num, seg = free_workers.pop(), job_list.pop()  # get available tag # get a new job
            busy_workers.append(worker_num)  # add number to busy workers

            # create new threads
            worker = workers[worker_num]
            worker.reuse(seg=seg, speed_limit=worker_sl)
            t = Thread(target=worker.run, daemon=True, name=str(worker_num))
            live_threads.append(t)
            t.start()

        # Monitor active threads and add the offline to a free_workers
        for t in live_threads:
            if not t.is_alive():
                worker_num = int(t.name)
                live_threads.remove(t)
                busy_workers.remove(worker_num)
                free_workers.append(worker_num)

        # update d param
        d.live_connections = len(live_threads)
        d.remaining_parts = len(live_threads) + len(job_list) + q.jobs.qsize()

        # change status
        if d.status != Status.downloading:
            # stop_all_workers()
            print('--------------thread manager cancelled-----------------')
            break

        # done downloading
        if not busy_workers and not job_list and not q.jobs.qsize():
            print('--------------thread manager done----------------------')
            break

    # update downloaded list
    downloaded = [seg.name for seg in d.segments if seg.downloaded]

    # save downloaded list to disk
    if os.path.isdir(d.temp_folder):
        save_json(file=os.path.join(d.temp_folder, 'downloaded.txt'), data=downloaded)

    log(f'thread_manager {d.num}: quitting')


def file_manager(d):
    completed = []  # contains names of all completed segments

    # job_list
    job_list = d.segments

    # load completed segments
    comp_file = os.path.join(d.temp_folder, 'completed.txt')
    if os.path.isfile(comp_file):
        completed = load_json(file=comp_file)

    if completed:
        for seg in job_list:
            if seg.name in completed:
                seg.completed = True

    while True:
        time.sleep(1)

        job_list = [seg for seg in d.segments if not seg.completed]
        # print(job_list)

        for seg in job_list:
            # process segments in order
            # print(seg.name, seg.downloaded, seg.completed)

            if seg.completed:  # skip completed segment
                continue

            if not seg.downloaded:  # if the first non completed segments is not downloaded will exit for loop
                break

            # append downloaded segment to temp file, mark as completed, then delete it.
            try:
                with open(seg.tempfile, 'ab') as trgt_file:
                    with open(seg.name, 'rb') as src_file:
                        trgt_file.write(src_file.read())

                seg.completed = True
                completed.append(seg.name)
                delete_file(seg.name)

                # save completed list on disk
                save_json(file=os.path.join(d.temp_folder, 'completed.txt'), data=completed)

                # print('merged: ', seg.name)
            except Exception as e:
                log('failed to merge segment', seg.name, ' - ', e)

        # check if all segments already merged
        if all([seg.completed for seg in job_list]):
            # handle dash video
            if d.type == 'dash':
                # merge audio and video
                output_file = d.target_file.replace(' ', '_')  # remove spaces from target file

                # set status to merge
                d.status = Status.merging_audio
                error, output = merge_video_audio(d.temp_file, d.audio_file, output_file)

                if not error:
                    log('done merging video and audio for: ', d.target_file)

                    rename_file(output_file, d.target_file)

                    # delete temp files
                    delete_file(d.temp_file)
                    delete_file(d.audio_file)
                    delete_folder(d.temp_folder)
                    delete_folder(d.temp_audio_folder)

                else:  # error merging
                    msg = f'failed to merge audio for file: {d.target_file}'
                    popup(msg, title='merge error')
                    d.status = Status.error
                    break

            else:
                rename_file(d.temp_file, d.target_file)
                delete_folder(d.temp_folder)

            # at this point all done successfully
            d.status = Status.completed
            print('---------file manager done merging segments---------')
            break

        # change status
        if d.status != Status.downloading:
            print('--------------file manager cancelled-----------------')
            break

    # Report quitting
    log(f'file_manager {d.num}: quitting')
