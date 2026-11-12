"""Read-only HSAW option projection from a draft payload; never opens or answers a gate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import gate_proposal


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--node', required=True)
    ap.add_argument('--language', required=True)
    args = ap.parse_args()
    try:
        raw = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('GATE_PROPOSAL_TOO_LARGE')
        def pairs(rows):
            result = {}
            for key,value in rows:
                if key in result: raise ValueError('GATE_PROPOSAL_DUPLICATE_KEY')
                result[key] = value
            return result
        payload = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('GATE_PROPOSAL_NONFINITE')))
        result = gate_proposal.project(payload, node=args.node, language=args.language)
        code = 0
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        result = dict(status='REFUSED', code=str(exc), authorization=False)
        code = 1
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
