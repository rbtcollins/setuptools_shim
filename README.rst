===============================
setuptools_shim
===============================

Abstract build system shim providing setup.py

This repository provides a shim so that projects using non-setuptools build
systems which can be built using the PEP XX [#pepxx] abstract build interface,
can be installed by older pip versions which do not implement the interface.

* Free software: Apache license
* Documentation: http://docs.openstack.org/developer/setuptools_shim
* Source: http://git.openstack.org/cgit/openstack/setuptools_shim
* Bugs: http://bugs.launchpad.net/setuptools_shim

Usage
-----

1. Copy ``shim.py`` from this project into your source tree as
   ``setup.py``

Once this is done, calling ``setup.py`` will trigger easy-install to make
``setuptools_shim`` and its dependencies as well as the bootstrap requirements
from ``pypa.json`` available at build/install time.
