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

import json
import os
import subprocess
import sys
from textwrap import dedent

import fixtures
import virtualenv
from testresources import FixtureResource, ResourcedTestCase
from testtools import content, TestCase


class CapturedSubprocess(fixtures.Fixture):
    """Run a process and capture its output.

    :attr stdout: The output (a string).
    :attr stderr: The standard error (a string).
    :attr returncode: The return code of the process.

    Note that stdout and stderr are decoded from the bytestrings subprocess
    returns using error=replace.
    """

    def __init__(self, label, *args, **kwargs):
        """Create a CapturedSubprocess.

        :param label: A label for the subprocess in the test log. E.g. 'foo'.
        :param *args: The *args to pass to Popen.
        :param **kwargs: The **kwargs to pass to Popen.
        """
        super(CapturedSubprocess, self).__init__()
        self.label = label
        self.args = args
        self.kwargs = kwargs
        self.kwargs['stderr'] = subprocess.PIPE
        self.kwargs['stdin'] = subprocess.PIPE
        self.kwargs['stdout'] = subprocess.PIPE

    def setUp(self):
        super(CapturedSubprocess, self).setUp()
        proc = subprocess.Popen(*self.args, **self.kwargs)
        out, err = proc.communicate()
        self.out = out.decode('utf-8', 'replace')
        self.err = err.decode('utf-8', 'replace')
        self.addDetail(self.label + '-stdout', content.text_content(self.out))
        self.addDetail(self.label + '-stderr', content.text_content(self.err))
        self.returncode = proc.returncode
        if proc.returncode:
            raise AssertionError('Failed process %s' % proc.returncode)
        self.addCleanup(delattr, self, 'out')
        self.addCleanup(delattr, self, 'err')
        self.addCleanup(delattr, self, 'returncode')


class Venv(fixtures.Fixture):
    """Create a virtual environment for testing with.

    :attr path: The path to the environment root.
    :attr python: The path to the python binary in the environment.
    """

    def __init__(self, reason):
        """Create a Venv fixture.

        :param reason: A human readable string to bake into the venv
            file path to aid diagnostics in the case of failures.
        """
        self._reason = reason

    def _setUp(self):
        path = self.useFixture(fixtures.TempDir()).path
        virtualenv.create_environment(path, clear=True)
        python = os.path.join(path, 'bin', 'python')
        command = [
            python, '-m', 'pip', 'install', '-U', 'pip<8', 'wheel']
        self.useFixture(CapturedSubprocess(
            'mkvenv-' + self._reason, command))
        self.addCleanup(delattr, self, 'path')
        self.addCleanup(delattr, self, 'python')
        self.path = path
        self.python = python


class Repo(fixtures.Fixture):
    """A local pypi repository.

    :attr path: The path to the repo root.
    :attr url: A file:// url pointing at the path.
    """

    def _setUp(self):
        path = self.useFixture(fixtures.TempDir()).path
        self.path = path
        self.url = 'file://' + os.path.realpath(path).replace('\\', '/')


class SDistRepo(fixtures.Fixture):
    """A local repo with only sdists in it.

    :attr url: The URL to the repo.
    """

    def _setUp(self):
        self._repo = self.useFixture(Repo())
        self.url = self._repo.url
        # Perhaps use a venv to build our sdist? depending on tox to have our
        # deps is sufficient for now.
        root = os.path.join(os.path.dirname(__file__), '../../')
        target = os.path.join(self._repo.path, "setuptools_shim")
        os.mkdir(target)
        self.useFixture(CapturedSubprocess(
            "shim-sdist", ["python", "setup.py", "sdist", "-d", target], cwd=root))
        # We need the build system the project is going to use
        builder = self.useFixture(TestBuilder())
        target = os.path.join(self._repo.path, "testbuilder")
        os.mkdir(target)
        self.useFixture(CapturedSubprocess(
            "builder-sdist", ["python", "setup.py", "sdist", "-d", target],
            cwd=builder.path))
        # We need a build-requires dependency to verify that that works.
        dep = self.useFixture(TestDep())
        target = os.path.join(self._repo.path, "testdep")
        os.mkdir(target)
        self.useFixture(CapturedSubprocess(
            "dep-sdist", ["python", "setup.py", "sdist", "-d", target],
            cwd=dep.path))
        # we need pbr (as a dependency for installing setuptools_shim via
        # easy-install, though perhaps in future we should avoid it to
        # minimise room for failures by minimising dependencies).
        for dep in "pyparsing", "pbr", "six":
            target = os.path.join(self._repo.path, dep)
            os.mkdir(target)
            self.useFixture(CapturedSubprocess(
                "cache %s" % dep, ["python", "-m", "pip", "install", "-d",
                target, "--no-binary", ":all:", "--no-deps", dep]))
        target = os.path.join(self._repo.path, "packaging")
        os.mkdir(target)
        self.useFixture(CapturedSubprocess(
            "cache packaging", ["cp",
            "../packaging/dist/packaging-15.4.dev0.tar.gz", target]))
        self._index()

    def _index(self):
        # hacky hacky :/
        for subdir in os.listdir(self._repo.path):
            dirpath = self._repo.path + '/' + subdir
            index_items = []
            for fname in os.listdir(dirpath):
                index_items.append('<a href="%s">%s</a>' % (fname, fname))
            with open(dirpath + '/index.html', 'wt') as output:
                output.write(''.join(index_items))

    def reset(self):
        # We never mutate post _setUp, so reset is a no-op.
        pass


