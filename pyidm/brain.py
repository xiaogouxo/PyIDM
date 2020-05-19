"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""
import io
import os
import time
from threading import Thread
from .video import merge_video_audio, unzip_ffmpeg, pre_process_hls, post_process_hls, \
    convert_audio, download_subtitles  # unzip_ffmpeg required here for ffmpeg callback
from . import config
from .config import Status, active_downloads, APP_NAME
from .utils import (log, size_format, popup, notify, delete_folder, delete_file, rename_file, load_json, save_json)
from .worker import Worker
from .downloaditem import Segment


def brain(d=None, downloader=None):
    """main brain for a single download, it controls thread manger, file manager, and get data from workers
    and communicate with download window Gui, Main frame gui"""

    # set status
    if d.status == Status.downloading:
        log('another brain thread may be running')
        return
    else:
        d.status = Status.downloading

    # reset segments
    d.segments = []

    log('\n')
    log('=' * 106)
    log(f'start downloading file: "{d.name}", size: {size_format(d.total_size)}, to: {d.folder}')

    # hls / m3u8 protocols
    if 'hls' in d.subtype_list:
        keep_segments = True  # don't delete segments after completed, it will be post-processed by ffmpeg
        try:
            success = pre_process_hls(d)
            if not success:
                d.status = Status.error
                return
        except Exception as e:
            d.status = Status.error
            log('pre_process_hls()> error: ', e, showpopup=True)
            return
    else:
        # for non hls videos and normal files
        keep_segments = True  # False

    # prepare download item for download
    d.prepare_for_downloading()

    # run file manager in a separate thread
    Thread(target=file_manager, daemon=True, args=(d, keep_segments)).start()

    # run thread manager in a separate thread
    Thread(target=thread_manager, daemon=True, args=(d,)).start()

    while True:
        time.sleep(0.1)  # a sleep time to make the program responsive

        if d.status == Status.completed:
            # os notification popup
            notification = f"File: {d.name} \nsaved at: {d.folder}"
            notify(notification, title=f'{APP_NAME} - Download completed')
            log(f'File: "{d.name}", completed.')
            break
        elif d.status == Status.cancelled:
            log(f'brain {d.num}: Cancelled download')
            break
        elif d.status == Status.error:
            log(f'brain {d.num}: download error')
            break

    # todo: should find a better way to handle callback.
    # callback, a method or func "name" to call if download completed, it is stored as a string to be able to save it
    # on disk with other downloaditem parameters
    if d.callback and d.status == Status.completed:
        # d.callback()
        globals()[d.callback]()

    # report quitting
    log(f'brain {d.num}: quitting')
    log('=' * 106, '\n')


