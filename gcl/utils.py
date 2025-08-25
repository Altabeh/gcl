import csv
import json
import re
import unicodedata
import urllib
import asyncio
import aiohttp
from ast import literal_eval
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from logging import getLogger
from multiprocessing import Pool
from os import cpu_count
from pathlib import Path
from typing import Any, Iterator, List, Tuple, Optional
from tqdm import tqdm

from dateutil import parser


logger = getLogger(__name__)

DOMAIN_FORMAT = re.compile(
    r"(?:^(\w{1,255}):(.{1,255})@|^)"  # http basic authentication [optional]
    # check full domain length to be less than or equal to 253 (starting after http basic auth, stopping before port)
    r"(?:(?:(?=\S{0,253}(?:$|:))"
    # check for at least one subdomain (maximum length per subdomain: 63 characters), dashes in between allowed
    r"((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:[a-z0-9]{1,63})))"  # check for top level domain, no dashes allowed
    r"|localhost)"  # accept also 'localhost' only
    r"(:\d{1,5})?",  # port [optional]
    re.IGNORECASE,
)
SCHEME_FORMAT = re.compile(
    r"^(http|hxxp|ftp|fxp)s?$",
    re.IGNORECASE,  # scheme: http(s) or ftp(s)
)


def generate_reporters(directory):
    """
    Generate a dictioanry of all reporters mapped to their standard format
    and sort them out based on length and save the result to
    `~/directory/reporters.json`.
    """
    from reporters_db import EDITIONS, REPORTERS

    reporters = {}

    for k, v in EDITIONS.items():
        reporters[k] = k

    for k, v in REPORTERS.items():
        for i in v:
            for x, y in i["variations"].items():
                reporters[x] = y

    new_d = {}
    for k in sorted(reporters, key=len, reverse=True):
        new_d[k] = reporters[k]

    with open(str(Path(directory) / "reporters.json"), "w") as f:
        json.dump(new_d, f, indent=4)


def rm_tree(path):
    """
    Remove file/directory under `path`.
    """
    path = Path(path)
    for child in path.glob("*"):
        if child.is_file():
            child.unlink()
        else:
            rm_tree(child)
    path.rmdir()


