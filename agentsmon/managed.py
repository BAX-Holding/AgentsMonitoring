"""User service ownership and verified daemon actions. Never invokes sudo."""
import os
from pathlib import Path
import pwd
import re
import shlex
import signal
import subprocess
import sys
import time


def user_env():
    env = dict(os.environ)
    runtime = Path(f'/run/user/{os.getuid()}')
    if runtime.is_dir():
        env.setdefault('XDG_RUNTIME_DIR', str(runtime))
        env.setdefault('DBUS_SESSION_BUS_ADDRESS', f'unix:path={env["XDG_RUNTIME_DIR"]}/bus')
    return env


def run(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=15, env=user_env())
    except (OSError, subprocess.SubprocessError):
        return None


def properties(unit):
    if not re.fullmatch(r'[A-Za-z0-9_.@:\\-]+\.service', unit):
        return {}
    r = run(['systemctl','--user','show',unit,'--property=LoadState,ActiveState,MainPID,UnitFileState'])
    return dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line) if r and r.returncode == 0 else {}


def process_ids(spec):
    if spec.get('bridge_config'):
        from . import bridges
        return bridges.running_pids(spec)
    pattern = spec.get('pattern') or spec.get('process')
    r = run(['pgrep','-u',str(os.getuid()),'-f','--',pattern]) if pattern else None
    ids = {int(p) for p in r.stdout.split() if p.isdigit()} if r and r.returncode == 0 else set()
    # A health listener can identify wrappers with no recognizable CLI in argv.
    from urllib.parse import urlsplit
    try:
        url = urlsplit(spec.get('health_url') or '')
        if url.hostname in ('127.0.0.1','localhost','::1') and url.port:
            r = run(['lsof','-nP',f'-iTCP:{url.port}','-sTCP:LISTEN','-t'])
            for p in r.stdout.split() if r and r.returncode == 0 else []:
                uid = run(['ps','-p',p,'-o','uid=']) if p.isdigit() else None
                if uid and uid.stdout.strip() == str(os.getuid()):
                    ids.add(int(p))
    except ValueError:
        pass
    return sorted(ids)


def discover(spec):
    if spec.get('manager'):
        return spec['manager']
    if sys.platform.startswith('linux'):
        hint = spec.get('unit_hint')
        if hint and properties(hint).get('LoadState') == 'loaded':
            return {'type':'systemd','unit':hint}
        owners = set()
        for pid in process_ids(spec):
            try:
                groups = Path(f'/proc/{pid}/cgroup').read_text()
            except OSError:
                continue
            for line in groups.splitlines():
                if f'/user@{os.getuid()}.service/' in line:
                    unit = line.rsplit('/',1)[-1]
                    # The cgroup proves ownership even when the user bus is down.
                    # Never convert that outage into permission to pkill a daemon.
                    if re.fullmatch(r'[A-Za-z0-9_.@:\\-]+\.service', unit):
                        owners.add(unit)
        if len(owners) == 1:
            return {'type':'systemd','unit':owners.pop()}
        if owners:
            return {'type':'ambiguous'}
    elif sys.platform == 'darwin':
        pids = process_ids(spec)
        r = run(['launchctl','list']) if pids else None
        labels = {parts[2] for line in r.stdout.splitlines() if len(parts := line.split()) == 3
                  and parts[0].isdigit() and int(parts[0]) in pids} if r and r.returncode == 0 else set()
        if len(labels) > 1:
            return {'type':'ambiguous'}
        if len(labels) == 1:
            label = labels.pop()
            for domain in (f'gui/{os.getuid()}', f'user/{os.getuid()}'):
                target = domain+'/'+label
                status = run(['launchctl','print',target])
                if status and status.returncode == 0:
                    owner = {'type':'launchd','target':target}
                    match = re.search(r'(?m)^\s*path = (.+\.plist)\s*$', status.stdout)
                    if match:
                        owner['plist'] = match.group(1)
                    return owner
    return None


def active(owner):
    if owner.get('type') == 'systemd':
        state = properties(owner['unit']).get('ActiveState')
        return state in ('active','activating','reloading') if state else None
    if owner.get('type') == 'launchd':
        r = run(['launchctl','print',owner['target']])
        if r and r.returncode == 113:
            return False  # launchctl: service not found after bootout
        if r and r.returncode == 0:
            return bool(re.search(r'\bstate = running\b', r.stdout))
    return None


