# Copyright (c) 2008-2016 The pip developers (see the pip AUTHORS.txt file)
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from distutils.command.install import SCHEME_KEYS
import os
import sys

def running_under_virtualenv():
    """
    Return True if we're running inside a virtualenv, False otherwise.

    """
    if hasattr(sys, 'real_prefix'):
        return True
    elif sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return True

    return False


def distutils_scheme(dist_name, user=False, home=None, root=None,
                     isolated=False, prefix=None):
    """
    Return a distutils install scheme
    """
    from distutils.dist import Distribution

    scheme = {}

    if isolated:
        extra_dist_args = {"script_args": ["--no-user-cfg"]}
    else:
        extra_dist_args = {}
    dist_args = {'name': dist_name}
    dist_args.update(extra_dist_args)

    d = Distribution(dist_args)
    d.parse_config_files()
    i = d.get_command_obj('install', create=True)
    # NOTE: setting user or home has the side-effect of creating the home dir
    # or user base for installations during finalize_options()
    # ideally, we'd prefer a scheme class that has no side-effects.
    assert not (user and prefix), "user={0} prefix={1}".format(user, prefix)
    i.user = user or i.user
    if user:
        i.prefix = ""
    i.prefix = prefix or i.prefix
    i.home = home or i.home
    i.root = root or i.root
    i.finalize_options()
    for key in SCHEME_KEYS:
        scheme[key] = getattr(i, 'install_' + key)

    # install_lib specified in setup.cfg should install *everything*
    # into there (i.e. it takes precedence over both purelib and
    # platlib).  Note, i.install_lib is *always* set after
    # finalize_options(); we only want to override here if the user
    # has explicitly requested it hence going back to the config
    if 'install_lib' in d.get_option_dict('install'):
        scheme.update(dict(purelib=i.install_lib, platlib=i.install_lib))

    if running_under_virtualenv():
        scheme['headers'] = os.path.join(
            sys.prefix,
            'include',
            'site',
            'python' + sys.version[:3],
            dist_name,
        )

        if root is not None:
            path_no_drive = os.path.splitdrive(
                os.path.abspath(scheme["headers"]))[1]
            scheme["headers"] = os.path.join(
                root,
                path_no_drive[1:],
            )

    return scheme
