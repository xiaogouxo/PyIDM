Hanash is a python open source alternative to IDM (Internet Download Manager) 
with multi-connections, high speed engine, 
it downloads general files, also videos, and playlists from youtube. <br>
Developed in Python, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"


### Naming, What does Hanash means??
Hanash is an Arabic name for some kind of snakes / pythons called a
black racer, reference wiki pages: <br>
[حنش](https://ar.wikipedia.org/wiki/حنش) <br>
[Eastern_racer](https://en.wikipedia.org/wiki/Eastern_racer)

![Hanash_image](https://upload.wikimedia.org/wikipedia/commons/thumb/f/f4/Coluber_constrictorPCCP20030612-1115B.jpg/220px-Coluber_constrictorPCCP20030612-1115B.jpg)


**snapshots**

![main window](https://github.com/Aboghazala/Hanash/blob/master/images/main.PNG)
![downloads_tab](https://github.com/Aboghazala/Hanash/blob/master/images/downloads.PNG)
![setting_tab](https://github.com/Aboghazala/Hanash/blob/master/images/setting.PNG)
![d_window](https://github.com/Aboghazala/Hanash/blob/master/images/d_window.PNG)

example multi-downloading with speed limit of 10 KB/sec as a test

![concurrent windows](https://github.com/Aboghazala/Hanash/blob/master/images/concurrent_windows.PNG)


# Requirements:

- Python 3+
- ffmpeg : for merging audio with youtube DASH videos

python packages: 
- pycurl: is a Python interface to libcurl / curl as our download engine,
- PySimpleGUI: a beautiful gui builder, 
- youtube_dl: famous youtube downloader, limited use for meta information extraction only but videos are downloaded using pycurl 
- certifi: required by 'pycurl' for validating the trustworthiness of SSL certificates,
- mimetypes: converts between a filename or URL and the MIME type associated with the filename extension.,
- pyperclip: A cross-platform clipboard module for monitoring url copied to clipboard,
- plyer: for systray area notification,


you can run one line command to install required packages:
```python
python -m pip install pycurl certifi PySimpleGUI mimetypes pyperclip plyer youtube_dl
```

Or, simply run Hanash application and it will install missing packages automatically



### Alternative to IDM (Internet Download Manager):
The main reason for making this application is the lack of free open source download
managers which has multi-connection, high download speed, and resume capability, also can download youtube
videos, in same time has a good gui design, to achieve that, decision made to use the high speed
library 'pycurl', a threading module for multi-connection, youtube_dl, and an easy and beautiful PySimpleGUI 
module for designing the gui user interface


### How does Hanash work??
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


### note for Youtube-dl: <br>
youtube website changes frequently, if this application failed to retrieve video/playlist data
you should update youtube-dl module https://github.com/ytdl-org/youtube-dl
```
python -m pip install youtube_dl --upgrade
```
<br>

### note for pyperclip: <br>
Pyperclip is a cross-platform Python module for copy and paste clipboard functions. it is being used if you want to monitor clipboard for files urls and it will be processed automatically by Hanash DM.
On Linux, this module makes use of the xclip or xsel commands, which should come with the os. Otherwise run "sudo apt-get install xclip" on Debian like or "sudo pacman -S xclip" on archlinux

<br>

### Windows: <br>
a standalone compressed version available on: https://github.com/Aboghazala/Hanash/tree/master/windows <br>
note that these builds are old and might not working as expected regarding 
youtube videos, for most recent versions, you can run from the source with most recent youtube_dl module


<br><br>

# Versions change log:
3.2.0:
- Automatically install required python packages to run the application.
- better log text newer entries are now at the bottom.


3.1.0:
- added functionality to download youtube DASH videos with audio merged using ffmpg.
- bug fixes.
- remove Pillow module from requirements
- new themes added from PySimpleGUI module are available for use in user
  setting (total of 105 themes)

<br><br>

# Future Plans :
- use native video library for merging audio and video, will check libav, or possibility with youtube_dl.



<br><br>

# Feedback:
your feedback is most welcomed by filling an issue on https://github.com/Aboghazala/Hanash <br>
Cheers, <br>
Mahmoud Elshahat, <br>
2019


