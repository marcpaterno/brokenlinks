import logging
from typing import Iterator, Set, TextIO, Tuple

import urllib.parse

import requests
from requests.exceptions import RequestException, ReadTimeout
from bs4 import BeautifulSoup

## TODO: Use multiple threads to speed the processing. This program will mostly
## be waiting on network IO; this is the classic example for the good use of
## threads in Python.

START_URLS = ["https://ed.fnal.gov"]
GOOD_STATUS_CODES = set([200])
EXPECTED_SCHEMES = set(["http", "https"])
UNTRAVERSABLE_TYPES = set(["gif", "jpg", "jpeg", "mp4", "mov", "pdf"])


def is_bad(status: int) -> bool:
    """Return whether we consider this status to be 'bad' (broken) or not"""
    return status not in GOOD_STATUS_CODES


def is_not_searchable(filepath: str) -> bool:
    """ "Return True if we should search through the resources named by this
    filepath, and False if not.
    """
    # TODO: This file type identification should be made more robust.
    suffix = filepath.split(".")[-1].lower()
    return suffix in UNTRAVERSABLE_TYPES


def should_traverse_url(url: str) -> bool:
    """Return True if the URL should be traversed (not merely tested)."""
    result = urllib.parse.urlsplit(url)
    if result.scheme not in EXPECTED_SCHEMES:
        return False
    if is_not_searchable(result.path):
        return False
    return result.hostname == "ed.fnal.gov"


def parse_links(html: BeautifulSoup) -> Iterator[str]:
    """Parse the given HTML text, yielding each link found."""
    for anchor in html.find_all("a", href=True):
        new_url = anchor.get("href")
        # We have to deal with ugly local hrefs.
        if new_url.startswith("https:"):
            yield new_url
        elif new_url.startswith("http:"):
            yield new_url
        elif new_url.startswith("/"):
            repaired_url = f"https://ed.fnal.gov{new_url}"
        else:
            repaired_url = f"https://ed.fnal.gov/{new_url}"
            yield repaired_url


class BrokenLinkCollector:
    """Main application object."""

    def __init__(self):
        self.seen_urls: Set[str] = set()
        self.broken_links: Set[Tuple[str, str, int]] = set()

    def process(self, page: str, url: str) -> None:
        """Process the given URL, and all the (internal) pages to which it links, recursively."""
        # Only process each URL once, regardless of how many times we see it.
        msg = "Starting to process link %s on page %s"
        logging.debug(msg, url, page)
        if url in self.seen_urls:
            msg = "We have already seen link %s, will not process it again"
            logging.debug(msg, url)
            return

        msg = "Registering link %s as seen"
        logging.debug(msg, url)
        self.seen_urls.add(url)
        if should_traverse_url(url):
            self.process_traversable_url(page, url)

        else:
            self.process_external_url(page, url)

    def process_external_url(self, page, url):
        """Process a URL that we are not intended to search for links."""
        msg = "Will not traverse link %s; starting test for access"
        logging.debug(msg, url)
        try:
            r = requests.head(url, timeout=1.0)
            msg = "Status for %s is %d"
            logging.debug(msg, url, r.status_code)
            if is_bad(r.status_code):
                self.broken_links.add((page, url, r.status_code))
        except (RequestException, ReadTimeout):
            # We are using status code = 999 to represent any error that
            # caused the server to not return a result. More specificity
            # is possible, if desired.
            self.broken_links.add((page, url, 999))

    def process_traversable_url(self, page, url):
        """Process a URL that we are intended to search for links."""
        msg = "Trying to get %s"
        logging.debug(msg, url)
        r = requests.get(url, timeout=2.0)
        msg = "Status for %s is %d"
        logging.debug(msg, url, r.status_code)
        if is_bad(r.status_code):
            self.broken_links.add((page, url, r.status_code))
        else:
            soup = BeautifulSoup(r.content, features="lxml")
            for new_link in parse_links(soup):
                # Recursively process the new link, recording it as contents of the current URL.
                self.process(url, new_link)

    def write_results(self, out: TextIO) -> None:
        """Write the broken links to the open file 'out', in CSV format."""
        out.write("host_page,broken_url,status\n")
        for triple in self.broken_links:
            out.write(f"{triple[0]},{triple[1]},{triple[2]}\n")


if __name__ == "__main__":
    logging.basicConfig(filename="debug.log", encoding="utf-8", level=logging.DEBUG)
    app = BrokenLinkCollector()
    for item in START_URLS:
        msg = "Start processing %s"
        logging.debug(msg, item)
        app.process(item, item)
        msg = "Finished processing %s"
        logging.debug(msg, item)

    logging.debug("Finished processing all top-level URLs.")
    with open("results.csv", mode="w", encoding="utf-8") as output:
        app.write_results(output)