def activate(owner):
    """Called only after an explicit add/setup selection, never while probing."""
    if owner.get('type') != 'systemd':
        return True, []
    unit = owner['unit']
    r = run(['systemctl','--user','enable','--now',unit])
    if not r or r.returncode != 0:
        return False, [f'Could not enable/start {unit}; check the user systemd bus and unit.']
    notes = [f'Enabled and started user unit {unit}.']
    user = pwd.getpwuid(os.getuid()).pw_name
    r = run(['loginctl','enable-linger',user])
    if not r or r.returncode != 0:
        notes.append('Boot persistence needs an administrator to run: loginctl enable-linger '+shlex.quote(user))
    else:
        notes.append(f'Enabled lingering for {user}.')
    return True, notes


def warnings(spec):
    owner = discover(spec)
    if not owner or owner.get('type') != 'systemd':
        return []
    info = properties(owner['unit'])
    out = []
    if info.get('UnitFileState') not in ('enabled','enabled-runtime','static'):
        out.append(f'{spec["name"]}: user unit {owner["unit"]} is not enabled.')
    user = pwd.getpwuid(os.getuid()).pw_name
    r = run(['loginctl','show-user',user,'--property=Linger','--value'])
    if not r or r.returncode != 0 or r.stdout.strip() != 'yes':
        out.append(f'{spec["name"]}: lingering is not verified; administrator: loginctl enable-linger {shlex.quote(user)}')
    return out


def action(spec, verb):
    if verb not in ('stop','restart'):
        return False, 'Unsupported daemon action.'
    owner = discover(spec)
    name = spec['name']
    if owner:
        if owner.get('type') == 'systemd':
            argv = ['systemctl','--user',verb,owner['unit']]
        elif owner.get('type') == 'launchd':
            target = owner['target']
            if verb == 'stop':
                argv = ['launchctl','bootout',target]
            else:
                loaded = run(['launchctl','print',target])
                if not loaded or loaded.returncode != 0:
                    if not owner.get('plist'):
                        return False, f'{name}: launchd job is unloaded and its plist path is unknown.'
                    r = run(['launchctl','bootstrap',target.rsplit('/',1)[0],owner['plist']])
                    if not r or r.returncode != 0:
                        return False, f'{name}: launchd bootstrap failed.'
                argv = ['launchctl','kickstart','-k',target]
        else:
            return False, f'{name}: unknown service manager; refusing process kill.'
        r = run(argv)
        if not r or r.returncode != 0:
            return False, f'{name}: {verb} failed in {owner["type"]}.'
        for attempt in range(5):
            if active(owner) == (verb == 'restart'):
                return True, f'{name}: {verb} verified via {owner["type"]}.'
            if attempt < 4:
                time.sleep(0.2)
        return False, f'{name}: {verb} could not be verified.'
    if verb == 'restart':
        if not spec.get('restart'):
            return False, f'{name} has no restart command.'
        if spec.get('bridge_config') and process_ids(spec):
            ok, message = action(spec, 'stop')
            if not ok:
                return False, message
        try:
            r = subprocess.run(spec['restart'], shell=True, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return False, f'{name}: restart command failed.'
        return r.returncode == 0, f'{name}: restart command exited {r.returncode}.'
    if spec.get('bridge_config'):
        # Exact config identity includes legacy env-only/default invocations.
        # Recheck just before signalling; never use a pattern shared by all bots.
        for pid in process_ids(spec):
            try:
                if pid in process_ids(spec):
                    os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError:
                return False, f'{name}: bridge stop failed.'
        for attempt in range(10):
            if not process_ids(spec):
                return True, f'{name}: bridge process absence verified.'
            if attempt < 9:
                time.sleep(0.2)
        return False, f'{name}: bridge is still running.'
    pattern = spec.get('pattern') or spec.get('binary')
    if not pattern:
        return False, f'{name}: no scoped process selector.'
    r = run(['pkill','-u',str(os.getuid()),'-f','--',pattern])
    if not r or r.returncode not in (0,1):
        return False, f'{name}: stop command failed.'
    for attempt in range(5):
        check = run(['pgrep','-u',str(os.getuid()),'-f','--',pattern])
        if check and check.returncode == 1:
            return True, f'{name}: stopped (process absence verified).'
        if attempt < 4:
            time.sleep(0.2)
    return False, f'{name}: process remains or its absence could not be verified.'
