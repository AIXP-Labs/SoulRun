"""Opt-in same-node error routing, bounded by committed Engine revisit events."""

MODE = 'bounded_self_retry'
RECOVERABLE = frozenset(('timeout', 'parse_error', 'io_error'))


def policy_error(reserved, name):
    policy = reserved.get('retry_policy')
    if not isinstance(policy, dict) or policy.get('mode') != MODE:
        return None
    routes = reserved.get('on_error')
    if (set(policy) != {'mode', 'max_retries'} or type(policy.get('max_retries')) is not int
            or not 0 <= policy['max_retries'] <= 3 or not isinstance(routes, dict) or not routes
            or any(key not in RECOVERABLE or target != name for key, target in routes.items())):
        return 'bounded_self_retry requires max_retries integer 0..3 and explicit recoverable self routes only'
    return None


def allowed(reserved, payload, index, entry):
    policy = reserved.get('retry_policy')
    if not isinstance(policy, dict) or policy.get('mode') != MODE:
        return True
    if payload.get('error_type') not in RECOVERABLE or not index or not entry:
        return False
    if policy_error(reserved, entry.get('node') or entry['name']):
        return False
    current = index['current']
    frame = next((row for row in reversed(index.get('call_stack', []))
                  if row['parent'] == entry.get('parent')), None) if entry.get('parent') else None
    if entry.get('parent') and frame is None:
        return False
    parent = frame['parent'] if frame else None
    parent_visit = frame['parent_visit'] if frame else None
    visit, count = current['visit'], 0
    for event in reversed(index.get('revisit_events', [])):
        if (event.get('target') != entry['name'] or event.get('target_visit') != visit
                or event.get('parent') != parent or event.get('parent_visit') != parent_visit):
            continue
        if event.get('reason') != 'error_route' or event.get('source') != entry['name']:
            break
        source_visit = event.get('source_visit')
        if type(source_visit) is not int or source_visit >= visit:
            return False
        count += 1
        visit = source_visit
    return count < policy['max_retries']
