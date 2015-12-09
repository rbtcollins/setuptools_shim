# A setup.py for projects using non-setuptools build systems.
# This adapts pypa.json to present a sufficiently compatible setuptools
# interface that pip versions before support for pypa.json was added can still
# install packages. To use, copy this file into a source tree as setup.py.

import sys

from setuptools import setup

if __name__ == '__main__':
    orig_args = sys.argv
    sys_path = list(sys.path)
    sys.argv = ['setup.py', 'test']
    setup(name="stage1", setup_requires=["setuptools_shim"])
    from setuptools_shim import main
    sys.exit(main.main(orig_args, sys_path))
