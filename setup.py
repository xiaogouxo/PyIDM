"""
    pyIDM

    multi-connections internet download manager, based on "pyCuRL/curl", "youtube_dl", and "PySimpleGUI"

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""
import setuptools, os

# Read version from version.py file
with open(os.path.join('pyidm', 'version.py')) as version_file:
    __version__ = version_file.read().split('=')[-1].strip().replace("'", '')

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pyIDM",
    version=__version__,
    scripts=['pyIDM.py'],
    author="Mahmoud Elshahat",
    author_email="mahmoud_elshahhat@yahoo.com",
    description="download manager",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pyIDM/pyIDM ",
    packages=setuptools.find_packages(),
    keywords="internet download manager youtube downloader pycurl youtube-dl PySimpleGUI",
    project_urls={
    'Source': 'https://github.com/pyIDM/pyIDM',
    'Tracker': 'https://github.com/pyIDM/pyIDM/issues',
    'Releases': 'https://github.com/pyIDM/pyIDM/releases',
    'Screenshots': 'https://github.com/pyIDM/pyIDM/issues/13'
    },
    install_requires=['PySimpleGUI', 'pyperclip', 'plyer', 'certifi', 'youtube_dl', 'pycurl'], #, 'mimetypes'
    # py_modules=['src/' + x for x in ['about', 'brain', 'config', 'downloaditem', 'gui', 'main', 'pyIDM', 'setting', 'test', 'update', 'utils', 'VERSION', 'version', 'video', 'worker']],
    # data_files=[('my_data', ['data/data_file'])], # could be used to install desktop shortcut 
    classifiers=[
        "Programming Language :: Python :: 3",
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)