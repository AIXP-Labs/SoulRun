"""Immutable menu versions beside the existing current-menu entry."""
import re
from .run_store import RunStore, RunStoreError, sha256_bytes


def version_name(store, name, text=None):
    from .dispatch_lifecycle import replacement_accounting
    if not re.fullmatch(r'menu\.[A-Za-z0-9_.-]+\.txt', name) or not store.exists() \
            or not replacement_accounting(store.read_json(store.index_path)):
        return None
    if text is None and not store.exists_path(store.public_dir/name):
        return None
    raw = text.encode('utf-8') if text is not None else store.read_bytes(store.public_dir/name)
    return name[:-4]+'.'+sha256_bytes(raw)+'.txt'


def preserve(store, name, text):
    snapshot = version_name(store, name, text)
    if not snapshot:
        return None
    path = store.public_dir/snapshot
    if store.exists_path(path):
        if store.read_bytes(path) != text.encode('utf-8'):
            raise RunStoreError('PUBLIC_SNAPSHOT_CONFLICT', 'Immutable menu evidence differs; preserve and stop.')
    else:
        store.write_text_once(path, text)
    return path


def ref(cache_dir, name):
    from . import render
    store = RunStore(cache_dir)
    snapshot = version_name(store, name)
    if snapshot and store.exists_path(store.public_dir/snapshot):
        name = snapshot
    return render.ref_line(store.cache_dir.name, name)


def current_refs(cache_dir, name):
    from . import render
    store = RunStore(cache_dir)
    legacy = render.ref_line(store.cache_dir.name, name)
    snapshot = version_name(store, name)
    if not snapshot:
        return (legacy,)
    path = store.public_dir/snapshot
    if not store.exists_path(path) or store.read_bytes(path) != store.read_bytes(store.public_dir/name):
        raise RunStoreError('PUBLIC_SNAPSHOT_CONFLICT', 'Current menu snapshot is missing or differs; preserve and stop.')
    refs = (render.ref_line(store.cache_dir.name, snapshot),)
    versions = tuple(store.public_dir.glob(name[:-4]+'.'+'?'*64+'.txt'))
    return refs+(legacy,) if len(versions) == 1 else refs
