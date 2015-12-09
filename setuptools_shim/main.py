# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import email.parser
import os
import json
import shutil
import subprocess
import sys
import tempfile

from setuptools import setup
from packaging.requirements import Requirement
from pkg_resources import DistInfoDistribution, PathMetadata, DEVELOP_DIST

def main(argv, orig_path):
    """CLI entry point for setuptools_shim.

    This maps:
     - egg_info into a metadata query + setuptools egg info creation
     - develop into a call to the build system develop api
     - wheel into a call to the build system wheel api
     - install into a call to the build system wheel api + a call to
       pip to install the resulting wheel - this is recursive and thus may not
       work when pip learns to lock environments, but the build system
       interface support in pip should land first, so this code will never be
       executed then.

    Direct reference dependencies are not yet supported.
    """
    # step 1, read pypa config
    build = AbstractBuildSystem('.')
    # step 2, install bootstrap requires and build requires
    _prepare_build_env(build, orig_path)
    # step 3, do the requested command
    if argv[1] == "egg_info":
        return _egg_info(build, argv)
    elif argv[1] == "develop":
        return _develop(build, argv)
    else:
        raise Exception("Unknown command in %r" % (argv,))


def _new_pythonpath(orig_path):
    # Add the new things added to the path by setup_requires to PYTHONPATH
    new_elements = sys.path[len(orig_path):]
    env_path = os.environ.get('PYTHONPATH', "")
    if env_path:
        new_env = os.pathsep.join([env_path] + new_elements) 
    else:
        new_env = os.pathsep.join(new_elements)
    return new_env


def _prepare_build_env(build, orig_path):
    # step 2, install bootstrap requires so we can invoke the actual build
    # system.
    if build.bootstrap_requires:
        sys.argv = ['setup.py', 'test']
        setup(name="stage2", setup_requires=build.bootstrap_requires)
    build.force_pythonpath(_new_pythonpath(orig_path))
    build_deps = build.build_requires()
    active_deps = []
    for dep in build_deps:
        if dep._url:
            raise Exception(
                "Direct reference dependencies not supported. %r" % (dep,))
        if not dep._marker or dep._marker.evaluate():
            spec = dep._specifier or ''
            extras = ('[%s]' % dep._extras) if dep._extras else ''
            active_deps.append("%s%s%s" % (dep._name, extras, spec))
    setup(name="stage3", setup_requires=active_deps)
    build.force_pythonpath(_new_pythonpath(orig_path))


def _egg_info(build, argv):
    metadata = build.metadata()
    # Reconstruct setuptools kwargs from the metadata.
    # We don't try to preserve markers: if a wheel is being built, the actual
    # build system is responsible; our only job is to generate a plausible
    # egg-info so that pip can consume it to determine dependencies for
    # right-here, right-now.
    # We need to emit extras however, since we don't know which ones the
    # calling pip will decide on.
    install_requires_set = set(str(r) for r in metadata.requires())
    extras = {}
    for extra in metadata.extras:
        extra_reqs_set = set(str(r) for r in metadata.requires([extra]))
        extra_reqs = [str(r) for r in (extra_reqs_set - install_requires_set)]
        extras[extra] = extra_reqs
    install_requires = [str(r) for r in install_requires_set]
    sys.argv = argv
    setup(
        name=metadata.project_name,
        version=metadata.version,
        extras_require=extras,
        install_requires=install_requires)
    return 0


def _develop(build, argv):
    # Seen pip command lines:
    # develop --no-deps
    # TODO: parse and translate --prefix and or --root parameters.
    build.develop()
    

class AbstractBuildSystem(object):
    """The PEP XXX abstract build system.
    
    :attr root: The base directory of the package source dir.
    """

    def __init__(self, path):
        """Construct an AbstractBuildSystem for a path.
        
        :param path: The root directory of the source for the package.
        """
        self.root = path
        with open(os.path.join(self.root, 'pypa.json'), 'rt') as source:
            self._pypa = json.loads(source.read())
        self._cmd_prefix = [
            x.format(PYTHON=sys.executable)
            for x in self._pypa['build_command']]
        self._pythonpath = self._sentinel = object()

    def force_pythonpath(self, pythonpath):
        """Force PYTHONPATH to some specific value.

        Useful when sys.path has been dynamically modified.

        :param pythonpath: optional override for PYTHONPATH. Set to None to
            unset PYTHONPATH entirely
        """
        self._pythonpath = pythonpath

    @property
    def bootstrap_requires(self):
        return self._pypa.get('bootstrap_requires', [])

    def build_requires(self):
        dependency_json_bytes = self._run_command(['build_requires'])
        dependency_json = dependency_json_bytes.decode('utf-8')
        dependencies = json.loads(dependency_json)
        result = []
        for dep in dependencies['build_requires']:
            result.append(Requirement(dep))
        return result

    def develop(self, prefix=None, root=None):
        command = ['develop']
        if prefix is not None:
            command.extend(['--prefix', prefix])
        if root is not None:
            command.extend(['--root', root])
        self._run_command(command, stdout=None)

    def metadata(self):
        metadata_bytes = self._metadata_bytes()
        return self._parse_metadata_bytes(metadata_bytes)

    def _parse_metadata_bytes(self, metadata_bytes):
        # Make a temp wheel on disk. (Ugh, aiee, etc, but lets us avoid
        # reimplementing much of pkg_resources while still having its
        # normalisation etc.
        tempdir = tempfile.mkdtemp()
        metadata_path = os.path.join(tempdir, 'METADATA')
        with open(metadata_path, 'wb') as output:
            output.write(metadata_bytes)
        if sys.version_info < ('3',):
            metadata_str = metadata_bytes.decode('utf-8')
        else:
            metadata_str = metadata_bytes
        try:
            # Try not to poke too deeply into pkg_resources implementation.
            metadata = PathMetadata(tempdir, tempdir)
            pkg_info = email.parser.Parser().parsestr(metadata_str)
            dist = DistInfoDistribution(
                tempdir, metadata, project_name=pkg_info.get('Name'),
                version=pkg_info.get('Version'),
                py_version=None, platform=None,
                precedence=DEVELOP_DIST)
            # cache the metadata before we delete the temp file on disk.
            dist.requires()
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)
        return dist

    def _metadata_bytes(self):
        return self._run_command(['metadata'])

    def _run_command(self, command, stdout=subprocess.PIPE):
        cmd = self._cmd_prefix + command
        proc_env = os.environ.copy()
        os.environ['PYTHON'] = sys.executable
        if self._pythonpath is not self._sentinel:
            if self._pythonpath is None:
                proc_env.pop('PYTHONPATH', None)
            else:
                proc_env['PYTHONPATH'] = self._pythonpath
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.root, stdout=stdout,
                stdin=subprocess.PIPE, env=proc_env)
        except OSError as err:
            raise Exception("%r failed, %r" % (cmd, err))
        out, _ = proc.communicate()
        retcode = proc.poll()
        if retcode:
            raise Exception("%r failed, got %r" % (cmd, out))
        return out