def thread_manager(d):

    #   soft start, connections will be gradually increase over time to reach max. number
    #   set by user, this prevent impact on servers/network, and avoid "service not available" response
    #   from server when exceeding multi-connection number set by server.
    #
    #   this technique will affect starting speed and may affect PyIDM speed testing against other download managers,
    #   but playing fair is more important than winning the game.
    limited_connections = 1  # used to limit connections in case of server errors

    # create worker/connection list
    workers = [Worker(tag=i, d=d) for i in range(config.max_connections)]

    free_workers = [i for i in range(config.max_connections)]
    free_workers.reverse()
    busy_workers = []
    live_threads = []  # hold reference to live threads

    # job_list
    job_list = [seg for seg in d.segments if not seg.downloaded]
    # print('thread manager job list:', job_list)

    # reverse job_list to process segments in proper order use pop()
    job_list.reverse()

    d.remaining_parts = len(job_list)

    # error track, if receive many errors with no downloaded data, abort
    downloaded = 0
    total_errors = 0
    max_errors = 100
    errors_descriptions = set()  # store unique errors
    error_timer = 0
    errors_check_interval = 1  # in seconds

    # speed limit
    sl_timer = time.time()

    def clear_error_q():
        # clear error queue
        for _ in range(config.error_q.qsize()):
            errors_descriptions.add(config.error_q.get())

    while True:
        time.sleep(0.1)  # a sleep time to while loop to make the app responsive

        # getting jobs which might be returned from workers as failed
        for _ in range(config.jobs_q.qsize()):
            job = config.jobs_q.get()
            job_list.append(job)

        # allowable connections
        allowable_connections = min(config.max_connections, d.remaining_parts, limited_connections)

        # dynamic connection manager ---------------------------------------------------------------------------------
        # check every n seconds for connection errors
        if time.time() - error_timer >= errors_check_interval:
            error_timer = time.time()
            errors_num = config.error_q.qsize()

            if errors_num >= 10:
                limited_connections = limited_connections - 1 if limited_connections > 1 else 1
                log('Thread Manager: receiving server errors, connections limited to:', limited_connections)

                clear_error_q()
            else:
                if limited_connections < config.max_connections and limited_connections < d.remaining_parts:
                    limited_connections = limited_connections + 1
                    log('Thread Manager: allowable connections:', allowable_connections)

            total_errors += errors_num
            d.errors = total_errors  # update errors property of download item

            if total_errors:
                log('--------------------------------- errors ---------------------------------:', total_errors)
                log('Errors descriptions:', errors_descriptions, log_level=3)

            # reset total errors if received any data
            if downloaded != d.downloaded:
                downloaded = d.downloaded
                # print('reset errors to zero')
                total_errors = 0
                clear_error_q()

            if total_errors >= max_errors:
                d.status = Status.error
                log('Thread manager: too many connection errors', 'maybe network problem or expired link',
                    start='', sep='\n', showpopup=True)

        # speed limit ------------------------------------------------------------------------------------------------
        # wait some time for dynamic connection manager to release all connections
        if time.time() - sl_timer < config.max_connections * errors_check_interval:
            worker_sl = (config.speed_limit // config.max_connections) if config.max_connections else 0
        else:
            # normal calculations
            worker_sl = (config.speed_limit // allowable_connections) if allowable_connections else 0

        # reuse a free worker to handle a job from job_list -----------------------------------------------------------
        if free_workers and job_list and d.status == Status.downloading and len(live_threads) < allowable_connections:
            # log('live_threads=', len(live_threads))
            for _ in range(allowable_connections - len(live_threads)):
                try:
                    # sometimes download chokes when remaining only one worker, will set higher minimum speed and
                    # less timeout for last workers batch
                    if len(job_list) + config.jobs_q.qsize() <= allowable_connections:
                        minimum_speed, timeout = 20 * 1024, 10  # worker will abort if speed less than 20 KB for 10 seconds
                    else:
                        minimum_speed = timeout = None   # default as in utils.set_curl_option

                    # get available tag and  get a new job
                    worker_num, seg = free_workers.pop(), job_list.pop()
                    busy_workers.append(worker_num)  # add number to busy workers

                    # create new threads
                    worker = workers[worker_num]
                    worker.reuse(seg=seg, speed_limit=worker_sl, minimum_speed=minimum_speed, timeout=timeout)
                    t = Thread(target=worker.run, daemon=True, name=str(worker_num))
                    live_threads.append(t)
                    t.start()

                    time.sleep(0.1)  # slow down between requests
                except:
                    break

        # update d param
        d.live_connections = len(live_threads)
        d.remaining_parts = len(live_threads) + len(job_list) + config.jobs_q.qsize()

        # Required check if things goes wrong
        if len(live_threads) + len(job_list) + config.jobs_q.qsize() == 0:
            # rebuild job_list
            job_list = [seg for seg in d.segments if not seg.downloaded]
            if not job_list:
                break

        # Monitor active threads and add the offline to a free_workers
        for t in live_threads:
            if not t.is_alive():
                worker_num = int(t.name)
                busy_workers.remove(worker_num)
                free_workers.append(worker_num)

        # update live threads
        live_threads = [thread for thread in live_threads if thread.is_alive()]

        # monitor status change
        if d.status != Status.downloading:
            # print('--------------thread manager cancelled-----------------')
            break

    # update d param
    d.live_connections = 0
    d.remaining_parts = len(live_threads) + len(job_list) + config.jobs_q.qsize()
    log(f'thread_manager {d.num}: quitting')


def file_manager(d, keep_segments=False):

    while True:
        time.sleep(0.1)

        job_list = [seg for seg in d.segments if not seg.completed]
        # print(job_list)

        for seg in job_list:
            # process segments in order

            if seg.completed:  # skip completed segment
                continue

            if not seg.downloaded:  # if the first non completed segments is not downloaded will exit for loop
                break

            # append downloaded segment to temp file, mark as completed, then delete it.
            try:
                if seg.merge:
                    with open(seg.tempfile, 'ab') as trgt_file:
                        with open(seg.name, 'rb') as src_file:
                            trgt_file.write(src_file.read())

                seg.completed = True
                log('completed segment: ',  seg.basename)

                if not keep_segments and not config.keep_temp:
                    delete_file(seg.name)

            except Exception as e:
                log('failed to merge segment', seg.name, ' - ', e)

        # all segments already merged
        if not job_list:

            # handle audio streams
            if d.type == 'audio':
                d.status = Status.processing
                success = convert_audio(d)
                if not success:
                    d.status = Status.error
                    log('file_manager()>  convert_audio() failed, file:', d.target_file, showpopup=True)
                    break
                else:
                    d.delete_tempfiles()

            # handle HLS streams
            if 'hls' in d.subtype_list:
                log('handling hls videos')
                # Set status to processing
                d.status = Status.processing

                success = post_process_hls(d)
                if not success:
                    d.status = Status.error
                    log('file_manager()>  post_process_hls() failed, file: \n', d.name, showpopup=True)
                    break

            # handle dash video
            if 'dash' in d.subtype_list:
                log('handling dash videos')
                # merge audio and video
                output_file = d.target_file.replace(' ', '_')  # remove spaces from target file

                # set status to processing
                d.status = Status.processing
                error, output = merge_video_audio(d.temp_file, d.audio_file, output_file, d)

                if not error:
                    log('done merging video and audio for: ', d.target_file)

                    rename_file(output_file, d.target_file)

                    # delete temp files
                    d.delete_tempfiles()

                else:  # error merging
                    d.status = Status.error
                    log('failed to merge audio for file: \n', d.name, showpopup=True)
                    break

            else:
                rename_file(d.temp_file, d.target_file)
                # delete temp files
                d.delete_tempfiles()

            # download subtitles
            download_subtitles(d.selected_subtitles, d)

            # at this point all done successfully
            d.status = Status.completed
            # print('---------file manager done merging segments---------')
            break

        # change status
        if d.status != Status.downloading:
            # print('--------------file manager cancelled-----------------')
            break

    # save progress info for future resuming
    if os.path.isdir(d.temp_folder):
        d.save_progress_info()

    # Report quitting
    log(f'file_manager {d.num}: quitting')
