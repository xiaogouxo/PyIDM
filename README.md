[![Downloads](https://pepy.tech/badge/pyidm)](https://pepy.tech/project/pyidm)

pyIDM is a python open source (Internet Download Manager) 
with multi-connections, high speed engine, 
it downloads general files and videos from youtube and tons of other streaming websites . <br>
Developed in Python, based on "pyCuRL/libcurl", "youtube_dl", and "PySimpleGUI"

![main window](https://user-images.githubusercontent.com/58998813/74883072-da304980-5378-11ea-81c5-a4a7a22fbb5f.gif)

---
**Features**:
* High download speeds "based on libcurl"   -  [See Speed test of: aria2 vs pyIDM](https://user-images.githubusercontent.com/58998813/74993622-361bd080-5454-11ea-8bda-173bfcf16349.gif).
* Multi-connection downloading "Multithreading"
* Scan and resume uncompleted downloads.
* Support for Youtube, and a lot of stream websites "using youtube-dl to fetch data".
* support for fragmented video streams.
* support for hls/m3u8 video streams.
* watch videos while downloading*   "some videos will have no audio until finish downloading"
* Auto check for application updates.
* Scheduling downloads
* Re-using existing connection to remote server.
* Clipboard Monitor.
* Refresh expired urls.
* Simple GUI interface with 140 themes available.
* http proxy support.
* user can control a lot of options:
    - select theme.
    - set proxy.
    - selecting Segment size.
    - Speed limit.
    - Max. Concurrent downloads.
    - Max. connections per download.


---
# How to install pyIDM?
You have 3 options to run pyIDM on your operating system:

1. **Windows portable version**:<br>
Latest Windows portable version available [here](https://github.com/pyIDM/pyIDM/releases/latest). <br>
unzip, and run from pyidm.exe, no installation required.

2. **pip**:<br>
    `pip install pyIDM`
    
    then you can run application from Terminal by:<br>
    `python -m pyidm`          note pyidm name in small letters 

    or just<br>
    `pyidm`        an exexutable "i.e. pyidm.exe on windows" will be located at "python/scripts", if it doesn't work append "python/scripts" folder to PATH. 


3. **run from github source code**:<br>
pyIDM is a python app. so, it can run on any platform that can run python, 
To run from source, you have to have a python installed, "supported python versions is 3.6, 3.7, and 3.8", then download or clone this repository, and run pyIDM.py (it will install the other required python packages automatically if missing)
if pyIDM failed to install required packages, you should install it manually, refer to "Dependencies" section below.

---

# Dependencies:
below are the requirements to run from source:
- Python 3.6+: tested with python 3.6 on windows, and 3.7, 3.8 on linux
- [ffmpeg](https://www.ffmpeg.org/) : for merging audio with youtube DASH videos "it will be installed automatically on windows"

Required python packages: 
- [pycurl](http://pycurl.io/docs/latest/index.html): is a Python interface to libcurl / curl as our download engine,
- [PySimpleGUI](https://github.com/PySimpleGUI/PySimpleGUI): a beautiful gui builder, 
- [youtube_dl](https://github.com/ytdl-org/youtube-dl): famous youtube downloader, limited use for meta information extraction only but videos are downloaded using pycurl 
- certifi: required by 'pycurl' for validating the trustworthiness of SSL certificates,
- pyperclip: A cross-platform clipboard module for monitoring url copied to clipboard, requires "xclip or xsel to be available on linux"
- plyer: for systray area notification.


** please read notes below


pyIDM application will do its best to install missing packages automatically once you run it. or you can install required packages manually using:

```
pip install -r requirements.txt
```
or
```
python -m pip install --user --upgrade certifi PySimpleGUI pyperclip plyer youtube_dl pycurl
```



---

**more snapshots**

![downloads_tab](https://user-images.githubusercontent.com/37757246/71418538-a0daa680-2673-11ea-82a8-e10e0ca673bd.PNG)
![playlist_window](https://user-images.githubusercontent.com/58998813/71775076-22d7a300-2f83-11ea-8011-b45f2f2605f4.png)
![setting_tab](https://user-images.githubusercontent.com/58998813/74783222-e4d1dc80-52ad-11ea-80b9-26741fe97a17.png)
![d_window](https://user-images.githubusercontent.com/37757246/71418539-a0daa680-2673-11ea-8073-0c217fff7e9a.png)


[view all screenshots with different themes](https://github.com/pyIDM/pyIDM/issues/13)


---
# Why another download manager?:
With all free and paid download manager why someone may need another one?
I believe in one term, **"if the product is free, then you are the product"**, most (if not all) free applications collect data about you, some of them are toxic and plant trojans and spyware in your system, then I decided to make my own download manager based on python with 👉 **"--GUI--"** relies only on open source tools and libraries, nothing hidden, with source code exposed to thousands of programmers, no one can play dirty games here 😉.

why not just use youtube-dl from command line or just use youtube-dl gui? answer is multithreading / multiconnection is not available in youtube-dl, most of the time streaming servers like youtube limit speed per connection and you end up with slow download speeds.

---

### note for pycurl: <br>
for windows users:
normal pip install i.e `python -m pip install pycurl` might fail on windows because you need to build libcurl on your system first which is a headache. 
your best choice if pip fail is to download exe file for pycurl from its official download [link](https://dl.bintray.com/pycurl/pycurl/), find the file that match your windows system and python version installed on your system, last checked on 28-01-2020, found available files for almost all Python versions upto version 3.7

example: if you have python 3.6 installed on windows 32bit, you should download "pycurl-7.43.0.2.win32-py3.6.exe" file and install it, 
another example: if you have python 3.7 running on windows 64 bit, you should choose and download "pycurl-7.43.0.3.win-amd64-py3.7.exe" file

other download options include a wheel, zip file, or even a windows installer

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

<br><br>

# Versions change log:
ChangeLog.txt is included in source code.




<br><br>

---
# How to contribute to this project:
1- by testing the application and opening [new issue](https://github.com/pyIDM/pyIDM/issues/new) for bug reporting, feature request, or suggestions. <br>
2- fork this repo and pull request

<br><br>

---


# Feedback:
your feedback is most welcomed by filling a [new issue](https://github.com/pyIDM/pyIDM/issues/new) <br>
or email me at: mahmoud_elshahhat@yahoo.com <br>

Author, <br>
Mahmoud Elshahat, <br>
2019-2020

---