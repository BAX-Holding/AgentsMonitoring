#!/usr/bin/env python3
"""Maintainer release step. Print the reviewed package manifest, do not self-heal it."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentsmon import __version__
from agentsmon.integrity import package_hashes

parser = argparse.ArgumentParser()
parser.add_argument('--release', required=True, help='Reviewed tag/candidate identifier')
args = parser.parse_args()
files = package_hashes(Path(__file__).resolve().parents[1] / 'agentsmon')
print(json.dumps({'version': __version__, 'release': args.release, 'files': files,
                  'content_id': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()},
                 sort_keys=True, indent=2))