WheelRepo = SDistRepo


def mktree(root, content):
    for obj in content:
        if type(obj) is str:
            os.mkdir(os.path.join(root, obj))
        else:
            path, content = obj
            with open(os.path.join(root, path), 'wt') as output:
                output.write(content)


class TestBuilder(fixtures.Fixture):
    """A test build system for projects to be built with.

    :attr path: Path to the source tree.
    """

    def _setUp(self):
        self.path = self.useFixture(fixtures.TempDir()).path
        # Build with setuptools
        setup_py = dedent("""\
            from setuptools import setup
            setup(
                name="testbuilder",
                version="1.0",
                py_modules=["testbuilder"],
                )
            """)
        script = dedent("""\
            import base64
            from hashlib import sha256
            import json
            import sys
            import zipfile
            from textwrap import dedent
            if sys.argv[1:] == ['metadata']:
                import testdep
                print(dedent('''\
                    Metadata-Version: 2.0
                    Name: test
                    Version: 1.0.0
                    Author: foo
                    Author-email: bar
                    License: UNKNOWN
                    Platform: UNKNOWN
                    Provides-Extra: extra
                    Requires-Dist: extra; extra == 'extra'
                    Requires-Dist: nothing; extra == ''
                    Requires-Dist: testdep
                    ''').lstrip())
            elif sys.argv[1:] == ['build_requires']:
                print json.dumps({'build_requires':['testdep']})
            elif sys.argv[1:] == ['develop']:
                with open("develop-done", "wt"):
                    pass
            elif sys.argv[1] == 'wheel':
                # Write a wheel with one trivial file.
                name = 'test-1.0-py2.py3-none-any.whl'
                if sys.argv[2:]:
                    assert sys.argv[2] == '-d'
                    name = sys.argv[3] + '/' + name
                f = zipfile.ZipFile(name, 'w')
                hashes = {}
                def add(name, data):
                    f.writestr(name, data)
                    hash = sha256(data).digest()
                    hashes[name] = (base64.urlsafe_b64encode(hash).rstrip(b'='), len(data))
                add('wheelinstalled.py', b'')
                add('test-1.0.dist-info/METADATA', dedent('''\
                    Metadata-Version: 2.0
                    Name: test
                    Version: 1.0
                    Summary: UNKNOWN
                    Home-page: UNKNOWN
                    Author: UNKNOWN
                    Author-email: UNKNOWN
                    License: UNKNOWN
                    Platform: UNKNOWN
                    
                    UNKNOWN
                    
                    ''').encode('utf8').lstrip())
                add('test-1.0.dist-info/WHEEL', dedent('''\
                    Wheel-Version: 1.0
                    Generator: bdist_wheel (0.26.0)
                    Root-Is-Purelib: true
                    Tag: py2-none-any
                    ''').encode('utf8').lstrip())
                record = b'\\n'.join(
                    b'%s,sha256=%s,%s' % (name, meta[0], meta[1]) for
                    (name, meta) in hashes.items())
                record += '\\ntest-1.0.dist-info/RECORD,,\\n'
                add('test-1.0.dist-info/RECORD', record)
                f.close()
            else:
                sys.exit(1)
            sys.exit(0)
            """)
        mktree(self.path, [
            ('setup.py', setup_py),
            ('testbuilder.py', script),
            ])


