# setup.py

from pathlib import Path

from setuptools import find_packages, setup

# Read the contents of README file
this_directory = Path(__file__).parent
readme_path = this_directory / "README.md"
if not readme_path.exists():
    readme_path = this_directory / "readme.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="file-search",
    version="1.0.0",
    author="CrispStrobe",
    author_email="",
    description="File Search and Index Tool with duplicate detection",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/CrispStrobe/duplicate-finder",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: System :: Filesystems",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
    install_requires=[
        "tqdm>=4.60.0",
    ],
    entry_points={
        "console_scripts": [
            "universal-search=main:main",
        ],
    },
)
