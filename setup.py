import codecs
import inosync
from os import path
from setuptools import setup, find_packages


def long_description():
    filespath = path.dirname(path.realpath(__file__))
    with codecs.open(path.join(filespath, 'README.rst'), encoding='utf8') as f:
        return f.read()

setup(
    name='inosync',
    version=inosync.__version__,
    packages=find_packages(),
    description=inosync.__description__,
    long_description=long_description(),
    classifiers=inosync.__classifiers__,
    keywords=inosync.__keywords__,
    author=inosync.__author__,
    author_email=inosync.__author_email__,
    url=inosync.__url__,
    license=inosync.__licence__,
    entry_points={
        'console_scripts': [
            'inosync=inosync.lib.runner:start'
        ],
    },
    zip_safe=True,
)