def load_json(path, allow_exception=False):
    """
    Load a json file and return its content.
    Set `allow_exception` to True if FileNotFound can be raised.
    """
    data = {}
    if not isinstance(path, Path):
        path = Path(path)

    if allow_exception:
        try:
            with open(path.__str__(), "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise Exception(f"{path.name} not found")

    else:
        if path.is_file():
            with open(path.__str__(), "r") as f:
                data = json.load(f)

    return data


def read_csv(path, start_row=1, end_row=None, ignore_column=[]):
    """
    Read csv file at `path` and keep the type of the element in each cell intact.

    Args
    ----
    * :param start_row: ---> int: the first row to read. Default: ignore the field names.
    * :param end_row: ---> int: the last row to read. Defaults to `None` (= last row in the csv file).
    """
    if not isinstance(path, Path):
        path = Path(path)

    with open(path.__str__(), "r", newline="") as file:
        rows = [
            list(
                map(
                    lambda r: literal_eval(r)
                    # If type(r) is either list or tuple, or dict, then preserve the type by applying
                    # ast.literal_eval().
                    if regex(r, [(r"^[\[\({].*[\]\)}]$", "")], sub=False)
                    else r,
                    # Ignore the columns in `ignore_column`.
                    [i for i in x if x.index(i) not in ignore_column],
                )
            )
            for x in csv.reader(file)
        ][start_row:]

    if not end_row:
        end_row = len(rows)

    return rows[:end_row]


def regex(item, patterns=None, sub=True, flags=None, start=0, end=None):
    """
    Apply a regex rule to find/substitute a textual pattern in the text.

    Args
    ----
    * :param item: ---> list or str: list of strings/string to apply regex to.
    * :param patterns: ---> list of tuples: regex patterns.
    * :param sub: ---> bool: switch between re.sub/re.search.
    * :param flags: ---> same as `re` flags. Defaults to `None` or `0`.
    * :param start: ---> int: start index of the input list from which applying regex begins.
    * :param end: ---> int: end index of the input list up to which applying regex continues.
    """
    if not patterns:
        raise Exception("Please enter a valid pattern e.g. [(r'\n', '')]")

    if not flags:
        flags = 0

    if item:
        for pattern, val in patterns:
            if isinstance(item, list):
                if isinstance(item[0], list):
                    if sub:
                        item = [
                            list(
                                map(
                                    lambda x: re.sub(pattern, val, x, flags=flags),
                                    group[start:end],
                                )
                            )
                            for group in item
                        ]
                    else:
                        item = [
                            list(
                                map(
                                    lambda x: re.findall(pattern, x, flags=flags),
                                    group[start:end],
                                )
                            )
                            for group in item
                        ]

                if isinstance(item[0], str):
                    if sub:
                        item = [
                            re.sub(pattern, val, el, flags=flags)
                            for el in item[start:end]
                        ]
                    else:
                        item = [
                            re.findall(pattern, el, flags=flags)
                            for el in item[start:end]
                        ]

            elif isinstance(item, str):
                if sub:
                    item = re.sub(pattern, val, item, flags=flags)
                else:
                    item = re.findall(pattern, item, flags=flags)
            else:
                continue
    return item


def create_dir(path):
    """
    Create a directory under `path`.
    """
    if isinstance(path, str):
        path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def concurrent_run(
    func: Any,
    gen_or_iter: Any,
    threading: bool = True,
    keep_order: bool = True,
    max_workers: int = None,
    disable_progress_bar: bool = False,
):
    """
    Wrap a function `func` in a multiprocessing(threading) block good for
    simultaneous I/O/CPU-bound operations.

    :param func: function to apply
    :param gen_or_iter: generator/iterator or iterable to iterate over.
    :param threading: set to True if the process is I/O-bound.
    :param keep_order: bool: if True, it sorts the results in the order of submitted tasks.
    :param max_workers: int: keeps track of how many logical cores/threads must be dedicated to the computation of the func.
    :param disable_progress_bar: if True, progress bar is not shown.
    """
    executor = (
        ThreadPoolExecutor(max_workers or 2 * cpu_count())
        if threading
        else Pool(max_workers or cpu_count())
    )
    with tqdm(
        total=len(gen_or_iter) if not isinstance(gen_or_iter, Iterator) else None,
        disable=disable_progress_bar,
    ) as pbar:
        if threading:
            if keep_order:
                results_or_tasks = executor.map(func, gen_or_iter)
                for result in results_or_tasks:
                    pbar.update(1)
                    yield result

            else:
                results_or_tasks = {executor.submit(func, item) for item in gen_or_iter}
                for f in as_completed(results_or_tasks):
                    pbar.update(1)
                    yield f.result()
            executor.shutdown()

        else:
            if keep_order:
                results_or_tasks = executor.map(func, gen_or_iter)
            else:
                results_or_tasks = executor.imap_unordered(func, gen_or_iter)

            for _ in results_or_tasks:
                pbar.update(1)
                yield _

            executor.close()
            executor.join()

    del results_or_tasks


def nullify(input_):
    if not input_:
        input_ = None
    return input_


def shorten_date(date_object):
    """
    Given a date object `date_object` of the format "Month Day, Year", abbreviate month and return date string.
    """
    date = date_object.strftime("%B %d, %Y")

    if not regex(date, [(r"May|June|July", "")], sub=False):
        date = date_object.strftime("%b. %d, %Y")

    elif "September" in date:
        date = date_object.strftime("Sept. %d, %Y")

    return date


def sort_int(string):
    """
    Sort strings based on an integer value embedded in.
    """
    return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", string)]


def deaccent(text):
    """
    Remove accentuation from the given string.
    Input text is either a unicode string or utf8 encoded bytestring.

    >>> deaccent('ůmea')
    u'umea'
    """
    result = "".join(ch for ch in normalize(text) if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", result)


def normalize(text):
    """
    Normalize text.
    """
    return unicodedata.normalize("NFD", text)


def closest_value(list_, value, none_allowed=True):
    """
    Take an unsorted list of integers and return index of the value closest to an integer.
    """
    if isinstance(value, str):
        value = int(value)
    for _index, i in enumerate(list_):
        if value > i:
            list_[_index] = value - i
    if m := min(list_):
        if none_allowed or m <= value:
            return list_.index(m)
        else:
            return


def timestamp(date_string):
    return datetime.timestamp(parser.parse(date_string))


def hyphen_to_numbers(string):
    """
    Convert a string number range with hyphen to a string of numbers.

    >>> hyphen_to_numbers('3-5')
    '3 4 5'
    """
    string_lst = list(map(lambda x: re.sub(r"^-|-$", "", x), string.split(" ")))
    final_list = []

    for x in string_lst:
        if re.search(r"\d+-\d+", x):
            lst = [
                (lambda sub: range(sub[0], sub[-1] + 1))(list(map(int, ele.split("-"))))
                for ele in x.split(", ")
            ]
            final_list += [str(b) for a in lst for b in a]
        else:
            final_list += [x.replace("-", "")]
    return " ".join(final_list)


def rm_repeated(lst: list) -> list:
    """
    Remove repeated elements of a list while keeping the order intact.
    """
    return list(dict.fromkeys(lst))


def validate_url(url: str) -> str:
    url = url.strip()

    if not url:
        raise Exception("No URL specified")

    if len(url) > 2048:
        raise Exception(
            "URL exceeds its maximum length of 2048 characters (given length={len(url)})"
        )

    result = urllib.parse.urlparse(url)
    scheme = result.scheme
    domain = result.netloc

    if not scheme:
        raise Exception("No URL scheme specified")

    if not re.fullmatch(SCHEME_FORMAT, scheme):
        raise Exception(
            f"URL scheme must either be http(s) or ftp(s) (given scheme={scheme})"
        )

    if not domain:
        raise Exception("No URL domain specified")

    if not re.fullmatch(DOMAIN_FORMAT, domain):
        raise Exception(f"URL domain malformed (domain={domain})")

    return url


class AsyncWebScraper:
    """
    Asynchronous web scraper for parallel downloads using aiohttp.
    """

    def __init__(self, max_concurrent_requests: int = 10):
        self.max_concurrent_requests = max_concurrent_requests
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

    async def _fetch_url(
        self, session: aiohttp.ClientSession, url: str
    ) -> Tuple[int, Optional[str]]:
        """
        Fetch a single URL with rate limiting.
        """
        async with self.semaphore:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        return 200, content
                    return response.status, None
            except Exception as e:
                logger.error(f"Error fetching {url}: {str(e)}")
                return 404, None

    async def fetch_urls(self, urls: List[str]) -> List[Tuple[int, Optional[str]]]:
        """
        Fetch multiple URLs concurrently.
        """
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_url(session, url) for url in urls]
            return await asyncio.gather(*tasks)

    @staticmethod
    def run_async(coro):
        """
        Run an async coroutine in a synchronous context.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
