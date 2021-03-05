import json
import re
import unicodedata
import urllib
from concurrent.futures import ProcessPoolExecutor as future_pool
from concurrent.futures import ThreadPoolExecutor as thread_future_pool
from datetime import datetime
from os import cpu_count, environ
from pathlib import Path
from time import sleep

import requests
from dateutil import parser
from pathos.multiprocessing import ProcessPool as pool
from pathos.threading import ThreadPool as thread_pool
from python_anticaptcha import AnticaptchaClient, NoCaptchaTaskProxylessTask
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from stem import Signal
from stem.control import Controller
from tqdm import tqdm

__all__ = [
    "rm_tree",
    "generate_reporters",
    "load_json",
    "create_dir",
    "multi_run",
    "regex",
    "nullify",
    "shorten_date",
    "sort_int",
    "deaccent",
    "normalize",
    "closest_value",
    "hyphen_to_numbers",
    "rm_repeated",
    "validate_url",
    "switch_ip",
    "proxy_browser",
    "recaptcha_process",
    "async_get",
    "get",
]

SELENIUM_OPTIONS = webdriver.ChromeOptions()
SELENIUM_OPTIONS.add_argument("headless")
SELENIUM_DRIVER = webdriver.Chrome(options=SELENIUM_OPTIONS)


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


def multi_run(
    func, files, threading=False, yield_results=False, cpus=cpu_count(), pathos=False
):
    """
    Wrap a function `func` in a multiprocessing(threading) block good for simultaneous I/O/CPU-bound
    operations involving multiple number of `files`. Set `yield_results` to True if the function intends
    to yield results back to the caller. Use `pathos` to implement dill backend that is useful
    for parallelizing nested and lambda functions.
    """

    if pathos:
        if threading:
            p = thread_pool(cpus)
        else:
            p = pool(cpus)
        for _ in tqdm(p.imap(func, files), total=len(files)):
            pass

        p.close()
        p.join()

    else:
        if threading:
            p = thread_future_pool(cpus)
        else:
            p = future_pool(cpus)

        for _ in tqdm(p.map(func, files), total=len(files)):
            if not yield_results:
                pass
            else:
                yield _


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


def rm_repeated(l):
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


def switch_ip():
    """
    Signal TOR for a new connection.
    """
    with Controller.from_port(port=9051) as controller:
        controller.authenticate()
        controller.signal(Signal.NEWNYM)


def proxy_browser(host="127.0.0.1", port=9050, proxy_type=1):
    """
    Get a new selenium webdriver with tor as the proxy.
    """
    fp = webdriver.FirefoxProfile()
    # Direct = 0, Manual = 1, PAC = 2, AUTODETECT = 4, SYSTEM = 5
    fp.set_preference("network.proxy.type", proxy_type)
    fp.set_preference("network.proxy.socks", host)
    fp.set_preference("network.proxy.socks_port", int(port))
    fp.update_preferences()
    options = Options()
    options.headless = True
    return webdriver.Firefox(options=options, firefox_profile=fp)


def _recaptcha_get_token(url, site_key, invisible=False):
    """
    Enter a `url` and a valid `site_key` to call https://anticaptcha.com API to solve
    the recaptcha encountered at the url. The response is a token soon to be used
    for verification purposes.

    Args
    ----
    :param invisible: ---> bool: If True, calls the invisible recaptcha api.
    """
    task = NoCaptchaTaskProxylessTask(
        website_url=url, website_key=site_key, is_invisible=invisible
    )

    ANTICAPTCHA_KEY = environ.get("ANTICAPTCHA_KEY", None)

    if ANTICAPTCHA_KEY:
        client = AnticaptchaClient(ANTICAPTCHA_KEY)
        job = client.createTask(task)
        job.join(maximum_time=60 * 15)
        return job.get_solution_response()

    raise Exception("ANTICAPTCHA_KEY could not be found in the python env.")


def _recaptcha_form_submit(driver, token):
    """
    Submit the recaptcha form with a valid `token`.
    """
    driver.execute_script(
        "document.getElementById('g-recaptcha-response').innerHTML='{}';".format(token)
    )
    driver.execute_script("gs_captcha_cb('{}')".format(token))
    sleep(1)


def recaptcha_process(url, driver):
    """
    Wait for a recaptcha-success message to show up in DOM after receiving
    the correct token from the anticaptcha servers and submitting the recaptcha form.
    """
    driver.get(url)
    site_key = regex(
        driver.find_element(By.TAG_NAME, "iframe").get_attribute("src"),
        [(r"&k=(.*?)&", "")],
        sub=False,
    )[0]
    token = _recaptcha_get_token(url, site_key)
    _recaptcha_form_submit(driver, token)
    return driver.find_element_by_class_name("recaptcha-success").text


def async_get(url, xpath):
    """
    Interactive selenium driver for active javascript execution that would
    be required in the websites that follow an AJAX call for search functionality.

    Args
    ----
    :param xpath: ---> str: wait for the element with xpath `xpath` to appear in DOM
                            to get the page content.
    """
    SELENIUM_DRIVER.get(url)
    try:
        WebDriverWait(SELENIUM_DRIVER, 10).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
    finally:
        r = SELENIUM_DRIVER.page_source
        return r


def get(url, json=False):
    """
    Request to make a get request to a given `url`.
    """
    res_content = ""
    response = requests.get(url)
    response.encoding = response.apparent_encoding
    status = response.status_code

    if status == 200:
        res_content = response.text
        if json:
            res_content = response.json()

    if status == 404:
        print(f'URL "{url}" not found')

    if status not in [200, 404]:
        raise Exception(f"Server response: {status}")
    return status, res_content
