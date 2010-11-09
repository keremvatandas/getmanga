#!/usr/bin/env python
"""Yet another (multi-site) manga downloader"""

# Copyright (c) 2010, Jamaludin Ahmad
# Released subject to the MIT License.
# Please see http://en.wikipedia.org/wiki/MIT_License

# Changes
# version 0.3 : download threading
# version 0.2 : config support for batch download
# version 0.1 : initial release

from __future__ import division

import os
import sys
import re
import urllib2
import zipfile
import gzip
import StringIO
import ConfigParser
import threading
import Queue

try:
    import argparse
except ImportError:
    sys.exit('You need to have "argparse" module installed '
             'to run this script')

if sys.version_info < (2, 7):
    try:
        from ordereddict import OrderedDict
    except ImportError:
        sys.exit('You need to have "ordereddict" module installed '
                 'to run this script')


class MangaException(Exception):
    """Exception class for manga"""
    pass


class Manga:
    """Base class for manga downloading"""
    site = None
    descending_chapters = True

    chapters_regex = None
    pages_regex = None
    image_regex = None

    def __init__(self, title=None, directory='.'):
        """Initiate manga title and download directory"""
        self.title = self._title(title)

        directory = os.path.abspath(os.path.expanduser(directory))
        if not os.path.isdir(directory):
            try:
                os.makedirs(directory)
            except OSError, msg:
                raise MangaException(msg)
        self.directory = directory

    def get(self, chapter=None, begin=None, end=None, new=False):
        """Decides which action executed from user input"""
        chapter_dict = self.chapterdict()
        chapter_ids = chapter_dict.keys()

        if new:
            latest = chapter_ids[-1]
            self.download(latest, chapter_dict[latest])

        elif chapter:
            chapter_id = self._id(chapter)
            if chapter_id in chapter_ids:
                self.download(chapter_id, chapter_dict[chapter_id])
            else:
                raise MangaException('Chapter does not exist')

        elif begin:
            start = position(self._id(begin), chapter_ids)
            if end:
                stop = position(self._id(end), chapter_ids)
            else:
                stop = None

            if cmp(chapter_ids[-1], start) == 1:
                for chapter_id in chapter_ids[start:stop]:
                    self.download(chapter_id, chapter_dict[chapter_id])
            else:
                raise MangaException('Can\'t begin from non-existent '
                                     'chapter')

        else:
            for chapter_id, chapter_dir in chapter_dict.iteritems():
                self.download(chapter_id, chapter_dir)

    def chapterdict(self):
        """Returns a dictionary of manga chapters available"""
        sys.stdout.write('retrieving %s info page..\n' % self.title)

        info_html = urlopen(self._infourl())
        chapters = self.chapters_regex.findall(info_html)
        if self.descending_chapters:
            chapters.reverse()

        chapter_dict = OrderedDict()
        for chapter in chapters:
            if self._verify(chapter[0]):
                chapter_dir = self._cleanup(chapter[0])
                chapter_dict.update({chapter[1]: chapter_dir})

        if chapter_dict:
            return chapter_dict
        else:
            raise MangaException('%s: No such title' % self.title)

    def download(self, chapter_id, chapter_dir):
        """Download and create zipped manga chapter"""
        cbz_name = os.path.join(self.directory,
                                self._name(chapter_id, chapter_dir))
        if os.path.isfile(cbz_name):
            sys.stdout.write('file %s exist, skipped download\n' %
                              cbz_name)
        else:
            tmp_name = '%s.tmp' % cbz_name
            chapter_html = urlopen(self._pageurl(chapter_dir))
            pages = self.pages_regex.findall(chapter_html)
            pages = sorted(list(set(pages)), key=int)

            sys.stdout.write('downloading %s %s:\n' %
                             (self.title, chapter_id))
            try:
                progress(0, len(pages))
                threads, semaphore, queue = ([], threading.Semaphore(4),
                                             Queue.Queue())
                cbz = zipfile.ZipFile(tmp_name, mode='w',
                                      compression=zipfile.ZIP_DEFLATED)
                for page in pages:
                    thread = threading.Thread(target=self._pagedownload,
                                              args=(semaphore, queue,
                                                    chapter_dir, page))
                    thread.start()
                    threads.append(thread)
                for thread in threads:
                    thread.join()
                    image = queue.get()
                    cbz.writestr(image[0], image[1])
                    progress(len(cbz.filelist), len(pages))
                cbz.close()
                os.rename(tmp_name, cbz_name)
            except Exception, msg:
                os.remove(tmp_name)
                raise MangaException(msg)

    def _pagedownload(self, semaphore, queue, chapter_dir, page):
        """Downloads page images inside a thread"""
        semaphore.acquire()
        page_html = urlopen(self._pageurl(chapter_dir, page))
        image_url = self.image_regex.findall(page_html)[0]
        image_name = re.search(r'([\w\.]+)$', image_url).group()
        image_file = urlopen(image_url)
        queue.put((image_name, image_file))
        semaphore.release()

    def _title(self, title):
        """Return the right manga title from user input"""
        return re.sub(r'\W+', '_',
                      re.sub(r'^\W+|W+$', '', title.lower()))

    def _id(self, chapter):
        """Returns the right chapter number formatting from user input"""
        return str(chapter)

    def _infourl(self):
        """Returns the index page's url of manga title"""
        return '%s/manga/%s/' % (self.site, self.title)

    def _pageurl(self, chapter_dir, page='1'):
        """Returns manga image page url"""
        return '%s%s/%s' % (self.site, chapter_dir, page)

    def _name(self, chapter_id, chapter_dir):
        """Returns the appropriate name for the zipped chapter"""
        match = re.search(r'v\d+', chapter_dir)
        if match:
            filename = '%s_%sc%s.cbz' % \
                        (self.title, match.group(), chapter_id)
        else:
            filename = '%s_c%s.cbz' % (self.title, chapter_id)
        return filename

    def _verify(self, chapter_dir):
        """Returns boolean status of a chapter validity"""
        return True

    def _cleanup(self, chapter_dir):
        """Returns a cleanup chapter directory"""
        return chapter_dir


