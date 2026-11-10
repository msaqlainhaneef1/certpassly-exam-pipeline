"""Workspace and skill paths. No hardcoded exam codes or repo paths.

Resolution order for the workspace root:
  1. paths.set_root(...) or CERTPASSLY_ROOT
  2. --root DIR on the command line (stripped from sys.argv)
  3. current working directory

Never fall back to a box checkout or a GitHub path.
"""
from __future__ import annotations
import os, sys, datetime

_ROOT=None

def skill_root():
    """Directory that holds SKILL.md, reference/, config/ and shared/.

    Resolution order:
      1. CERTPASSLY_SKILL_ROOT
      2. Walk up from this file looking for SKILL.md or reference/site-format
         (git clone, zip, or pip install -e .)
      3. Packaged data next to this module (non-editable pip install, if bundled)
    --help works even when this folder is missing; running stages needs 1 or 2.
    """
    env=os.environ.get('CERTPASSLY_SKILL_ROOT')
    if env and os.path.isdir(env):
        return os.path.abspath(env)
    here=os.path.abspath(__file__)
    d=os.path.dirname(here)
    for _ in range(10):
        if os.path.isfile(os.path.join(d,'SKILL.md')) or os.path.isdir(os.path.join(d,'reference','site-format')):
            return d
        parent=os.path.dirname(d)
        if parent==d:
            break
        d=parent
    pkg=os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(pkg,'data'), os.path.join(pkg,'_data')):
        if os.path.isdir(os.path.join(cand,'reference','site-format')):
            return os.path.abspath(cand)
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

def set_root(path):
    global _ROOT
    _ROOT=os.path.abspath(path)
    os.environ['CERTPASSLY_ROOT']=_ROOT
    return _ROOT

def consume_cli_root(argv=None):
    """Pull --root DIR out of argv so older scripts can keep using sys.argv[1]."""
    argv=list(sys.argv if argv is None else argv)
    out=[argv[0]] if argv else [sys.argv[0]]
    i=1
    root=None
    while i<len(argv):
        if argv[i] in ('--root','--workspace') and i+1<len(argv):
            root=argv[i+1]; i+=2; continue
        if argv[i].startswith('--root='):
            root=argv[i].split('=',1)[1]; i+=1; continue
        out.append(argv[i]); i+=1
    if root: set_root(root)
    if argv is None: sys.argv[:]=out
    return out, root

def root():
    if _ROOT: return _ROOT
    env=os.environ.get('CERTPASSLY_ROOT')
    if env: return os.path.abspath(env)
    return os.getcwd()

def today():
    return os.environ.get('CERTPASSLY_DATE') or datetime.date.today().isoformat()

def now_label():
    """Timestamp in Asia/Karachi, labelled."""
    try:
        from zoneinfo import ZoneInfo
        t=datetime.datetime.now(ZoneInfo('Asia/Karachi'))
    except Exception:
        t=datetime.datetime.now()
    return t.strftime('%Y-%m-%d %H:%M')+' (Asia/Karachi)'

def site_format_version(cfg=None):
    if cfg and cfg.get('site_format_version'): return str(cfg['site_format_version'])
    return os.environ.get('CERTPASSLY_SITE_FORMAT','v1')

def site_format_dir(version=None):
    v=version or site_format_version()
    d=os.path.join(skill_root(),'reference','site-format',v)
    if not os.path.isdir(d):
        raise SystemExit(f'site-format {v} not found at {d}. Add that folder or change site_format_version in config.')
    return d

def csv_template_dir(version=None):
    return os.path.join(site_format_dir(version),'csv_templates')

# Consume --root early when imported as a library by a CLI script.
if any(a=='--root' or a.startswith('--root=') or a=='--workspace' for a in sys.argv[1:]):
    consume_cli_root()
