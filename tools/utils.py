import re
import unicodedata
from pathlib import Path
from subprocess import PIPE, CalledProcessError, Popen, check_output
import urllib

__all__ = ['pdf_to_text', 'get_page_count',
           'sort_int', 'deaccent', 'normalize',
           'closest_value', 'hyphen_to_numbers',
           'remove_repeated', 'validate_url']


DOMAIN_FORMAT = re.compile(
    r'(?:^(\w{1,255}):(.{1,255})@|^)' # http basic authentication [optional]
    r'(?:(?:(?=\S{0,253}(?:$|:))' # check full domain length to be less than or equal to 253 (starting after http basic auth, stopping before port)
    r'((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+' # check for at least one subdomain (maximum length per subdomain: 63 characters), dashes in between allowed
    r'(?:[a-z0-9]{1,63})))' # check for top level domain, no dashes allowed
    r'|localhost)' # accept also 'localhost' only
    r'(:\d{1,5})?', # port [optional]
    re.IGNORECASE
)
SCHEME_FORMAT = re.compile(
    r'^(http|hxxp|ftp|fxp)s?$', # scheme: http(s) or ftp(s)
    re.IGNORECASE
)

def pdf_to_text(pdf_path, target_dir):
    """
    Convert pdf at `pdf_path` to a txt file in `target_dir` using xpdf.
    """
    file_name = Path(pdf_path).stem
    command = ["pdftotext", "-layout", pdf_path,
               str(Path(target_dir) / f'{file_name}.txt')]
    proc = Popen(
        command, stdout=PIPE, stderr=PIPE)
    proc.wait()
    (stdout, stderr) = proc.communicate()
    if proc.returncode:
        return stderr
    return ''


def get_page_count(pdf_path):
    """
    Use xpdf's pdfinfo to extract the number of pages in a pdf file.
    """
    try:
        output = check_output(["pdfinfo", pdf_path]).decode()
        pages_line = [line for line in output.splitlines()
                      if "Pages:" in line][0]
        num_pages = int(pages_line.split(":")[1])
        return num_pages

    except (CalledProcessError, UnicodeDecodeError):
        return 0


def sort_int(string):
    """
    Sort strings based on an integer value embdedd in.
    """
    return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', string)]


def deaccent(text):
    """
    Remove accentuation from the given string. 
    Input text is either a unicode string or utf8 encoded bytestring.

    >>> deaccent('ůmea')
    u'umea'
    """
    result = ''.join(ch for ch in normalize(
        text) if unicodedata.category(ch) != 'Mn')
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
    string_lst = list(map(lambda x : re.sub(r'^-|-$', '', x), string.split(' ')))
    final_list = []

    for x in string_lst:
        if re.search(r'\d+-\d+', x):
            lst = [(lambda sub: range(sub[0], sub[-1] + 1))
                   (list(map(int, ele.split('-')))) for ele in x.split(', ')]
            final_list += [str(b) for a in lst for b in a]
        else:
            final_list += [x.replace('-', '')]
    return ' '.join(final_list)

def remove_repeated(l):
    """
    Remove repeated elements of a list while keeping the order intact.
    """
    return list(dict.fromkeys(l))


def validate_url(url: str):
    url = url.strip()

    if not url:
        raise Exception('No URL specified')

    if len(url) > 2048:
        raise Exception('URL exceeds its maximum length of 2048 characters (given length={len(url)})')

    result = urllib.parse.urlparse(url)
    scheme = result.scheme
    domain = result.netloc

    if not scheme:
        raise Exception('No URL scheme specified')

    if not re.fullmatch(SCHEME_FORMAT, scheme):
        raise Exception(f'URL scheme must either be http(s) or ftp(s) (given scheme={scheme})')

    if not domain:
        raise Exception('No URL domain specified')

    if not re.fullmatch(DOMAIN_FORMAT, domain):
        raise Exception(f'URL domain malformed (domain={domain})')

    return url
