"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""

# worker class
import os
import time

import certifi
import pycurl

from .config import Status, APP_NAME
from .utils import get_seg_size


class Worker:
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
        self.use_range = True # if false will set pycurl option not to use ranges

    @property
    def actual_size(self):
        return self.start_size + self.downloaded + self.buff

    def reuse(self, seg='0-0', speed_limit=0, use_range=True):
        """Recycle same object again, better for performance as recommended by curl docs"""
        self.reset()

        # assign new values
        self.seg = seg  # segment name
        self.seg_range = seg  # byte range it must be formatted as 'start_byte-end_byte' example '100-600'
        self.target_size = get_seg_size(seg)
        self.f_name = os.path.join(self.temp_folder, seg)  # segment name with full path
        self.speed_limit = speed_limit
        self.use_range = use_range

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
        agent = f"{APP_NAME} Download Manager"
        self.c.setopt(pycurl.USERAGENT, agent)

        self.c.setopt(pycurl.URL, self.url)
        if self.use_range:
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