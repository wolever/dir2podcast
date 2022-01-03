#!/usr/bin/env python
from __future__ import with_statement

import sys
import os
import urllib
import hashlib
import logging
import traceback
from os import path
from datetime import datetime
from xml.dom.minidom import Document, Element, Text

sys.path.insert(0, path.join(path.dirname(__file__), "libs/"))

from mutagen.mp3 import EasyMP3, error as mp3_error
from mutagen.mp4 import MP4, error as mp4_error

log = logging.getLogger()

def seconds2duration(seconds):
    return "%d:%02d" %(seconds / 60, seconds % 60)

def tounicode(s):
    if isinstance(s, unicode):
        return s
    if not isinstance(s, basestring):
        return unicode(s)
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


class PodcastItem(object):
    def __init__(self, url, file):
        self.file = file
        self.url = url
        self.error = None
        self.init()

    def init(self):
        pass

    def guid(self):
        md5 = hashlib.md5()
        for hunk in iter((lambda: self.file.read(4096)), ""):
            md5.update(hunk)
        self.file.seek(0)
        return "md5:" + md5.hexdigest()

    def mtime(self):
        mtime_int = os.path.getmtime(self.file.name)
        return datetime.fromtimestamp(mtime_int)

    def get_xml(self):
        item = EzElement("item")
        item["title"] = self.title()
        item["pubDate"] = self.mtime().strftime("%a, %d %b %Y %H:%M:%S +0000")
        item["itunes:author"] = self.author()
        item["itunes:subtitle"] = self.subtitle()
        item["itunes:duration"] = seconds2duration(self.length())
        item["guid"] = self.guid()
        item["enclosure"] = {
            "url": self.url,
            "length": os.path.getsize(self.file.name),
            "type": self.mimetype(),
        }
        return item


class MutogenItem(PodcastItem):
    def init(self):
        try:
            self.media = self.mutogen_type(self.file.name)
        except self.mutogen_error as e:
            self.error = str(e)

    def media_attr(self, key):
        if key not in self.media:
            return None
        val = self.media[key]
        if isinstance(val, list) and len(val) > 0:
            val = val[0]
        return val

    def mimetype(self):
        return self.media.mime[0]

    def length(self):
        return self.media.info.length

    def title(self):
        return self.media_attr("title") or os.path.basename(self.file.name)

    def author(self):
        return self.media_attr("artist")

    def subtitle(self):
        return self.media_attr("album")


class VideoPodcastItem(MutogenItem):
    extensions = ["mov", "mp4"]
    mutogen_type = MP4
    mutogen_error = mp4_error


class MP3PodcastItem(MutogenItem):
    extensions = ["mp3"]
    mutogen_type = EasyMP3
    mutogen_error = mp3_error


class Podcast(object):
    item_classes = [
        MP3PodcastItem,
        VideoPodcastItem,
    ]

    def __init__(self, dir):
        self.dir = path.realpath(dir)
        self.title = path.basename(self.dir)

    def _find_files(self):
        extensions = {}
        for item_cls in self.item_classes:
            extensions.update(
                (ext, item_cls)
                for ext in item_cls.extensions
            )
        for dirpath, dirnames, filenames in os.walk(self.dir):
            for file in filenames:
                _, _, ext = file.partition(".")
                ext = ext.lower()
                if ext in extensions:
                    yield extensions[ext], path.join(dirpath, file)


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

    def file2item(self, ItemCls, baseurl, file):
        url = baseurl + urllib.quote_plus(self._rel_path(file))
        item = ItemCls(url, open(file))
        if item.error:
            log.warning("Error loading %r: %r", file, item.error)
            return None
        return item

    def iter_file(self, file):
        file = urllib.unquote_plus(file)
        file = self.dir + "/" + file
        file = self._abs_path(file)
        size = os.stat(file).st_size
        def iterfile():
            with open(file) as f:
                data = f.read(1024)
                while data:
                    yield data
                    data = f.read(1024)
        return size, iterfile()

    def xml(self, baseurl):
        channel = EzElement("channel")
        channel["title"] = self.title

        items = []
        for item_cls, file in self._find_files():
            item = self.file2item(item_cls, baseurl, file)
            if item is None:
                continue
            items.append(item)

        items.sort(key=lambda i: i.mtime())

        for item in items:
            channel.appendChild(item.get_xml())

        rss = EzElement("rss")
        rss["xmlns:itunes"] = "http://www.itunes.com/dtds/podcast-1.0.dtd"
        rss["version"] = "2.0"
        rss.appendChild(channel)

        doc = Document()
        doc.appendChild(rss)
        return doc.toprettyxml(encoding="utf-8")

###
# WSGI/HTTP stuff
###
from wsgiref.util import application_uri
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
        podcast = self.podcasts[podcast_name]
        size, data = podcast.iter_file(file_name)
        if data is None:
            return self.send_not_found(environ)
        return "200 OK", [("Content-length", str(size))], data

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
            tb = traceback.format_exc()
            data = [ tb, str(e) ]
            log.exception("Error encountered while processing request:")

        start_response(status, headers)
        return data


def main():
    logging.basicConfig()
    import sys
    if len(sys.argv) < 2:
        print "Usage: %s [--export] DIRECTORY [DIRECTORY ...]" %(sys.argv[0], )
        return 1

    podcasts = []
    for arg in sys.argv[1:]:
        dir = path.realpath(arg)
        name = path.basename(dir)
        podcast = Podcast(dir)
        podcasts.append((name, podcast))
        print "http://0.0.0.0:9431/" + name

    from werkzeug.serving import run_simple
    app = Dir2PodcastWsgiApp(podcasts)
    httpd = run_simple('0.0.0.0', 9431, app.handle_request,
                       use_reloader=True, threaded=True)
    httpd.serve_forever()
