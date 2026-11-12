"""Append-only diagnostic framing; it never supplies recovery authority."""
import hashlib
import json


def rows(raw):
    lines=raw.splitlines(keepends=True)
    result=[]
    offset=0
    for n,line in enumerate(lines):
        try:
            item=json.loads(line)
        except json.JSONDecodeError as exc:
            tail=n==len(lines)-1 and not line.endswith((b'\n',b'\r'))
            incomplete=exc.pos>=len(exc.doc.rstrip()) or exc.msg.startswith('Unterminated string')
            if tail and incomplete:
                return result,dict(verification='UNVERIFIABLE',offset=offset,bytes=len(line),
                    tail_sha256=hashlib.sha256(line).hexdigest(),cause='UNDETERMINED',
                    recovery_authorized=False,business_result_not_replayed=True)
            raise
        result.append(item)
        offset+=len(line)
    return result,None
