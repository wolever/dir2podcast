#!/usr/bin/env python

import sys
from os import path
from xml.dom.minidom import Document, Element, Text

sys.path.insert(0, path.join(path.dirname(__file__), "libs/"))

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

def seconds2duration(seconds):
    return "%d:%02d" %(seconds / 60, seconds % 60)

def tounicode(s):
    if isinstance(s, unicode):
        return s
    try:
        return unicode(s, "utf-8")
    except UnicodeDecodeError:
        return unicode(s, "latin-1")


class EzElement(Element):
    def __init__(self, tag):
        Element.__init__(self, tag)

    def __setitem__(self, tag, value):
        child = Element(tounicode(tag))

        if isinstance(value, basestring):
            text = Text()
            text.data = tounicode(value)
            child.appendChild(text)

        elif isinstance(value, dict):
            for key, val in value.items():
                child.setAttribute(tounicode(key), tounicode(val))
        else:
            raise Exception("Ohno!")

        self.appendChild(child)


class Channel(EzElement):
    def __init__(self):
        EzElement.__init__(self, "channel")

    def add_item(self, file):
        audio = MP3(file, ID3=EasyID3)

        def val(x):
            if isinstance(x, list) and len(x) > 0:
                x = x[0]
            return x

        item = EzElement("item")
        item["title"] = val(audio["title"]) or path.basename(file)
        item["itunes:author"] = val(audio["artist"]) or None
        item["itunes:subtitle"] = val(audio["album"]) or None
        item["itunes:duration"] = seconds2duration(audio.info.length)
        item["guid"] = file
        item["enclosure"] = {"url": "file/" + file}

        self.appendChild(item)

class Podcast(object):
    title = "Some Podcast"

    def send_xml(self, environ):
        return "200 Ok", [("Content-type", "text/plain")], [self.xml()]

    def xml(self):
        channel = Channel()
        channel["title"] = "Some Podcast"
        channel.add_item("test.mp3")

        rss = Element("rss")
        rss.setAttribute("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
        rss.setAttribute("version", "2.0")
        rss.appendChild(channel)

        doc = Document()
        doc.appendChild(rss)
        return doc.toprettyxml(encoding="utf-8")

###
# WSGI/HTTP stuff
###
from wsgiref.util import request_uri
import re

def send_not_found(environ, *ignored):
    resp = environ["PATH_INFO"] + " not found." 
    headers = [('Content-type', 'text/plain')]
    return "404 Not Found", headers, [resp]

urls = [
    ("^favicon.ico$", send_not_found),
]

def dir2podcast_app(environ, start_response):
    url = environ["PATH_INFO"][1:]
    handler = send_not_found
    args = []
    for regex, handler in urls:
        match = re.match(regex, url)
        if match:
            args = match.groups()
            break

    try:
        status, headers, data = handler(environ, *args)
    except Exception, e:
        status = "500 Internal error"
        headers = [('Content-type', 'text/plain')]
        data = [ str(e) ]

    start_response(status, headers)
    return data


def main():
    from wsgiref.simple_server import make_server
    httpd = make_server('', 8000, dir2podcast_app)
    httpd.serve_forever()
