pyIDM is a python open source (Internet Download Manager) 
with multi-connections, high speed engine, 
it downloads general files with good youtube support (such as downloading videos, whole playlists at once, or just an audio file for a video stream) . <br>
Developed in Python, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

![main window](https://user-images.githubusercontent.com/58998813/71563996-a2580480-2aa1-11ea-8818-6476b500d200.png)

---

# Why another download manager?:
With all free and paid download manager why someone may need another one?
I believe in one term, **"if the product is free, then you are the product"**, most (if not all) free applications collect data about you, some of them are toxic and plant trojans and spyware in your system, then I decided to make my own download manager based on python with 👉 **"--GUI--"** relies only on open source tools and libraries, nothing hidden, with source code exposed to thousands of programmers, no one can play dirty games here 😉.

originally I made this application for my personal use then decided to release its open source for others to use, hoping it might help someone.

# What makes pyIDM different? 
Like most download managers it can download, pause, resume any file, additionally, pyIDM has some strength points in some fields like:

- **Re-using existing connection**, pyIDM will reuse already establiched connections to the download server which saves the time of establishing new connections. 
- **Segment size:** you can decide the size of the individual file segments "chunk size".
- **Resume:** files downloaded in **segments** saved at user download directory in a temp folder, in case download interrupts or fatal os system failure, if you try to download the same file again with same name and at the same destination folder, pyIDM will scan all completed segments and resume where it left.
- **Youtube support**: you can download videos with any quality, also can download the whole playlist at once. the different here over famous applications that you don't need a browser extension to get the available youtube streams, you just copy youtube video link and all metadata will be fetched internally with all available video streams and  audio streams as well for this video will be available to be downloaded from the application.
- **Refresh expired urls**, keeping a file's webpage url saved and fetch the effective download link to download the file, in case a download url gets expired "most servers issue a temporary download links", you can press refresh button on downloads Tab and it will fetch a new download link for you then you can press download button to resume downloading the file.
- **Speed:** relying on famous "LibCurl" library as a powerfull download engine, in comparision tests it overcomes famous download managers in speed.
- **GUI:** a beautiful and yet simple user interface, with very simple options to get what you want without effort, with around 140 themes to choose among them, and this is something missing from other opensource python download managers.
- **Updates:** relying on highly active python packages and libraries will guarantee a decent update cycle to this application.
- **Speed Limit:** it does a good job limiting download speeds as per user requirements.
- **Multiconnection:** you can decide how many connections (workers) you want per file download, the default is 10 connections. some servers limit download per connection, in this case increasing connections number will make a huge difference in download speeds.
- **Concurrent downloads:** you can decide how many simultaneous downloads from setting Tab. 
- **Clipboard Monitor**: it watches any copied url and directly process and fetch metadata (you can disable this behaviour in setting if you wish)






---

**more snapshots**

![downloads_tab](https://user-images.githubusercontent.com/37757246/71418538-a0daa680-2673-11ea-82a8-e10e0ca673bd.PNG)
![playlist_window](https://user-images.githubusercontent.com/58998813/71775076-22d7a300-2f83-11ea-8011-b45f2f2605f4.png)
![setting_tab](https://user-images.githubusercontent.com/37757246/71418549-a2a46a00-2673-11ea-848a-ca5ca82e743b.PNG)
![d_window](https://user-images.githubusercontent.com/37757246/71418539-a0daa680-2673-11ea-8073-0c217fff7e9a.png)
![black](https://user-images.githubusercontent.com/37757246/71418541-a1733d00-2673-11ea-85c3-cd6f6b2d66c1.PNG)

example multi-downloading with speed limit of 20 KB/sec as a test

![concurrent windows](https://user-images.githubusercontent.com/37757246/71418548-a2a46a00-2673-11ea-8101-c95d29b6a0e4.png)

[view all screenshots with different themes](https://github.com/pyIDM/pyIDM/issues/13)

---

# How to run pyIDM?
You have 2 options to run pyIDM on your operating system:
1. **Binary executables**:
currently binary build "Standalone zip" is available only for windows [here](https://github.com/pyIDM/pyIDM/releases/latest).

2. **run from the source**:
pyIDM is a python app. so, it can run on any platform that can run python, 
To run from source, you have to have a python installed, "supported python versions is 3.6, 3.7, and 3.8", then download or clone this repository, and run pyIDM.py (it will install the other required python packages automatically if missing)
additionally you have to install 'ffmpeg' for merging audio with youtube DASH videos
if pyIDM failed to install required packages, you should install it manually, refer to "Dependencies" section below.

---

# Dependencies:
below are the requirements to run from source:
- Python 3.6+: tested with python 3.6 on windows, and 3.7, 3.8 on linux
- [ffmpeg](https://www.ffmpeg.org/) : for merging audio with youtube DASH videos 

Required python packages: 
- [pycurl](http://pycurl.io/docs/latest/index.html): is a Python interface to libcurl / curl as our download engine,
- [PySimpleGUI](https://github.com/PySimpleGUI/PySimpleGUI): a beautiful gui builder, 
- [youtube_dl](https://github.com/ytdl-org/youtube-dl): famous youtube downloader, limited use for meta information extraction only but videos are downloaded using pycurl 
- certifi: required by 'pycurl' for validating the trustworthiness of SSL certificates,
- mimetypes: converts between a filename or URL and the MIME type associated with the filename extension.,
- pyperclip: A cross-platform clipboard module for monitoring url copied to clipboard, requires "xclip or xsel to be available on linux"
- plyer: for systray area notification.

** please read notes below


pyIDM application will do its best to install missing packages automatically once you run it. or you can install required packages manually using:
```
python -m pip install --user --upgrade certifi PySimpleGUI mimetypes pyperclip plyer youtube_dl pycurl
```

### note for pycurl: <br>
for windows users:
normal pip install i.e `python -m pip install pycurl` will fail on windows because you need to build libcurl on your system first which is a headache. 
your best choice if pip fail is to download a wheel, zip file, or even a windows installer for pycurl from its official download [link](https://dl.bintray.com/pycurl/pycurl/), find the file that match your windows system and python version installed on your system, last checked on 16-12-2019 available files for Python 3.4 through 3.6, still no wheels or installers for 3.7 or 3.8.

for linux users:
there is no issues, since most linux distros have curl preinstalled, so pycurl will link with libcurl library to get built with no issues, checked with python versions 3.6, 3.7, and 3.8 working with no problems.
<br>


### note for [Youtube-dl](https://github.com/ytdl-org/youtube-dl): <br>
youtube website changes frequently, if this application failed to retrieve video/playlist data
you should update youtube-dl module thru pyIDM setting tab or manually by
```
python -m pip install youtube_dl --upgrade
```

### note for pyperclip: <br>
Pyperclip is a cross-platform Python module for copy and paste clipboard functions. it is being used if you want to monitor clipboard for files urls and it will be processed automatically by the application.
On Linux, this module makes use of the xclip or xsel commands, which should come with the os. Otherwise run "sudo apt-get install xclip" on Debian like or "sudo pacman -S xclip" on archlinux

---

### Windows binaries: <br>
a standalone frozen version prepared by py2exe or cx_freeze is available on: [latest version](https://github.com/pyIDM/pyIDM/releases/latest) <br>
for all available build versions you can check https://github.com/pyIDM/pyIDM/releases

---

### Alternative to IDM (Internet Download Manager):
The main reason for making this application is the lack of free open source download managers which has multi-connection, high download speed, and resume capability, also can download youtube videos, in same time has a good gui design, to achieve that, decision made to use the high speed library 'pycurl', a threading module for multi-connection, youtube_dl, and an easy and beautiful PySimpleGUI module for designing the gui user interface

---

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

---

<br><br>

# Versions change log:
change log / what's new now moved to releases page under each release




<br><br>

---



# Feedback:
your feedback is most welcomed by filling a [new issue](https://github.com/pyIDM/pyIDM/issues/new) <br>
or email me at: mahmoud_elshahhat@yahoo.com <br>

Author, <br>
Mahmoud Elshahat, <br>
2019-2020

---