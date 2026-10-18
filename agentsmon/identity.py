"""Conservative process-to-conversation ownership (no newest-by-directory guesses)."""
from datetime import datetime
import json
import os
from pathlib import Path
import shlex


def explicit_id(command, uuid_re):
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    for i, word in enumerate(words):
        if word in ('resume', '--resume', '--conversation', '--session-id') and i+1 < len(words):
            if uuid_re.fullmatch(words[i+1]):
                return words[i+1]
        if word.startswith(('--resume=', '--conversation=', '--session-id=')):
            value = word.split('=', 1)[1]
            if uuid_re.fullmatch(value):
                return value
    return None


def _record(path, kind, uuid_re):
    """Only inspect a bounded header, never load the full conversation."""
    try:
        with path.open(encoding='utf-8') as stream:
            for _ in range(10):
                line = stream.readline(1024*1024)
                if not line or len(line) >= 1024*1024:
                    break
                row = json.loads(line)
                data = row.get('payload', row) if kind == 'codex' else row
                sid = data.get('id') if kind == 'codex' else data.get('sessionId')
                cwd = data.get('cwd')
                stamp = data.get('timestamp') or row.get('timestamp')
                if isinstance(sid, str) and uuid_re.fullmatch(sid) and cwd and stamp:
                    return {'id':sid, 'cwd':os.path.realpath(cwd),
                            'created':datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp(),
                            'path':str(path)}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def resolve(rows, detect, now):
    """Resolve all sessions together; a candidate claimed twice stays unresolved.

    Proof order: explicit resume argv, process-held transcript/presence lock, unique
    session metadata within the first minute of a fresh process. Closely overlapping
    process starts are ambiguous (ps start-time precision is only one second).
    """
    records = {}
    for kind, root, pattern in (
        ('codex', Path(os.environ.get('CODEX_HOME', Path.home()/'.codex'))/'sessions', 'rollout-*.jsonl'),
        ('claude-code', Path.home()/'.claude/projects', '*.jsonl'),
    ):
        relevant = [r for r in rows if r['kind'] == kind]
        if not relevant:
            continue
        starts = [r['started'] for r in relevant if r['started'] is not None]
        oldest = min(starts) - 2 if starts else now
        for path in root.rglob(pattern):
            try:
                if path.stat().st_mtime < oldest and not any(r['session_id'] in str(path)
                        for r in relevant if r['session_id']):
                    continue
            except OSError:
                continue
            record = _record(path, kind, detect.UUID_RE)
            if record:
                records[(kind, record['id'])] = record
    for row in rows:
        if row['session_id'] or row['kind'] not in detect.RESUME_TEMPLATES:
            continue
        held = set(detect.open_files(row['pids']))
        if row['kind'] == 'antigravity':
            ids = {m.group(0) for f in held if '/presence/' in f and f.endswith('.lock')
                   if (m := detect.UUID_RE.search(Path(f).name))}
        else:
            ids = {rec['id'] for (kind, _), rec in records.items()
                   if kind == row['kind'] and rec['path'] in held}
        if len(ids) == 1:
            row['session_id'] = next(iter(ids))
    claimed = {(r['kind'], r['session_id']) for r in rows if r['session_id']}
    candidates = {}
    for i, row in enumerate(rows):
        start = row['started']
        if row['session_id'] or start is None or not row['cwd']:
            continue
        peers = [r for j,r in enumerate(rows) if j != i and r['kind'] == row['kind']
                 and r['cwd'] == row['cwd']]
        if any(r['started'] is None or abs(r['started']-start) <= 2 for r in peers):
            continue
        end = min([start+60] + [r['started']-2 for r in peers if r['started'] > start])
        candidates[i] = [rec['id'] for key,rec in records.items()
                         if key[0] == row['kind'] and key not in claimed
                         and rec['cwd'] == row['cwd'] and start-1 <= rec['created'] < end]
    for i, ids in candidates.items():
        if len(ids) == 1 and sum(ids[0] in other for other in candidates.values()) == 1:
            rows[i]['session_id'] = ids[0]
    for row in rows:
        sid = row['session_id']
        if sid and sum(r['kind']==row['kind'] and r['session_id']==sid for r in rows) > 1:
            row['identity_conflict'] = True
        rec = records.get((row['kind'], sid))
        row['transcript'] = rec['path'] if rec else None


def requires_pin(agent):
    if agent.get('identity_required') or agent.get('kind') in ('codex', 'claude-code', 'antigravity'):
        return True
    try:
        command = shlex.split(agent.get('restart') or '')
    except ValueError:
        return True
    return bool(command and Path(command[0]).name in ('codex','claude','agy'))