class MangaFox(Manga):
    """class for mangafox site"""
    site = 'http://www.mangafox.com'

    chapters_regex = re.compile(r'</a>\s*<a href="(\S+)" class="chico">'
                                 '\s*.* Ch\.([\d\.]+):')
    pages_regex = re.compile(r'<option value="\d+" .*?>(\d+)</option>')
    image_regex = re.compile(r'<img src="(\S+)" width="\d+" id="image"')

    def _id(self, chapter):
        """Returns the right chapter number formatting from user input"""
        return '%03d' % chapter

    def _infourl(self):
        """Returns the index page's url of manga title"""
        return '%s/manga/%s?no_warning=1' % (self.site, self.title)

    def _pageurl(self, chapter_dir, page='1'):
        """Returns manga image page url"""
        return '%s%s%s.html' % (self.site, chapter_dir, page)


class MangaStream(Manga):
    """class for mangastream site"""
    site = 'http://mangastream.com'

    chapters_regex = re.compile(r'<a href="(\S+)">(\d+)')
    pages_regex = re.compile(r'<option value="\S+".*?>(\d{1,2})</option>')
    image_regex = re.compile(r'this.src=\'(\S+)\'" border="0"')

    def _infourl(self):
        """Returns the index page's url of manga title"""
        return '%s/manga/' % self.site

    def _verify(self, chapter_dir):
        """Returns boolean status of a chapter validity"""
        return re.search(self.title, chapter_dir)

    def _cleanup(self, chapter_dir):
        """Returns a cleanup chapter directory"""
        return re.sub(r'/\d+$', '', chapter_dir)


class MangaToshokan(Manga):
    """class for mangatoshokan site"""
    site = 'http://www.mangatoshokan.com'

    chapters_regex = re.compile(r'href=\'(\S+)\' .* (\d+)</a>')
    pages_regex = re.compile(r'<option value="\S+".*?>(\d+)</option>')
    image_regex = re.compile(r'dir=\'rtl\'><img src="(\S+)"')

    def _title(self, title):
        """Returns the right manga title from user input"""
        return re.sub(r'[^\-0-9a-zA-Z]+', '', re.sub(r'[\s_]', '-', title))

    def _infourl(self):
        """Returns the index page's url of manga title"""
        return '%s/series/%s' % (self.site, self.title)


