#!/usr/bin/env python

import os
import sys

from setuptools import setup, find_packages

os.chdir(os.path.dirname(sys.argv[0]) or ".")

try:
    long_description = open("README.rst", "U").read()
except IOError:
    long_description = "See https://github.com/wolever/dir2podcast"

import libdir2podcast
version = "%s.%s.%s" %libdir2podcast.__version__

setup(
    name="dir2podcast",
    version=version,
    url="https://github.com/wolever/dir2podcast",
    author="David Wolever",
    author_email="david@wolever.net",
    description="""
        dir2pi builds a hacky podcast from a directory of MP3s
    """,
    long_description=long_description,
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'dir2podcast = libdir2podcast.dir2podcast:main',
        ],
    },
    license="BSD",
)