def pin_sessions(cfg, live):
    """Keep observed identities outside user config; fresh sessions become resumable."""
    from . import config, wizard
    path = config.state_dir()/'session-pins.json'
    try:
        pins = json.loads(path.read_text())
    except (OSError, ValueError):
        pins = {}
    changed = False
    for agent in cfg.get('agents', []):
        if not requires_pin(agent):
            continue
        row = next((r for r in live if r['name'] == agent['name']), None)
        if not row or not row.get('alive'):
            continue
        key = agent['name']
        if not row.get('resume_cmd'):
            changed = pins.pop(key, None) is not None or changed
            continue
        value = {'cwd':agent.get('cwd'), 'kind':row['kind'], 'id':row['session_id'],
                 'config':str(config.DEFAULT_PATH.absolute()),
                 'restart':wizard._auto_restart(row)}
        if pins.get(key) != value:
            pins[key] = value
            changed = True
    if changed:
        wizard._write_json(path, pins)
    return pins


def fresh_command(agent):
    """Remove conversation selectors from a direct CLI invocation, preserving options.

    Shell wrappers cannot be safely rewritten. Store their direct fresh invocation
    in fresh_start instead. Quote all argv again so shell syntax stays inert.
    """
    from . import wizard
    command = agent.get('fresh_start') or agent.get('restart')
    if not command:
        command = next((a['launch'] for a in wizard.AGENT_TYPES if a['kind']==agent.get('kind')), '')
        binary, _, options = command.partition(' ')
        if binary:
            command = shlex.quote(wizard.find_cli(binary) or binary)+' '+options
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    if not words or Path(words[0]).name not in ('codex', 'claude', 'agy'):
        return None
    cli = Path(words[0]).name
    selectors = {'resume', '--resume', '--conversation', '--session-id', '--fork-session', 'fork'}
    flags = {'--continue', '--last', '--all', '--pick'}
    if cli == 'claude':
        selectors.add('-r')
        flags.add('-c')
    result = [words[0]]
    i = 1
    while i < len(words):
        word = words[i]
        key = word.partition('=')[0]
        if word in {'--model', '-m', '--effort', '--profile', '--config'} or (cli=='codex' and word in {'-c','-p'}):
            result.extend(words[i:i+2])
            i += 2
            continue
        if key in selectors:
            if '=' not in word and i+1 < len(words) and not words[i+1].startswith('-'):
                i += 1
        elif key not in flags:
            result.append(word)
        i += 1
    return shlex.join(result)


def safe_restart(agent, live=None, pins=None):
    """Resume proven ownership, otherwise start fresh with a visible warning."""
    from . import config, detect, wizard
    if not requires_pin(agent):
        return agent if agent.get('restart') else None
    row = next((r for r in live or [] if r['name'] == agent['name'] and r.get('alive')), None)
    pin = (pins or {}).get(agent['name'], {})
    if pin.get('cwd') != agent.get('cwd') or pin.get('config') != str(config.DEFAULT_PATH.absolute()):
        pin = {}
    sid = row.get('session_id') if row and row.get('resume_cmd') and not row.get('identity_conflict') else (
        pin.get('id') if not row else None)
    if not isinstance(sid, str) or not detect.UUID_RE.fullmatch(sid) or any(
            r['name'] != agent['name'] and r.get('alive') and r.get('session_id') == sid for r in live or []):
        sid = None
    configured = agent.get('restart') or ''
    old = explicit_id(configured, detect.UUID_RE)
    if sid:
        if old:
            return {**agent, 'restart':configured.replace(old, sid)}
        if agent.get('fresh_start') or configured:
            fresh = fresh_command(agent)
            if fresh:
                cli = Path(shlex.split(fresh)[0]).name
                selector = {'codex':'resume', 'claude':'--resume', 'agy':'--conversation'}[cli]
                return {**agent, 'restart':fresh+' '+selector+' '+sid}
        if pin.get('restart') and explicit_id(pin['restart'], detect.UUID_RE) == sid:
            return {**agent, 'restart':pin['restart']}
        if row:
            return {**agent, 'restart':wizard._auto_restart(row)}
    fresh = fresh_command(agent)
    return {**agent, 'restart':fresh,
            'restart_warning':'Fresh conversation started: previous identity could not be verified; history was not resumed.'} if fresh else None


def record_restart(agent):
    """Persist recovery notices across supervisor/dashboard processes."""
    from . import config, wizard
    path = config.state_dir()/'restart-notices.json'
    try:
        notices = json.loads(path.read_text())
    except (OSError, ValueError):
        notices = {}
    if agent.get('restart_warning'):
        notices[agent['name']] = {'config':str(config.DEFAULT_PATH.absolute()), 'cwd':agent.get('cwd'),
                                 'warning':agent['restart_warning'], 'time':datetime.now().isoformat()}
    else:
        notices.pop(agent['name'], None)
    if not wizard._write_json(path, notices):
        raise OSError('Could not preserve the restart notice')


def restart_warnings(cfg):
    from . import config
    try:
        notices = json.loads((config.state_dir()/'restart-notices.json').read_text())
    except (OSError, ValueError):
        return {}
    return {a['name']:n['warning'] for a in cfg.get('agents', [])
            if isinstance(n := notices.get(a['name']), dict) and n.get('warning')
            and n.get('cwd') == a.get('cwd') and n.get('config') == str(config.DEFAULT_PATH.absolute())}
