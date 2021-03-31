from setuptools import setup, find_packages
import re
from pathlib import Path

def get_property(prop):
    result = re.search(
        r'{}\s*=\s*[\'"]([^\'"]*)[\'"]'.format(prop),
        (Path(__file__) / "gcl" / "__init__.py").read_text(),
    )
    return result.group(1)


setup(
    name="gcl",
    description="A package for scraping and parsing Google Caselaw pages",
    url="https://github.com/StacksLaw/gcl",
    author="Alireza Behtash",
    author_email="proof.beh@gmail.com",
    version=get_property("__version__"),
    license="MIT",
    packages=find_packages(include=["gcl"]),
    package_data={"gcl": ["data/*"]},
    install_requires=[
        "bs4>=0.0.1",
        "requests>=2.25.1",
        "tqdm>=4.54.1",
        "reporters-db>=2.0.5",
        "pathos>=0.2.7",
        "stem>=1.8.0",
        "lxml>=4.6.2",
        "selenium>=3.141.0",
        "python-anticaptcha>=0.7.1",
        "python-dateutil>=2.8.1",
    ],
    classifiers=[
        "Intended Audience :: Commercial/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)