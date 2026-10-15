"""Package-content integrity, not a signature or proof of publisher identity."""
import hashlib
import json
from pathlib import Path
from . import __version__


def package_hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and
            '__pycache__' not in p.parts and p.name!='core-manifest.json' and p.suffix not in ('.pyc','.pyo')}


def status(root=None):
    root=Path(root) if root else Path(__file__).parent
    result={'version':__version__,'state':'unverified','release':None,'content_id':None}
    try:
        manifest=json.loads((root/'core-manifest.json').read_text())
        actual=package_hashes(root)
        result.update(release=manifest['release'],content_id=manifest['content_id'])
        canonical=hashlib.sha256(json.dumps(manifest['files'],sort_keys=True).encode()).hexdigest()
        result['state']='clean' if actual==manifest['files'] and canonical==manifest['content_id'] and manifest['version']==__version__ else 'modified'
    except (OSError,ValueError,KeyError,TypeError): pass
    return result
