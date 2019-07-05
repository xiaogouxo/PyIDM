Hanash is a general purpose multi-connections download manager based on python, 
it downloads any file type, plus videos, and playlists from youtube.
![main window](https://github.com/Aboghazala/Hanash/blob/master/images/main.PNG)

please note "Hanash DM" uses PycURL, a Python interface to libcurl which will try to use your max internet speed, you can use "limit speed" option in setting window 

Developed in Python, based on "pyCuRL/curl", "youtube_dl", and designed by "PySimpleGUI"

**snapshots**

![downloads_tab](https://github.com/Aboghazala/Hanash/blob/master/images/downloads.PNG)
![setting_tab](https://github.com/Aboghazala/Hanash/blob/master/images/setting.PNG)
![d_window](https://github.com/Aboghazala/Hanash/blob/master/images/d_window.PNG)

example multi-downloading with speed limit of 10 KB/sec as a test

![concurrent windows](https://github.com/Aboghazala/Hanash/blob/master/images/concurrent_windows.PNG)


**-----Requirements -------**
```python
Python 3+
```

you can run one line command to install required packages:
```python
pip pycurl certifi PySimpleGUI mimetypes pyperclip plyer pillow youtube_dl
```
**note for pyperclip:**

Pyperclip is a cross-platform Python module for copy and paste clipboard functions. it is being used if you want to monitor clipboard for files urls and it will be processed automatically by Hanash DM.
On Linux, this module makes use of the xclip or xsel commands, which should come with the os. Otherwise run "sudo apt-get install xclip" on Debian like or "sudo pacman -S xclip" on archlinux



your feedback is most welcomed on https://github.com/Aboghazala/Hanash or email to mahmoud_elshahhat@yahoo.com

Thanks,
Mahmoud Elshahat 
2019