class TestDep(fixtures.Fixture):
    """A noddy dependency for use as a build-dependency.

    :attr path: Path to the source tree.
    """

    def _setUp(self):
        self.path = self.useFixture(fixtures.TempDir()).path
        # Build with setuptools
        setup_py = dedent("""\
            from setuptools import setup
            setup(
                name="testdep",
                version="1.0",
                py_modules=["testdep"],
                )
            """)
        script = ""
        mktree(self.path, [
            ('setup.py', setup_py),
            ('testdep.py', script),
            ])


class TestProject(fixtures.Fixture):
    """A project for testing with.

    :attr path: The path to the project.
    """

    def _setUp(self):
        self.path = self.useFixture(fixtures.TempDir()).path
        # pypa.json
        build_config = {
            'bootstrap_requires': ["testbuilder"],
            'build_command': ["{PYTHON}", "-m", "testbuilder"]}
        root = os.path.join(os.path.dirname(__file__), '../../')
        with open(os.path.join(root, 'setuptools_shim/shim.py'), 'rt') as f:
            setup_py = f.read()
        mktree(self.path, [
            ('pypa.json', json.dumps(build_config, ensure_ascii=False)),
            ('setup.py', setup_py),
            ])


def configure_mirror(repo, venv):
    """Configure venv to install things from repo."""
    # XXX: windows uses no dot, but this is only test code.
    pydistutils_path = os.path.join(venv.path, ".pydistutils.cfg")
    with open(pydistutils_path, "wt") as output:
        output.write(dedent("""\
            [easy_install]
            index-url=%s
            """ % (repo.url[7:],)))
    # And here pip changes the name too :/
    pip_conf_path = os.path.join(venv.path, "pip.conf")
    with open(pip_conf_path, "wt") as output:
        output.write(dedent("""\
            [global]
            index-url = %s
            """ % (repo.url,)))


class TestSetuptools_shim(ResourcedTestCase, TestCase):

    resources = [
        # create a virtualenv with pip< 8 (so we get a version that is known
        # not to support the abstract build system.
        ("venv", FixtureResource(Venv("test"))),
        # put this code tree into local repos
        ("sdistrepo", FixtureResource(SDistRepo())),
        ("wheelrepo", FixtureResource(WheelRepo())),
        ]

    def test_pip_7_develop_install(self):
        # configure setuptools to use a private repo
        # and disable the real index
        configure_mirror(self.sdistrepo, self.venv)
        # create a project on disk that uses it
        project = self.useFixture(TestProject())
        # do a develop install via pip
        self.useFixture(CapturedSubprocess('develop install',
            [self.venv.python, '-m', 'pip', 'install', '-e', project.path,
            '-vvv']))
        # check that develop was called:
        with open(project.path + '/develop-done', 'rt'):
            pass

    def test_pip_7_install(self):
        # Using pip 7 install without wheels
        # configure setuptools to use a private repo
        # and disable the real index
        configure_mirror(self.sdistrepo, self.venv)
        # create a project on disk that uses it
        project = self.useFixture(TestProject())
        # do an install via pip --no-binary :all:
        # this will need to thunk through to wheel and install that wheel
        # itself.
        self.useFixture(CapturedSubprocess('source install',
            [self.venv.python, '-m', 'pip', 'install', '--no-binary', ':all:',
             project.path, '-vvv']))
        # check that it was installed.
        path = self.venv.path + '/lib/python%s.%s/site-packages/wheelinstalled.py' % sys.version_info[:2]
        with open(path, 'rt'):
            pass

    def test_pip_7_wheel(self):
        # Using pip 7 install to build a wheel
        # configure setuptools to use a private repo
        # and disable the real index
        configure_mirror(self.sdistrepo, self.venv)
        # create a project on disk that uses it
        project = self.useFixture(TestProject())
        # A place to put the wheel we build.
        wheelhouse = project.path + '/wheels'
        os.mkdir(wheelhouse)
        self.useFixture(CapturedSubprocess('pip wheel',
            [self.venv.python, '-m', 'pip', 'wheel', project.path, '-vvv',
             '-w', wheelhouse]))
        # Install the wheel
        self.useFixture(CapturedSubprocess('wheel install',
            [self.venv.python, '-m', 'pip', 'install', 'test', '-vvv', '-f',
             wheelhouse]))
        # check that it was installed.
        path = self.venv.path + '/lib/python%s.%s/site-packages/wheelinstalled.py' % sys.version_info[:2]
        with open(path, 'rt'):
            pass
