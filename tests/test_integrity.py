import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from agentsmon import __version__,integrity


class IntegrityTests(unittest.TestCase):
    def test_missing_manifest_is_unknown_and_modified_added_missing_files_are_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);code=p/'a.py';code.write_text('a=1\n')
            self.assertEqual(integrity.status(p)['state'],'unverified')
            files=integrity.package_hashes(p)
            manifest={'version':__version__,'release':'fixture','files':files,
                      'content_id':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()}
            (p/'core-manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(integrity.status(p)['state'],'clean')
            code.write_text('a=2\n');self.assertEqual(integrity.status(p)['state'],'modified')
            code.write_text('a=1\n');extra=p/'extra.css';extra.write_text('body{}\n')
            self.assertEqual(integrity.status(p)['state'],'modified')
            extra.unlink();code.unlink();self.assertEqual(integrity.status(p)['state'],'modified')
