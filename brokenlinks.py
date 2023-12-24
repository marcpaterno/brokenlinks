import logging
import os.path
from typing import Iterator, Set, TextIO

import urllib.parse

import requests
from requests.exceptions import (
    RequestException,
    ReadTimeout,
    ConnectionError as RequestConnectionError,
)
from bs4 import BeautifulSoup

## TODO: Use multiple threads to speed the processing. This program will mostly
## be waiting on network IO; this is the classic example for the good use of
## threads in Python.

START_URLS = ["https://ed.fnal.gov"]
GOOD_STATUS_CODES = set([200])
EXPECTED_SCHEMES = set(["http", "https"])
UNHANDLED_SCHEMES = set(["mailto", "javascript"])
UNTRAVERSABLE_TYPES = set(
    ["gif", "jpg", "jpeg", "mp4", "mov", "pdf", "ppt", "pptx", "xls", "xlsx"]
)


def is_bad(status: int) -> bool:
    """Return whether we consider this status to be 'bad' (broken) or not"""
    group = status // 100
    return group != 2


def is_not_searchable(filepath: str) -> bool:
    """ "Return True if we should search through the resources named by this
    filepath, and False if not.
    """
    # TODO: This file type identification should be made more robust.
    suffix = filepath.split(".")[-1].lower()
    return suffix in UNTRAVERSABLE_TYPES


def should_traverse_url(parsed: urllib.parse.SplitResult) -> bool:
    """Return True if the URL should be traversed (not merely tested)."""
    if parsed.scheme not in EXPECTED_SCHEMES:
        # We will not try to traverse, e.g., a 'mailto:','javascript:' links.
        return False
    if is_not_searchable(parsed.path):
        return False
    return parsed.hostname == "ed.fnal.gov"


def parse_links(
    current_page: urllib.parse.SplitResult, current_html: BeautifulSoup
) -> Iterator[str]:
    """Parse the given HTML text, yielding each link found."""
    for anchor in current_html.find_all("a", href=True):
        new_url = anchor.get("href")
        msg = "parse_links processing href %s"
        logging.debug(msg, new_url)
        full_url = fixup_url(
            current_page.scheme, current_page.netloc, current_page.path, new_url
        )
        yield full_url


def fixup_url(scheme: str, server: str, page_path: str, new_url: str) -> str:
    """Fixup a URL, returning a complete and absolute URL to the same resource."""
    split_url = urllib.parse.urlsplit(new_url)

    if split_url.scheme.lower() == "mailto":
        return new_url

    # Canonicalize the parts.
    normalized_scheme = split_url.scheme.lower()
    normalized_netloc = split_url.netloc.lower()
    normalized_path = "/".join(
        segment.strip("/") for segment in split_url.path.split("/")
    )

    # We don't do anything more to mailto links.

    # Try to duplicate the rules followed by the combination of a web browser
    # and web server.
    # See: https://stackoverflow.com/questions/2005079/absolute-vs-relative-urls
    if normalized_scheme == "":
        normalized_scheme = scheme
    if normalized_scheme in ("https", "http"):
        if normalized_netloc == "":
            normalized_netloc = server
        if normalized_path == "":
            normalized_path = "/"
        if not normalized_path.startswith("/"):
            normalized_path = complete_relative_link(normalized_path, page_path)

    return f"{normalized_scheme}://{normalized_netloc}{normalized_path}"


def complete_relative_link(relative_link: str, page_path: str) -> str:
    """Complete the given relative link by adding the current directory from
    the current page."""
    current_directory = os.path.dirname(page_path)
    new_path = os.path.join(current_directory, relative_link)
    return new_path


