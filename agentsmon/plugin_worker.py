"""Private process boundary. Plugins never import inside the dashboard process."""
import contextlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys


def main():
    request=json.loads(sys.stdin.buffer.read(1024*1024+1))
    target=request['target']
    # Core modules and installed entry points are resolved in this worker only.
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    with contextlib.redirect_stdout(sys.stderr):
        if target['type']=='file':
            path=Path(target['path'])
            sys.path.insert(0,str(path.parent))
            spec=importlib.util.spec_from_file_location('agentsmon_extension',path)
            module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        else:
            name,_,attr=target['value'].partition(':')
            module=importlib.import_module(name)
            if attr: module=getattr(module,attr)
        method=request['method']
        if method not in ('collect','action'): raise ValueError('Unknown method')
        result=getattr(module,method)(request['context'],request['settings'])
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':
    try: main()
    except BaseException:
        # Do not disclose plugin exception bodies (may contain tokens/config).
        sys.exit(1)
