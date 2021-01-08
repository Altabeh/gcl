import re
import unicodedata
import urllib
from concurrent.futures import ProcessPoolExecutor as future_pool
from os import cpu_count
from pathlib import Path

from tqdm import tqdm

__all__ = [
    "create_dir",
    "multiprocess",
    "regex",
    "sort_int",
    "deaccent",
    "normalize",
    "closest_value",
    "hyphen_to_numbers",
    "remove_repeated",
    "validate_url",
]


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
    r"^(http|hxxp|ftp|fxp)s?$", re.IGNORECASE  # scheme: http(s) or ftp(s)
)


def regex(item, patterns=None, sub=True, flags=None, start=0, end=None):
    """
    Apply a regex rule to find/substitute a textual pattern in the text.

    Args
    ----
    :param item: ---> list or str: list of strings/string to apply regex to.
    :param patterns: ---> list of tuples: regex patterns.
    :param sub: ---> bool: switch between re.sub/re.search.
    :param flags: ---> same as `re` flags. Defaults to `None` or `0`.
    :param start: ---> int: start index of the input list from which applying regex begins.
    :param end: ---> int: end index of the input list up to which applying regex continues.
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


def multiprocess(func, files, yield_results=False, cpus=cpu_count()):
    """
    Wrap a function `func` in a multiprocessing block good for simultaneous I/O operations
    involving multiple number of `files`.
    Set `yield_results` to True if intend to yield results back to the caller.
    """
    with future_pool(max_workers=cpus) as p:
        for _ in tqdm(p.map(func, files), total=len(files)):
            if not yield_results:
                pass
            else:
                yield _


def sort_int(string):
    """
    Sort strings based on an integer value embdedd in.
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


def closest_value(list_, value):
    """
    Take an unsorted list of integers and return index of the value closest to an integer.
    """
    if isinstance(value, str):
        value = int(value)
    for _index, i in enumerate(list_):
        if value > i:
            list_[_index] = value - i

    return list_.index(min(list_))


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


def remove_repeated(l):
    """
    Remove repeated elements of a list while keeping the order intact.
    """
    return list(dict.fromkeys(l))


def validate_url(url: str):
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
