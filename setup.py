from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gcl",
    version="1.3.3",
    author="Alireza Behtash",
    description="Google Case Law and Patent Parser",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/alirezabehtash/gcl",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8,<3.13",
    install_requires=[
        "beautifulsoup4>=4.12.2",
        "lxml>=4.9.0",
        "requests>=2.31.0",
        "selenium>=4.0.0",
        "tqdm>=4.66.4",
        "python-dateutil>=2.8.2",
        "reporters-db>=3.2.56",
        "webdriver-manager>=3.5.4",
        "pyyaml>=6.0.1",
    ],
    package_data={
        "gcl": ["data/*.json"],
    },
)
