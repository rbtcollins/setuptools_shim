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

from fixtures import Fixture

from testtools import TestCase

class TestSetuptools_shim(TestCase):

    resources = []

    def test_pip_7_develop_install(self):
        pass
        # create a virtualenv
        # install pip 7 (so we get a version that is known not to support the
        # abstract build system.
        # configure setuptools to use a private repo
        # and disable the real index
        # put this code tree into a local index
        # create a project on disk that uses it
        # do a develop install via pip
        # check the project is importable

    def test_pip_7_install(self):
        pass

    def test_pip_7_wheel(self):
        pass
