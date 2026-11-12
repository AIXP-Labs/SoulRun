"""Final-answer structure, not a semantic truth oracle. No model or network calls."""
from __future__ import annotations

import copy
from functools import lru_cache

from . import schema_lite

from . import contracts as _contracts   # alpha.97 (doc 233)

CONTENT_FIELDS = ('key_data', 'comparisons', 'conditions_limits_risks', 'follow_up')
REASONING_RULE = _contracts.text("final-answer.reasoning")
LEGACY_SYNTHESIS_RULE = _contracts.joined(_contracts.text("execute-report.legacy_synthesis"), REASONING_RULE)   # alpha.100: one text, as before

EXECUTION_REPORT_RULE = _contracts.text("execute-report.execution_report")
REFERENCE_RULE = _contracts.text("final-answer.reference")
ANSWER_STREAM_RULE = _contracts.text("final-answer.answer_stream")
SYNTHESIS_RULE = _contracts.joined(_contracts.text("final-answer.synthesis"), REASONING_RULE)   # alpha.100: one text, as before


def _object(properties, required=None):
    return dict(type='object', additionalProperties=False, properties=properties,
                required=list(properties) if required is None else required)


@lru_cache(maxsize=1)
def artifact_schema():
    """Single source for the readable artifact schema and commit's model-input projection."""
    string = dict(type='string', minLength=1)
    strings = dict(type='array', items=string)
    identity = dict(node=string, visit=dict(type='integer', minimum=1))
    excerpt = dict(type='string', minLength=1, pattern=r'\S')
    detail = _object(dict(text=string, answer_excerpt=excerpt, source_nodes=dict(strings, uniqueItems=True)))
    coverage = _object(dict(identity, answer_excerpt=excerpt))
    details = _object(dict(coverage=dict(type='array', items={'$ref': '#/$defs/coverage'}),
                           request_summary=string,
                           **{key: dict(type='array', minItems=1, items={'$ref': '#/$defs/detail'}) for key in CONTENT_FIELDS}),
                      ['coverage'])
    record = _object(dict(source_ref=string, source_sha256=dict(type=['string', 'null']),
                          kind=string, record=dict(type=['object', 'string'])))
    container = _object(dict(record_state={'enum': ['records_present', 'none_recorded', 'not_applicable', 'unknown']},
                             items=dict(type='array', items={'$ref': '#/$defs/record'}),
                             checked_scopes=dict(strings, minItems=1), unobserved_scopes=strings))
    container['oneOf'] = [
        dict(properties=dict(record_state={'const': 'records_present'}, items=dict(minItems=1))),
        dict(properties=dict(record_state={'enum': ['none_recorded', 'not_applicable']}, items=dict(maxItems=0))),
        dict(properties=dict(record_state={'const': 'unknown'}, unobserved_scopes=dict(minItems=1))),
    ]
    association = _object(dict(identity, source_ref=string, source_sha256=string,
                               association={'enum': ['excerpt_present', 'not_assessed']},
                               answer_excerpt=dict(type=['string', 'null'])))
    association['oneOf'] = [
        dict(properties=dict(association={'const': 'excerpt_present'}, answer_excerpt=excerpt)),
        dict(properties=dict(association={'const': 'not_assessed'}, answer_excerpt={'type': 'null'})),
    ]
    properties = dict(schema_version={'const': 1}, user_language=string, answer=excerpt,
                      main_node_coverage=dict(type='array', items={'$ref': '#/$defs/association'}),
                      **{key: {'$ref': '#/$defs/records'} for key in
                         ('evidence', 'exceptions', 'human_decisions', 'artifacts_changes')})
    required = list(properties)
    properties.update({key: value for key, value in details['properties'].items() if key != 'coverage'})
    return dict(_object(properties, required), **{
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:soulbot:final-answer:1',
        'description': 'Engine-assembled final artifact. Presence and excerpts do not prove semantic truth or completeness.',
        '$defs': dict(detail=detail, coverage=coverage, details=details, record=record,
                      records=container, association=association),
    })


def input_projection():
    spec = artifact_schema()
    return copy.deepcopy(spec['$defs']['details']), {
        key: copy.deepcopy(spec['$defs'][key]) for key in ('detail', 'coverage')}


def validate_details(details, answer, main_nodes, source_nodes):
    if details is None:
        return
    spec = artifact_schema()
    errors = schema_lite.validate(details, spec['$defs']['details'], root=spec)
    if errors:
        raise ValueError(str(errors[0]))
    actual = [(row['node'], row['visit']) for row in details['coverage']]
    expected = [(row['node'], row['visit']) for row in main_nodes]
    if actual != expected:
        raise ValueError(f'coverage must match actual main occurrences in order: {expected!r}')
    for row in details['coverage'] + [item for key in CONTENT_FIELDS for item in details.get(key, [])]:
        if not row['answer_excerpt'].strip() or row['answer_excerpt'] not in answer:
            raise ValueError('answer_excerpt must occur verbatim in the complete business answer')
        if not set(row.get('source_nodes', [])) <= set(source_nodes):
            raise ValueError('source_nodes must identify actual committed nodes, not planned or invented nodes')


def records(items, checked, unobserved=()):
    return dict(record_state='records_present' if items else 'none_recorded', items=items,
                checked_scopes=list(checked), unobserved_scopes=list(unobserved))


def assemble(text, language, basis, details):
    associations = (details or {}).get('coverage', [])
    covered = {(row['node'], row['visit']): row['answer_excerpt'] for row in associations}
    result = dict(schema_version=1, user_language=language, answer=text, main_node_coverage=[])
    for row in basis['main_nodes']:
        excerpt = covered.get((row['node'], row['visit']))
        result['main_node_coverage'].append(dict(row, answer_excerpt=excerpt,
                                                association='excerpt_present' if excerpt else 'not_assessed'))
    result.update({key: basis[key] for key in ('evidence', 'exceptions', 'human_decisions', 'artifacts_changes')})
    result.update({key: value for key, value in (details or {}).items() if key != 'coverage'})
    errors = schema_lite.validate(result, artifact_schema())
    if errors:
        raise ValueError(str(errors[0]))
    return result
