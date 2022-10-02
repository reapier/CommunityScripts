import os
import xml.etree.ElementTree as xml
import base64
import glob
import re
import requests
import config
import log


class NfoParser:
    ''' Parse nfo files '''

    # Searched in the list order. First found is the one used.
    _image_formats = ["jpg", "jpeg", "png"]
    _image_suffixes = ["-landscape", "-thumb", "-cover", "-poster", ""]
    # Max number if images to process (2 for front/back cover in movies).
    _image_Max = 2

    def __init__(self, scene_path, folder_mode=False):
        # Finds nfo file
        nfo_path = None
        if config.nfo_location.lower() == "with files":
            if folder_mode:
                dir_path = os.path.dirname(scene_path)
                nfo_path = os.path.join(dir_path, "folder.nfo")
            else:
                nfo_path = os.path.splitext(scene_path)[0] + ".nfo"
        # else:
            # TODO: supports dedicated dir instead of "with files" (compatibility with nfo exporter)
        self._nfo_file = nfo_path
        self._nfo_root = None

    def __read_cover_image_file(self):
        thumb_images = []
        path_no_ext = os.path.splitext(self._nfo_file)[0]
        file_no_ext = os.path.split(path_no_ext)[1]
        files = sorted(glob.glob(f"{path_no_ext}*.*"))
        file_pattern = re.compile("^.*" + re.escape(file_no_ext) + "(-landscape\\d{0,2}|-thumb\\d{0,2}|-poster\\d{0,2}|-cover\\d{0,2}|\\d{0,2})\\.(jpe?g|png)$", re.I)
        index = 0
        for file in files:
            if index >= self._image_Max:
                break
            if file_pattern.match(file):
                with open(file, "rb") as img:
                    img_bytes = img.read()
                thumb_images.append(img_bytes)
                index += 1
        return thumb_images

    def ___extract_thumb_urls(self, filter):
        result = []
        matches = self._nfo_root.findall(filter)
        for match in matches:
            result.append(match.text)
        return result

    def __download_cover_images(self):
        # Prefer "landscape" images, then "poster", otherwise take any thumbnail image...
        thumb_urls = self.___extract_thumb_urls("thumb[@aspect='landscape']") or self.___extract_thumb_urls(
            "thumb[@aspect='poster']") or self.___extract_thumb_urls("thumb")
        # Ensure there are images and the count does not exceed the max allowed...
        if len(thumb_urls) == 0:
            return
        del thumb_urls[self._image_Max:]
        # Download images from url
        thumb_images = []
        for thumb_url in thumb_urls:
            img_bytes = None
            try:
                r = requests.get(thumb_url, timeout=10)
                img_bytes = r.content
                thumb_images.append(img_bytes)
            except Exception as e:
                log.LogDebug(
                    "Failed to download the cover image from {}: {}".format(thumb_url, e))
        return thumb_images

    def __extract_cover_images_b64(self):
        file_images = []
        # Get image from disk (file), otherwise from <thumb> tag (url)
        thumb_images =  self.__read_cover_image_file() or self.__download_cover_images()
        for thumb_image in thumb_images:
            thumb_b64img = base64.b64encode(thumb_image)
            if thumb_b64img:
                file_images.append(f"data:image/jpeg;base64,{thumb_b64img.decode('utf-8')}")
        return file_images

    def __extract_nfo_rating(self):
        user_rating = round(float(self._nfo_root.findtext("userrating") or 0))
        if user_rating > 0:
            return user_rating
        # <rating> is converted to a scale of 5 if needed
        rating = None
        rating_elem = self._nfo_root.find("ratings/rating")
        if rating_elem is not None:
            max = float(rating_elem.attrib["max"])
            value = float(rating_elem.findtext("value"))
            rating = round(value / (max / 5))
        return rating

    def __extract_nfo_date(self):
        # date either in <premiered> (full) or <year> (only the year)
        year = self._nfo_root.findtext("year")
        if year is not None:
            year = "{}-01-01".format(year.text)
        return self._nfo_root.findtext("premiered") or year

    def __extract_nfo_tags(self):
        file_tags = []
        # from nfo <tag>
        tags = self._nfo_root.findall("tag")
        for tag in tags:
            file_tags.append(tag.text)
        # from nfo <genre>
        genres = self._nfo_root.findall("genre")
        for genre in genres:
            file_tags.append(genre.text)
        return list(set(file_tags))

    def __extract_nfo_actors(self):
        file_actors = []
        actors = self._nfo_root.findall("actor/name")
        for actor in actors:
            file_actors.append(actor.text)
        return file_actors

    def parse(self, defaults={}):
        ''' Parses the nfo (with xml parser) '''
        if not os.path.exists(self._nfo_file):
            return
        if defaults is None:
            defaults = {}
        log.LogDebug("Parsing '{}'".format(self._nfo_file))
        # Parse NFO xml content (stripping non-standard whitespaces/new lines)
        try:
            with open(self._nfo_file, "r") as nfo:
                clean_nfo_content = nfo.read().strip()
            self._nfo_root = xml.fromstring(clean_nfo_content)
        except Exception as e:
            log.LogError("Could not parse nfo '{}'".format(self._nfo_file, e))
            return
        # Extract data from XML tree. Spec: https://kodi.wiki/view/NFO_files/Movies
        b64_images = self.__extract_cover_images_b64()
        file_data = {
            # TODO: supports stash uniqueid to match to existing scenes (compatibility with nfo exporter)
            "file": self._nfo_file,
            "source": "nfo",
            "title": self._nfo_root.findtext("title") or self._nfo_root.findtext("originaltitle") or self._nfo_root.findtext("sorttitle"),
            "director": self._nfo_root.findtext("director") or defaults.get("director"),
            "details": self._nfo_root.findtext("plot") or self._nfo_root.findtext("outline") or self._nfo_root.findtext("tagline") or defaults.get("details"),
            "studio": self._nfo_root.findtext("studio") or defaults.get("studio"),
            "date": self.__extract_nfo_date() or defaults.get("date"),
            "actors": self.__extract_nfo_actors() or defaults.get("actors"),
            # tags are merged with defaults
            "tags": list(set(self.__extract_nfo_tags() + (defaults.get("tags") or []))),
            "rating": self.__extract_nfo_rating() or defaults.get("rating"),
            "cover_image": None if len(b64_images) < 1 else b64_images[0],
            "other_image": None if len(b64_images) < 2 else b64_images[1],

            # Below are NFO extensions or liberal tag interpretations (not part of the standard KODI tags)
            "movie": self._nfo_root.findtext("set/name") or defaults.get("title"),
            "scene_index": self._nfo_root.findtext("set/index"),
            "url": self._nfo_root.findtext("url"),
        }
        return file_data
