"""Optional Agent2Telegram integration, keyed by config path rather than bot secrets."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys

from . import config, detect


def _path(value):
    return str(Path(value).expanduser().absolute())


def entry(config_path, python, pythonpath='', state=''):
    path = _path(config_path)
    if not os.path.isabs(python):
        raise ValueError('Bridge interpreter must be an absolute path.')
    if any('\n' in s or '\0' in s for s in (path, python, pythonpath, state)):
        raise ValueError('Bridge paths must not contain control characters.')
    tag = hashlib.sha256(path.encode()).hexdigest()[:12]
    name = 'Telegram Bridge: '+(_session_label(path) or Path(path).stem)
    argv = [python, '-m', 'agent2telegram', 'run', '--config', path]
    env = ['AGENT2TELEGRAM_CONFIG='+path]
    if pythonpath:
        env.append('PYTHONPATH='+pythonpath)
    if state:
        env.append('AGENT2TELEGRAM_STATE='+_path(state))
    log = str(config.state_dir()/('bridge-'+tag+'.log'))
    pattern = r'(^|[ /])agent2telegram run --config '+re.escape(path)+r'($|[[:space:]])'
    return {'name':name, 'pattern':pattern, 'bridge_config':path, 'enabled':True,
            'restart':'nohup '+shlex.join(['env']+env+argv)+' >> '+shlex.quote(log)+' 2>&1 &'}


CARD = 'Telegram Bridge'
LEGACY_NAME = re.compile(r'^Telegram Bridge: .+ \[[0-9a-f]{12}\]$')


def _session_label(path):
    """The bridged tmux session name (a non-secret field) for a readable title."""
    try:
        value = json.loads(Path(path).read_text('utf-8')).get('tmux_session')
    except (OSError, ValueError, AttributeError):
        return ''
    if not isinstance(value, str):
        return ''
    return ' '.join(value.split())[:60]


def process_env(pid):
    """Read only three restart fields; never log or retain the environment."""
    keys = ('PYTHONPATH','AGENT2TELEGRAM_CONFIG','AGENT2TELEGRAM_STATE')
    try:
        raw = Path(f'/proc/{pid}/environ').read_bytes()
        return {key.decode():value.decode('utf-8') for chunk in raw.split(b'\0')
                for key, sep, value in [chunk.partition(b'=')] if sep and key.decode('utf-8','ignore') in keys}
    except (OSError, UnicodeError):
        pass
    if sys.platform == 'darwin':
        r = detect._run(['ps','eww','-p',str(pid),'-o','command='])
        if r and r.returncode == 0:
            return {key:match.group(1) for key in keys if (match := re.search(
                r'(?:^| )'+key+r'=(.*?)(?= [A-Za-z_][A-Za-z0-9_]*=|$)',r.stdout.rstrip()))}
    return None


def process_info(pid, command):
    """Capture only restart-relevant nonsecret env keys, never serialize all environ."""
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    if 'agent2telegram' in words:
        i = words.index('agent2telegram')
    else:
        i = next((i for i,w in enumerate(words) if Path(w).name == 'agent2telegram'), -1)
    if i < 0 or words[i+1:i+2] != ['run']:
        return None
    # Do not mistake a shell containing a quoted command for the actual bridge.
    if Path(words[0]).name in ('sh','bash','zsh','fish'):
        return None
    env = process_env(pid)
    tail = words[i+2:]
    explicit = '--config' in tail or any(w.startswith('--config=') for w in tail)
    if env is None and not explicit:
        return None  # Unknown env-only config cannot safely be treated as default.
    env = env or {}
    cfg = env.get('AGENT2TELEGRAM_CONFIG') or str(Path.home()/'.config/agent2telegram/config.json')
    if '--config' in tail:
        index = tail.index('--config')
        if index+1 >= len(tail):
            return None
        cfg = tail[index+1]
    else:
        cfg = next((w.split('=',1)[1] for w in tail if w.startswith('--config=')), cfg)
    python = words[0] if Path(words[0]).name.startswith('python') else None
    if python and not os.path.isabs(python):
        from .wizard import find_cli
        python = find_cli(python)
    return {'config':_path(cfg), 'python':python, 'pythonpath':env.get('PYTHONPATH',''),
            'state':env.get('AGENT2TELEGRAM_STATE','')}


def processes():
    procs, _ = detect._proc_table()
    own = detect._run(['ps','-U',str(os.getuid()),'-o','pid='])
    allowed = {int(x) for x in own.stdout.split() if x.isdigit()} if own and own.returncode == 0 else set()
    return [(pid, info) for pid, cmd in procs.items() if pid in allowed
            if (info := process_info(pid, cmd))]


def running_pids(spec):
    return [pid for pid, info in processes() if info['config'] == spec['bridge_config']]


def candidates():
    found = {}
    for _, info in processes():
        if info['python']:
            item = entry(info['config'], info['python'], info['pythonpath'], info['state'])
            found[item['bridge_config']] = item
    return list(found.values())


def register(cfg, item):
    """Idempotent shared implementation for interactive add and the public CLI."""
    entries = cfg.setdefault('daemons', [])
    existing = next((d for d in entries if d.get('bridge_config') == item['bridge_config']), None)
    if item['name'] in {d.get('name') for d in entries if d is not existing}:
        # Two bridges for the same session/file name: keep them apart with the path hash.
        item = {**item, 'name':item['name']+' ['+hashlib.sha256(item['bridge_config'].encode()).hexdigest()[:12]+']'}
    if existing:
        # Preserve explicit stopped state and custom names; only automatic titles are renamed.
        keep = item['name'] if LEGACY_NAME.match(existing.get('name', '')) else existing['name']
        item = {**item, 'enabled':existing.get('enabled', True), 'name':keep}
        existing.update(item)
    else:
        entries.append(item)
    cfg['daemons'] = [d for d in entries if not (d.get('name') == 'Telegram Bridge'
                     and d.get('pattern') == 'agent2telegram run')]
    # One card for all bridges. It is up only when every enabled bridge runs, so a healthy bot
    # never hides a dead one; the detail names the missing bridge. Per-bridge cards and the
    # legacy shared card are folded into it.
    services = [s for s in cfg.get('services', [])
                if not s.get('bridge_config') and s.get('name') != 'Telegram Bridge Status']
    if not any(s.get('kind') == 'bridges' for s in services):
        services.append({'name':CARD, 'kind':'bridges'})
    cfg['services'] = services


def health(cfg):
    """(up, detail) for the shared card; None when no bridge is configured."""
    specs = [d for d in cfg.get('daemons', []) if d.get('bridge_config') and d.get('enabled', True)]
    if not specs:
        return None
    missing = [d['name'] for d in specs if not running_pids(d)]
    detail = f"{len(specs)-len(missing)}/{len(specs)} bridges running"
    if missing:
        detail += '; down: '+', '.join(missing)
    return not missing, detail


def add_noninteractive(args):
    try:
        item = entry(args.bridge_config, args.bridge_python, args.bridge_pythonpath or '', args.bridge_state or '')
        cfg = config.load()
        register(cfg, item)
        config.save(cfg)
    except (OSError, ValueError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}))
        return 1
    print(json.dumps({'ok':True,'name':item['name']}))
    return 0
