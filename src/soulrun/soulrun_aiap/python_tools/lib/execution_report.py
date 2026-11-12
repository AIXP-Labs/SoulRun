"""Machine-owned summary and content-addressed complete execution report."""
from .run_store import sha256_bytes, atomic_write_bytes, read_bytes


def describe(summary, full_text, cache_name, node, visit, language):
    digest = sha256_bytes(full_text.encode('utf-8'))
    title = '完整执行报告（原文）' if str(language).startswith('zh') else 'Complete execution report (original)'
    link = f'[{title}](engine-report:{cache_name}/{node}@{visit}/{digest})'
    return dict(schema_version=1, node=node, visit=visit, cache=cache_name,
                summary=summary, summary_sha256=sha256_bytes(summary.encode('utf-8')),
                full_sha256=digest, full_bytes=len(full_text.encode('utf-8')),
                file=f'_reports/sha256-{digest}.txt', display=summary+'\n\n'+link)


def materialize(store, meta, full_text):
    path = store.cache_dir/meta['file']
    if path.resolve().parent != store.cache_dir/'_reports' or path.is_symlink():
        raise ValueError('Execution report path escaped its cache')
    data = full_text.encode('utf-8')
    if sha256_bytes(data) != meta['full_sha256']:
        raise ValueError('Execution report digest changed')
    if path.exists():
        if read_bytes(path) != data:
            raise ValueError('Existing execution report differs; never overwrite it')
    else:
        atomic_write_bytes(path,data)


def verify(meta, full_text, cache_name, node, visit):
    summary = meta.get('summary')
    if not isinstance(summary, str):
        raise ValueError('Execution report summary is absent')
    if (meta.get('node'), meta.get('visit'), meta.get('cache')) != (node, visit, cache_name):
        raise ValueError('Execution report identity changed')
    if meta.get('summary_sha256') != sha256_bytes(summary.encode('utf-8')) or meta.get('full_sha256') != sha256_bytes(full_text.encode('utf-8')):
        raise ValueError('Execution report projection digest changed')
    link = f'(engine-report:{cache_name}/{node}@{visit}/{meta["full_sha256"]})'
    display = meta.get('display')
    if not isinstance(display, str) or not display.startswith(summary+'\n\n[') or not display.endswith(link):
        raise ValueError('Execution report display changed')
    return display
