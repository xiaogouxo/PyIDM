pyIDM is a python open source alternative to IDM (Internet Download Manager) 
with multi-connections, high speed engine, 
it downloads general files with good youtube support (such as downloading videos, whole playlists at once, or just an audio file for a video stream) . <br>
Developed in Python, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"



**snapshots**

![main window](https://github.com/pyIDM/pyIDM/blob/master/screenshots/main_reds.png)
![downloads_tab](https://github.com/pyIDM/pyIDM/blob/master/screenshots/downloads_reds_2.PNG)
![setting_tab](https://github.com/pyIDM/pyIDM/blob/master/screenshots/setting_reds.PNG)
![d_window](https://github.com/pyIDM/pyIDM/raw/master/screenshots/dwindow.png)

example multi-downloading with speed limit of 20 KB/sec as a test

![concurrent windows](https://github.com/pyIDM/pyIDM/blob/master/screenshots/multi-1.png)


# Requirements:
To run from source you will need to install python and some packages as follows:
- Python 3.6+: tested with python 3.6 on windows, and 3.7, 3.8 on linux
- [ffmpeg](https://www.ffmpeg.org/) : for merging audio with youtube DASH videos 

Required python packages: 
- [pycurl](http://pycurl.io/docs/latest/index.html): is a Python interface to libcurl / curl as our download engine,
- [PySimpleGUI](https://github.com/PySimpleGUI/PySimpleGUI): a beautiful gui builder, 
- [youtube_dl](https://github.com/ytdl-org/youtube-dl): famous youtube downloader, limited use for meta information extraction only but videos are downloaded using pycurl 
- certifi: required by 'pycurl' for validating the trustworthiness of SSL certificates,
- mimetypes: converts between a filename or URL and the MIME type associated with the filename extension.,
- pyperclip: A cross-platform clipboard module for monitoring url copied to clipboard,
- plyer: for systray area notification,

** please read notes below


pyIDM application will do its best to install missing packages automatically once you run it. or you can install required packages manually using:
```python
python -m pip install certifi PySimpleGUI mimetypes pyperclip plyer youtube_dl pycurl
```
on linux you should add `--user` argument for pip or use `sudo pip ...`

### Windows binaries: <br>
a standalone frozen version prepared by cx_freeze will be available soon on: https://github.com/pyIDM/pyIDM/releases <br>
note that these builds might be older than source code, for most recent versions, you can run from the source


### Alternative to IDM (Internet Download Manager):
The main reason for making this application is the lack of free open source download managers which has multi-connection, high download speed, and resume capability, also can download youtube videos, in same time has a good gui design, to achieve that, decision made to use the high speed library 'pycurl', a threading module for multi-connection, youtube_dl, and an easy and beautiful PySimpleGUI module for designing the gui user interface



### note for pycurl: <br>
for windows users:
last checked on 16-12-2019 pycurl [website](http://pycurl.io/docs/latest/index.html) support python Python 3.4 through 3.6, no mention 
for 3.7 or 3.8
normal pip install i.e `python -m pip install pycurl` will fail on windows because you need to build libcurl on your system first which is a headach. 
your best choice if pip fail is to download a wheel, zip file, or even a windows installer for pycurl from its official download [link](https://dl.bintray.com/pycurl/pycurl/), find the file that match your windows system and python version installed on your system.

for linux users:
there is no issues, since most linux distros have curl preinstalled, so pycurl will link with libcurl library to get built with no issues, checked with python versions 3.6, 3.7, and 3.8 working with no problems.
<br>


### note for [Youtube-dl](https://github.com/ytdl-org/youtube-dl): <br>
youtube website changes frequently, if this application failed to retrieve video/playlist data
you should update youtube-dl module thru pyIDM setting tab or manually by
```
python -m pip install youtube_dl --upgrade
```
<br>

### note for pyperclip: <br>
Pyperclip is a cross-platform Python module for copy and paste clipboard functions. it is being used if you want to monitor clipboard for files urls and it will be processed automatically by the application.
On Linux, this module makes use of the xclip or xsel commands, which should come with the os. Otherwise run "sudo apt-get install xclip" on Debian like or "sudo pacman -S xclip" on archlinux

<br>

### How does pyIDM work??
- once you copy any url in clipboard the application start processing this url automatically "you can disable this in user setting"
- pycurl get url headers and follow redirections to get the effective download url.
- headers get processed and data get extracted and create a download_item object 
containing attributes like name, size, url, etc... for the target file
- update gui accordingly.
- if user click start download button, the download_item object added to download queue.
- depending on user setting objects in download queue get prcessed concurrently
- each download object will be passed to a brain function
- brain function will prepare a segment list or parts list " file will be downloaded in chunks concurrently" for 
example a 100MB file will be splitted into 100 parts with part size of 1MB each, each part will be downloaded 
separately in a dedicated thread, Number of threads, and part size can be changed in user setting.
- brain will start a thread manager to make a worker thread for each file segment / part.
- brain will start file manager to collect segments and write it to a temp file, in same time write completed 
segments names in a file for resume later function.
- Thread manager will report operation completed to brain once finished downloading all file segments
- brain will order both thread manager and file manager to quit and report completed download to main window, then quit
- and so on for all downloads
- example if you have a 3 concurrent downloads with 10 concurrent connections for each download you will have 30 running threads 
concurrently.
- communications between threads based heavily on queues which shows best fit for this job.
- some websites doesn't support range requests, so downloads will not be resumable nor multi-connection will be available.
- 
- for youtube video url, a youtube_dl module starts in a separate threads to get playlist videos and available streams for each video
- video streams are three types (normal videos, video only, audio only) if user decided to download a video only stream, the application
will choose an audio stream with the same format, then download both streams as explained above (by brain function) then once completed
the audio will be merged into video file using FFMPEG external application "subprocess".  


<br><br>

# Versions change log:
3.3:
- Change application name to pyIDM instead of old name Hanash.

3.2:
- Automatically install required python packages to run the application.
- better log text newer entries are now at the bottom.
- correct app. icon not appearing in windows


3.1:
- added functionality to download youtube DASH videos with audio merged using ffmpg.
- bug fixes.
- remove Pillow module from requirements
- new themes added from PySimpleGUI module are available for use in user
  setting (total of 105 themes)

<br><br>

# Future Plans :
- use native video library for merging audio and video, will check libav, or possibility with youtube_dl.
- Design different user interface.



<br><br>

# Feedback:
your feedback is most welcomed by filling an issue on https://github.com/pyIDM/pyIDM <br>
or email me: mahmoud_elshahhat@yahoo.com
Cheers, <br>
Mahmoud Elshahat, <br>
2019