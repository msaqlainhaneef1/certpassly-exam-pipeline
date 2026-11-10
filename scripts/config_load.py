"""Load pipeline config (YAML or JSON). Owner-specific values live in config, not in code."""
from __future__ import annotations
import json, os, re
from paths import root, skill_root

def _unescape_dq(s):
    out=[]; i=0
    while i<len(s):
        if s[i]=='\\' and i+1<len(s):
            n=s[i+1]
            out.append({'n':'\n','t':'\t','r':'\r','"':'"',"'":"'",'\\':'\\'}.get(n,n))
            i+=2; continue
        out.append(s[i]); i+=1
    return ''.join(out)

def _parse_scalar(s):
    s=s.strip()
    if s in ('null','~','Null'): return None
    if s in ('true','True'): return True
    if s in ('false','False'): return False
    if re.fullmatch(r'-?\d+',s): return int(s)
    if re.fullmatch(r'-?\d+\.\d+',s): return float(s)
    if s.startswith('"') and s.endswith('"') and len(s)>=2:
        return _unescape_dq(s[1:-1])
    if s.startswith("'") and s.endswith("'") and len(s)>=2:
        return s[1:-1]
    return s

def _parse_simple_yaml(text):
    """Minimal YAML subset: maps, lists, scalars, list-of-maps, | and > blocks. No tags or anchors."""
    raw_lines=text.splitlines()
    def clean(line):
        in_s=None; out=[]
        i=0
        while i<len(line):
            c=line[i]
            if in_s:
                out.append(c)
                if c==in_s and (i==0 or line[i-1]!='\\'): in_s=None
                i+=1; continue
            if c in ('"',"'"): in_s=c; out.append(c); i+=1; continue
            if c=='#' and (i==0 or line[i-1].isspace()): break
            out.append(c); i+=1
        return ''.join(out).rstrip()
    tokens=[]
    for line in raw_lines:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        c=clean(line)
        if not c.strip():
            continue
        indent=len(line)-len(line.lstrip(' '))
        tokens.append((indent,c.strip()))
    def peek_indent(idx):
        return tokens[idx][0] if idx<len(tokens) else -1
    def parse_block(idx, min_indent):
        if idx>=len(tokens) or tokens[idx][0]<min_indent:
            return None, idx
        ind=tokens[idx][0]
        if tokens[idx][1].startswith('- '):
            return parse_list(idx, ind)
        return parse_map(idx, ind)
    def parse_list(idx, ind):
        items=[]
        while idx<len(tokens) and tokens[idx][0]==ind and tokens[idx][1].startswith('- '):
            val=tokens[idx][1][2:].strip()
            idx+=1
            if val=='' or val in ('|','>'):
                if val in ('|','>'):
                    block,idx=read_block(idx, ind, val=='|'); items.append(block)
                elif idx<len(tokens) and tokens[idx][0]>ind:
                    child,idx=parse_block(idx, ind+1); items.append(child)
                else:
                    items.append(None)
                continue
            if val.endswith(':') and not val.startswith(('"','\'')) and val not in ('|','>'):
                key=_parse_scalar(val[:-1].strip())
                if idx<len(tokens) and tokens[idx][0]>ind:
                    child,idx=parse_block(idx, ind+1)
                    item={key:child}
                    # more keys of this list item
                    item,idx=fill_map(item, idx, ind)
                    items.append(item)
                else:
                    items.append({key:None})
                continue
            if ':' in val and not val.startswith(('{','[','"',"'")):
                k,v=val.split(':',1)
                item={_parse_scalar(k.strip()): (_parse_scalar(v.strip()) if v.strip() else None)}
                item,idx=fill_map(item, idx, ind)
                items.append(item)
                continue
            items.append(_parse_scalar(val))
        return items, idx
    def fill_map(item, idx, parent_dash_indent):
        # subsequent keys for a list-of-map item are indented further than the dash
        while idx<len(tokens) and tokens[idx][0]>parent_dash_indent and not tokens[idx][1].startswith('- '):
            s=tokens[idx][1]; kind_indent=tokens[idx][0]
            if ':' not in s: raise ValueError('expected key: '+s)
            key,rest=s.split(':',1); key=key.strip(); rest=rest.strip(); idx+=1
            if rest in ('|','>'):
                item[key],idx=read_block(idx, kind_indent, rest=='|')
            elif rest=='':
                if idx<len(tokens) and tokens[idx][0]>kind_indent:
                    item[key],idx=parse_block(idx, kind_indent+1)
                else:
                    item[key]=None
            else:
                item[key]=_parse_scalar(rest)
        return item, idx
    def parse_map(idx, ind):
        mapping={}
        while idx<len(tokens) and tokens[idx][0]==ind and not tokens[idx][1].startswith('- '):
            s=tokens[idx][1]
            if ':' not in s: raise ValueError('expected key: '+s)
            key,rest=s.split(':',1); key=key.strip(); rest=rest.strip(); idx+=1
            if rest in ('|','>'):
                mapping[key],idx=read_block(idx, ind, rest=='|')
            elif rest=='':
                if idx<len(tokens) and tokens[idx][0]>ind:
                    mapping[key],idx=parse_block(idx, ind+1)
                else:
                    mapping[key]=None
            else:
                mapping[key]=_parse_scalar(rest)
        return mapping, idx
    def read_block(idx, parent_indent, keep_newlines):
        lines=[]
        while idx<len(tokens) and tokens[idx][0]>parent_indent:
            lines.append(tokens[idx][1]); idx+=1
        text='\n'.join(lines) if keep_newlines else ' '.join(lines)
        return text, idx
    if not tokens:
        return {}
    doc,idx=parse_block(0,0)
    if idx!=len(tokens):
        raise ValueError('unparsed yaml starting at: '+tokens[idx][1])
    return doc


def _deep(d, *keys, default=None):
    cur=d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur: return default
        cur=cur[k]
    return cur

def find_config(explicit=None):
    if explicit and os.path.exists(explicit): return os.path.abspath(explicit)
    env=os.environ.get('CERTPASSLY_CONFIG')
    if env and os.path.exists(env): return os.path.abspath(env)
    for name in ('pipeline.yaml','pipeline.yml','pipeline.json','site.json'):
        p=os.path.join(root(),'config',name)
        if os.path.exists(p): return p
    example=os.path.join(skill_root(),'config','pipeline.example.yaml')
    if os.path.exists(example): return example
    raise SystemExit('No pipeline config found. Copy config/pipeline.example.yaml to <workspace>/config/pipeline.yaml and set brand, disclaimer and banned terms.')

def load(explicit=None):
    path=find_config(explicit)
    text=open(path,encoding='utf-8').read()
    if path.endswith('.json'):
        cfg=json.loads(text)
    else:
        cfg=_parse_simple_yaml(text)
    cfg['_config_path']=path
    return cfg