class MangaBle(Manga):
    """class for mangable site"""
    site = 'http://mangable.com'

    chapters_regex = re.compile(r'href="(\S+)" title="[\D\s]*(\d+)">')
    pages_regex = re.compile(r'<option value="\d+">Page (\d+)</option>')
    image_regex = re.compile(r'<img src="(\S+)" class="image"')

    def _title(self, title):
        """Returns the right manga title from user input"""
        return re.sub(r'[^\-_0-9a-zA-Z]+', '',
                      re.sub(r'\s', '_', title.lower()))

    def _infourl(self):
        """Returns the index page's url of manga title"""
        return '%s/%s' % (self.site, self.title)

    def _pageurl(self, chapter_dir, page=None):
        """Returns manga image page url"""
        if page:
            return '%s%s' % (chapter_dir, page)
        else:
            return chapter_dir


class MangaAnimea(Manga):
    """class for manga animea site"""
    site = 'http://manga.animea.net'

    chapters_regex = re.compile(r'href="(\S+)">["\s\w]+\s(\d+)</a>\s')
    pages_regex = re.compile(r'<option value="\d+">(\d+)</option>')
    image_regex = re.compile(r'<img src="(\S+)" .* class="chapter_img"')

    def _title(self, title):
        """Returns the right manga title from user input"""
        return re.sub(r'\W+', '-', title.lower())

    def _infourl(self):
        """Returns the index page's url of manga title"""
        return '%s/%s.html?skip=1' % (self.site, self.title)

    def _pageurl(self, chapter_dir, page='1'):
        """Returns manga image page url"""
        return re.sub(r'.html$', '-page-%s.html' % page, chapter_dir)

    def _verify(self, chapter_dir):
        """Returns boolean status of a chapter validity"""
        return re.search(self.title, chapter_dir)


class MangaReader(Manga):
    """class for mangareader site"""
    site = 'http://www.mangareader.net'
    descending_chapters = False

    chapters_regex = re.compile(r'<td> <a class="chico" href="(\S+)">'
                                 '\s+.+\s+(\d+)</a>')
    pages_regex = re.compile(r'<option value="\S+">(\d+)</option>')
    image_regex = re.compile(r'<img\s+src="(\S+)" .* width="800"')

    def _title(self, title):
        """Returns the right manga title from user input"""
        return re.sub(r'[^\-0-9a-zA-Z]', '',
                      re.sub(r'[\s_]', '-', title.lower()))

    def _infourl(self):
        """Returns the index page's url of manga title"""
        listhtml = urlopen('%s/alphabetical' % self.site)
        info = re.findall(r'\d+/' + self.title + '.html', listhtml)[0]
        return '%s/%s' % (self.site, info)

    def _pageurl(self, chapter_dir, page='1'):
        """Returns manga image page url"""
        page = re.sub(r'\-\d+/', '-%s/' % page, chapter_dir)
        return '%s/%s' % (self.site, page)


def urlopen(url):
    """Returns data available (html or image file) from a url"""
    request = urllib2.Request(url)
    request.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; U; ' \
                       'Intel Mac OS X 10_6_4; id) AppleWebKit/533.18.1 ' \
                       '(KHTML, like Gecko) Version/5.0.2 Safari/533.18.5')
    request.add_header('Accept-encoding', 'gzip')

    data = None
    retry = 0
    while retry < 5:
        try:
            response = urllib2.urlopen(request, timeout=15)
            data = response.read()
        except urllib2.HTTPError, msg:
            raise MangaException('HTTP Error: %s - %s\n' % (msg.code, url))
        except Exception:
            #what may goes here: urllib2.URLError, socket.timeout,
            #                    httplib.BadStatusLine
            retry += 1
        else:
            if response.headers.getheader('content-length'):
                if len(data) == \
                        int(response.headers.getheader('content-length')):
                    retry = 5
                else:
                    retry = 0
            else:
                retry = 5
            if response.headers.getheader('content-encoding') == 'gzip':
                compressed = StringIO.StringIO(data)
                data = gzip.GzipFile(fileobj=compressed).read()
            response.close()
    if data:
        return data
    else:
        raise MangaException('Failed to retrieve %s' % url)


