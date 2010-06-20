#!/usr/bin/env python
from __future__ import with_statement

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
        if value is None:
            return

        child = Element(tounicode(tag))

        if isinstance(value, basestring):
            text = Text()
            text.data = tounicode(value)
            child.appendChild(text)

        elif isinstance(value, dict):
            for key, val in value.items():
                child.setAttribute(tounicode(key), tounicode(val))
        else:
            raise Exception("Ohno! I didn't expect %r" %(value, ))

        self.appendChild(child)


class Podcast(object):
    def __init__(self, dir):
        self.dir = path.realpath(dir)
        self.title = path.basename(self.dir)

    def _find_files(self):
        yield "test.mp3"

    def _abs_path(self, file):
        file = path.realpath(file)
        if not file.startswith(self.dir):
            raise Exception("%r is outside of %r" %(file, self.dir))
        if not path.exists(file):
            raise Exception("%r doesn't exist." %(file, ))
        return file

    def _rel_path(self, file):
        file = self._abs_path(file)
        return file[len(self.dir)+1:]

    def file2item(self, baseurl, file):
        audio = MP3(self._abs_path(file), ID3=EasyID3)
        def val(key):
            if key not in audio:
                return None
            val = audio[key]
            if isinstance(val, list) and len(val) > 0:
                val = val[0]
            return val

        item = EzElement("item")
        item["title"] = val("title") or path.basename(file)
        item["itunes:author"] = val("artist") or None
        item["itunes:subtitle"] = val("album") or None
        item["itunes:duration"] = seconds2duration(audio.info.length)
        item["guid"] = self._abs_path(file)
        item["enclosure"] = {"url": baseurl + self._rel_path(file)}

        return item

    def iter_file(self, file):
        file = self._abs_path(file)
        def iterfile():
            with open(file) as f:
                data = f.read(1024)
                while data:
                    yield data
                    data = f.read(1024)
        return iterfile()

    def xml(self, baseurl):
        channel = EzElement("channel")
        channel["title"] = self.title

        for file in self._find_files():
            item = self.file2item(baseurl, file)
            channel.appendChild(item)

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
from wsgiref.util import request_uri, application_uri
import re

class Dir2PodcastWsgiApp(object):

    urls = [
        (r"^$", "send_podcast_list"),
        (r"^([^/]*)/?$", "send_podcast"),
        (r"^([^/]*)/(.*)$", "send_file"),
    ]
    urls = [ (re.compile(regex), url) for regex, url in urls ]

    def __init__(self, podcasts):
        # podcasts = [ (name, Podcast), ... ]
        self.podcasts = dict(podcasts)

    def send_not_found(self, environ, *ignored):
        resp = environ["PATH_INFO"] + " not found." 
        headers = [('Content-type', 'text/plain')]
        return "404 Not Found", headers, [resp]

    def send_podcast(self, environ, podcast_name):
        if podcast_name not in self.podcasts:
            return self.send_not_found(environ)
        baseurl = application_uri(environ) + podcast_name + "/"
        podcast = self.podcasts[podcast_name]
        return "200 OK", [], podcast.xml(baseurl)

    def send_file(self, environ, podcast_name, file_name):
        if podcast_name not in self.podcasts:
            return self.send_not_found(environ)
        data = self.podcasts[podcast_name].iter_file(file_name)
        if data is None:
            return self.send_not_found(environ)
        return "200 OK", [], data

    def handle_request(self, environ, start_response):
        url = environ["PATH_INFO"][1:]

        handler = self.send_not_found
        args = []
        for regex, handler_name in self.urls:
            match = re.match(regex, url)
            if match:
                handler = getattr(self, handler_name)
                args = match.groups()
                break

        try:
            status, headers, data = handler(environ, *args)
        except Exception, e:
            status = "500 Internal error"
            headers = [('Content-type', 'text/plain')]
            import traceback, sys
            tb = traceback.format_exc() #TRACEBACK
            data = [ tb, str(e) ]

        start_response(status, headers)
        return data


def main():
    from wsgiref.simple_server import make_server
    podcasts = [ ("test", Podcast(".")) ]
    app = Dir2PodcastWsgiApp(podcasts)
    httpd = make_server('', 8000, app.handle_request)
    httpd.serve_forever()