class BrokenLinkCollector:
    """Main application object."""

    def __init__(
        self, results: TextIO, redirects: TextIO, visited: TextIO, unhandled: TextIO
    ):
        self.seen_urls: Set[str] = set()
        self.results = results
        self.redirects = redirects
        self.visited = visited
        self.unhandled = unhandled
        self.write_headers()

    def write_headers(self) -> None:
        """Write the headers for all output files."""
        self.results.write("host_page,broken_url,status\n")
        self.redirects.write("host_page,redirected_url,stauts\n")
        self.visited.write("url\n")
        self.unhandled.write("page,url\n")

    def process(self, page_full_url: str, full_url: str) -> None:
        """Process the given URL, and all the (internal) pages to which it links, recursively."""
        # Only process each URL once, regardless of how many times we see it.
        msg = "Starting to process link %s on page %s"
        logging.debug(msg, full_url, page_full_url)

        if full_url in self.seen_urls:
            msg = "We have already seen link %s, will not process it again"
            logging.debug(msg, full_url)
            return

        msg = "Registering link %s as seen"
        logging.debug(msg, full_url)
        self.seen_urls.add(full_url)
        self.visited.write(f"{full_url}\n")
        parsed_url = urllib.parse.urlsplit(full_url)
        if parsed_url.scheme.lower() in UNHANDLED_SCHEMES:
            self.unhandled.write(f"{page_full_url},{full_url}\n")
            return
        if should_traverse_url(parsed_url):
            self.process_traversable_url(page_full_url, full_url)
            return
        self.process_external_url(page_full_url, full_url)

    def process_external_url(self, page: str, url: str) -> None:
        """Process a URL that we are not intended to search for links."""
        msg = "Will not traverse link %s; starting test for access"
        logging.debug(msg, url)
        try:
            r = requests.head(url, timeout=1.0)
            msg = "Status for %s is %d"
            logging.debug(msg, url, r.status_code)
            if is_bad(r.status_code):
                self.write_bad_link(page, r, url)
        except (RequestException, ReadTimeout, RequestConnectionError):
            # We are using status code = 999 to represent any error that
            # caused the server to not return a result. More specificity
            # is possible, if desired.
            self.results.write(f"{page},{url},999\n")

    def process_traversable_url(self, page: str, url: str) -> None:
        """Process a URL that we are intended to search for links.
        Both page and url are full URLs (with scheme, server, and path)."""
        msg = "Trying to get traversable url %s"
        logging.debug(msg, url)

        try:
            r = requests.get(url, timeout=2.0)
            msg = "Status for %s is %d"
            logging.debug(msg, url, r.status_code)
            if is_bad(r.status_code):
                self.write_bad_link(page, r, url)
            else:
                soup = BeautifulSoup(r.content, features="lxml")
                current_page_split = urllib.parse.urlsplit(page)
                for new_link in parse_links(current_page_split, soup):
                    # new_link will be a full URL.
                    # Recursively process the new link, recording it as contents of the current URL.
                    self.process(url, new_link)
        except (RequestException, ReadTimeout, ConnectionError):
            self.results.write(f"{page},{url},999\n")

    def write_bad_link(self, page: str, r: requests.Response, url: str) -> None:
        group = r.status_code // 100
        if group == 3:
            self.redirects.write(f"{page},{url},{r.status_code}\n")
        else:
            self.results.write(f"{page},{url},{r.status_code}\n")


if __name__ == "__main__":
    logging.basicConfig(filename="debug.log", encoding="utf-8", level=logging.DEBUG)
    with open("results.csv", mode="w", encoding="utf-8") as results, open(
        "visited_links.txt", mode="w", encoding="utf-8"
    ) as visited_links, open(
        "unhandled_links.txt", mode="w", encoding="utf-8"
    ) as unhandled_links, open(
        "redirects.csv", mode="w", encoding="utf-8"
    ) as redirects:
        app = BrokenLinkCollector(results, redirects, visited_links, unhandled_links)
        for item in START_URLS:
            msg = "Start processing %s"
            logging.debug(msg, item)
            app.process(item, item)
            msg = "Finished processing %s"
            logging.debug(msg, item)

    logging.debug("Finished processing all top-level URLs.")