def progress(page, total):
    """Display progress bar"""
    page, total = int(page), int(total)
    marks = int(round(50 * (page / total)))
    spaces = int(round(50 - marks))

    loader = '[' + ('#' * int(marks)) + ('-' * int(spaces)) + ']'

    sys.stdout.write('%s page %d of %d\r' % (loader, page, total))
    if page == total:
        sys.stdout.write('\n')
    sys.stdout.flush()


def position(item, listobj):
    """Returns position of an item inside a list object"""
    for index in xrange(len(listobj)):
        if listobj[index] == item:
            return index


def cmdparse():
    """Returns parsed arguments from command line"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', type=str,
                        help='%(prog)s config file')
    parser.add_argument('-s', '--site', choices=('animea', 'mangable',
                        'mangafox', 'mangareader', 'mangastream',
                        'toshokan'), help='manga site to download from')
    parser.add_argument('-t', '--title', type=str,
                        help='manga title to download')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-n', '--new', action='store_true',
                       help='download the last chapter')
    group.add_argument('-c', '--chapter', type=int,
                       help='chapter number to download a single chapter')
    group.add_argument('-b', '--begin', type=int,
                       help='chapter number to begin on a bulk download')
    parser.add_argument('-e', '--end', type=int,
                        help='chapter number to end on a bulk download')
    parser.add_argument('-d', '--dir', type=str, default='.',
                        help='download directory')
    parser.add_argument('-v', '--version', action='version',
                        version='%(prog)s 0.3',
                        help='show program version and exit')
    args = parser.parse_args()

    if args.file:
        if not os.path.isfile(args.file):
            parser.print_usage()
            sys.exit('%s: error: config file does not exit' %
                     parser.prog)
    elif not args.site:
        parser.print_usage()
        sys.exit('%s: error: argument -s/--start is required' %
                 parser.prog)
    elif not args.title:
        parser.print_usage()
        sys.exit('%s: error: argument -t/--title is required' %
                 parser.prog)
    elif args.end:
        if not args.begin:
            parser.print_usage()
            sys.exit('%s: error: argument -e/--end: need -s/--start' %
                     parser.prog)
        elif args.end < args.begin:
            parser.print_usage()
            sys.exit('%s: error: argument -e/--end: should be bigger'
                     'than -s/--start' % parser.prog)
    return args


def configparse(filepath):
    """Returns parsed config from an ini file"""
    if sys.version_info >= (2, 6):
        parser = ConfigParser.SafeConfigParser(dict_type=OrderedDict)
    else:
        parser = ConfigParser.SafeConfigParser()
    parser.read(filepath)
    config = []
    for title in parser.sections():
        try:
            config.append((parser.get(title, 'site'), title,
                           parser.get(title, 'dir'),
                           parser.getboolean(title, 'new')))
        except Exception, msg:
            raise MangaException('Config Error: %s' % msg)
    return config


def main():
    """Decide the right action from the command line"""
    mangaclass = {'animea': MangaAnimea,
                  'mangable': MangaBle,
                  'mangafox': MangaFox,
                  'mangareader': MangaReader,
                  'mangastream': MangaStream,
                  'toshokan': MangaToshokan}

    args = cmdparse()

    try:
        if args.file:
            config = configparse(args.file)
            for option in config:
                site, title, directory, new = option
                manga = mangaclass[site](title, directory)
                manga.get(new=new)
        else:
            manga = mangaclass[args.site](args.title, args.dir)
            manga.get(chapter=args.chapter, begin=args.begin,
                      end=args.end, new=args.new)
    except MangaException, msg:
        sys.exit(msg)
    except KeyboardInterrupt:
        sys.exit('Cancelling download... quit')


if __name__ == '__main__':
    main()
