import re
from pathlib import Path

from setuptools import find_packages, setup


def get_property(prop):
    result = re.search(
        r'{}\s*=\s*[\'"]([^\'"]*)[\'"]'.format(prop),
        (Path.cwd() / "gcl" / "__init__.py").read_text(),
    )
    return result.group(1)


AUTHOR = "Alireza Behtash"
EMAIL = "proof.beh@gmail.com"
VERSION = get_property("__version__")
HERE = Path(__file__).resolve().parent

with open(str(HERE / "requirements.txt")) as reqs_file:
    reqs = reqs_file.read().splitlines()


setup(
    name="gcl",
    description="A package for scraping and parsing Google Caselaw pages.",
    url="https://github.com/StacksLaw/gcl",
    author=AUTHOR,
    author_email=EMAIL,
    maintainer=AUTHOR,
    maintainer_email=EMAIL,
    version=VERSION,
    license="MIT",
    packages=find_packages(include=["gcl"]),
    package_data={"gcl": ["data/*"]},
    install_requires=reqs,
    classifiers=[
        "Intended Audience :: Legal Industry",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Development Status :: 3 - Alpha",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
