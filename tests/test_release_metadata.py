"""Release metadata and installation instructions must agree with the CLI."""
import json
from pathlib import Path
import re
import unittest

from agentsmon import __version__, config

ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadata(unittest.TestCase):
    def test_module_example_is_generic_english(self):
        self.assertIn('name=VPN status,', config._module_header.__doc__)

    def test_metadata_matches_current_release(self):
        project = (ROOT / 'pyproject.toml').read_text()
        version = re.search(r'^version = "([^"]+)"', project, re.MULTILINE).group(1)
        manifest = json.loads((ROOT / 'agentsmon/core-manifest.json').read_text())
        self.assertEqual(version, __version__)
        self.assertEqual(manifest['version'], __version__)
        self.assertTrue(manifest['release'].startswith('v' + __version__))
        self.assertIn('## ' + __version__ + ' ', (ROOT / 'CHANGELOG.md').read_text())

    def test_install_docs_describe_supported_platforms_and_actions(self):
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('Ubuntu 22.04 / 24.04', readme)
        self.assertIn('macOS', readme)
        self.assertIn('brew install', readme)
        self.assertIn('apt-get install', readme)
        self.assertNotIn('dashboard has no auth', readme)
        self.assertNotIn('dashboard is **read-only**', readme)
        self.assertIn('restart/stop actions', readme)
