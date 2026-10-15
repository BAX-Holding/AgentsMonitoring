"""Opt-in, account-scoped usage column. Inspired by TomasErnest's PR #8.

Read local usage/status-line snapshots only. No OAuth token reads or network
requests; never infer that all agents from one vendor share an account.
"""
from datetime import datetime
import json
import math
from pathlib import Path
import time


def epoch(value):
    if type(value) in (int,float) and math.isfinite(value): return int(value)
    if isinstance(value,str): return int(datetime.fromisoformat(value.replace('Z','+00:00')).timestamp())
    return None


def window(label, pct, reset, now):
    if type(pct) not in (int,float) or not math.isfinite(pct) or not 0<=pct<=100: return None
    reset=epoch(reset)
    if reset and reset<=now: return None
    return {'label':label,'percent':round(pct,1),
            'title':('Resets '+datetime.fromtimestamp(reset).astimezone().isoformat()) if reset else 'Reset time unavailable'}


def read_source(spec, now):
    path=Path(spec['path']).expanduser()
    kind=spec['format']
    with path.open('rb') as stream:
        if kind=='codex-rollout':
            stream.seek(max(0,stream.seek(0,2)-2_000_000))
        raw=stream.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('Oversized snapshot')
    stamp=path.stat().st_mtime
    if kind=='codex-rollout':
        data=None
        for line in reversed(raw.splitlines()):
            try: record=json.loads(line)
            except ValueError: continue
            limits=(record.get('payload') or {}).get('rate_limits')
            if limits:
                data=limits; stamp=epoch(record.get('timestamp')) or stamp; break
        if data is None: raise ValueError('No usage snapshot')
        pairs=[('5h','primary','used_percent','resets_at'),('7d','secondary','used_percent','resets_at')]
    elif kind=='claude-statusline':
        data=json.loads(raw).get('rate_limits') or {}
        pairs=[('5h','five_hour','used_percentage','resets_at'),('7d','seven_day','used_percentage','resets_at')]
    elif kind=='chatgpt-snapshot':
        data=json.loads(raw).get('rate_limit') or {}
        pairs=[('5h','primary_window','used_percent','reset_at'),('7d','secondary_window','used_percent','reset_at')]
    else: raise ValueError('Unknown usage source')
    bars=[]
    for label,key,pct,reset in pairs:
        w=data.get(key) or {}
        # Prefer reported window length, not a guessed five-hour/week label.
        minutes=w.get('window_minutes') or (w.get('limit_window_seconds') or 0)/60
        if minutes: label=(f'{minutes/1440:g}d' if minutes%1440==0 else f'{minutes/60:g}h')
        b=window(label,w.get(pct),w.get(reset),now)
        if b: bars.append(b)
    if not bars: return {'text':'No current reading','tone':'muted','title':'No unexpired usage window'}
    stale=now-stamp>600 or stamp>now+30
    return {'text':'Cached' if stale else '', 'tone':'muted' if stale else 'ok', 'bars':bars,
            'title':f"{spec.get('account','Explicit source')} · {kind} · {datetime.fromtimestamp(stamp).astimezone().isoformat()}"}


def collect(context,settings):
    sources=settings.get('sources',{})
    if not isinstance(sources,dict) or len(sources)>200: raise ValueError('Invalid usage mapping')
    patches=[]
    for identity,source in sources.items():
        try: value=read_source(source,time.time())
        except Exception: value={'text':'Unavailable','tone':'muted','title':'Usage source unavailable; account not inferred'}
        patches.append({'row_id':identity,'cells':{'limits':value}})
    return {'columns':[{'id':'limits','title':'Usage'}],'patches':patches}
