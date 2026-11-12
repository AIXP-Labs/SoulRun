"""Reject ambiguous decoded Windows paths; never rewrite a human decision."""
import re
ROOT=re.compile(r'\b[A-Za-z]:(?:[\a\b\f\t\v]|\r(?!\n))(?=[A-Za-z0-9_.-])|\b[A-Za-z]:\r?\n(?=[A-Za-z0-9_.-]+(?:\\|[\a\b\f\t\v]))')
TAIL=re.compile(r'\b[A-Za-z]:\\[^\n\r]*[\a\b\f\t\v](?=[A-Za-z0-9_.-])|\b[A-Za-z]:\\[^\n\r]*\r(?!\n)(?=[A-Za-z0-9_.-])')
AMBIGUOUS=re.compile(r'\b[A-Za-z]:\\[^\n\r]*\r?\n(?=[A-Za-z0-9_.-]+\\)')

def diagnostics(payload):
    notes=[]
    validate(payload,notes,reject_gate=False)
    return notes

def validate(payload,notes=None,*,reject_gate=True):
    from .engine_core import EngineError
    def check(value,field):
        if isinstance(value,str) and (ROOT.search(value) or TAIL.search(value)):
            message='Windows path text contains decoded control characters; use forward slashes or JSON-escaped backslashes. Original text is not rewritten.'
            if reject_gate and (field=='gate' or field.startswith('gate.')):
                raise EngineError('PUBLIC_PATH_CONTROL_CHARACTER',message+' No gate was accepted.',
                    field=field,expected='unambiguous path text; legitimate paragraph breaks remain unchanged',example='C:/work/targets')
            if notes is not None:notes.append(dict(code='PUBLIC_PATH_CONTROL_CHARACTER',text=message,field=field))
        elif isinstance(value,str) and AMBIGUOUS.search(value) and notes is not None:
            notes.append(dict(code='PUBLIC_PATH_TEXT_AMBIGUOUS', field=field,
                text='Path-like text crosses a line boundary; verify the original field. No path was rewritten or confirmed.'))
        if isinstance(value,dict):
            for k,v in value.items():check(v,f'{field}.{k}')
        elif isinstance(value,list):
            for n,v in enumerate(value):check(v,f'{field}[{n}]')
    for key in ('gate','user_summary','user_messages'):
        if key in payload:check(payload[key],key)
