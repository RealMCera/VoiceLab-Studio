from __future__ import annotations
import json
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name('voice_catalog.json')

def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    return json.loads(CATALOG_PATH.read_text(encoding='utf-8'))

def search_catalog(q: str = '', provider: str = '', kind: str = '', access: str = '', capability: str = '') -> list[dict]:
    qn = q.strip().lower()
    out = []
    for item in load_catalog():
        if provider and item.get('provider') != provider:
            continue
        if kind and item.get('kind') != kind:
            continue
        if access and item.get('access') != access:
            continue
        if capability and capability not in item.get('capabilities', []):
            continue
        hay = ' '.join(str(item.get(k, '')) for k in ('name','provider','kind','description','notes')).lower()
        if qn and qn not in hay:
            continue
        out.append(item)
    return out
