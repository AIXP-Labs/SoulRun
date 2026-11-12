"""Bounded declaration checks, not a natural-language intent or truth oracle."""
from __future__ import annotations

import re

from .evidence_views import _absolute_path

from . import contracts as _contracts   # alpha.97 (doc 233)

RULE = _contracts.text("node.public_obligations")
_ASK = re.compile(
    r'(?:询问|请|要求|等待)用户(?:回答|答复|选择|确认|决定|提供|输入|是否)|询问用户|'
    r'\b(?:ask|request|prompt) (?:the )?user\b|\bwait for (?:the )?user (?:to |answer|reply)', re.I)
_DISPLAY = re.compile(
    r'(?:向|给)用户(?:展示|呈现|显示|输出|告知)|^(?:展示|呈现)(?!.*(?:示例代码|语法示例))|'
    r'\b(?:show|display|present|deliver)\b[^.\n]{0,180}\bto (?:the )?user\b', re.I)
_CONDITION = re.compile(r'\b(?:if|unless|when|otherwise)\b|如果|否则|如有|若|当.{0,35}(?:时|后)', re.I)
# alpha.81 (doc 170): a display verb directly followed by 时 is a manner / temporal adverbial ("呈现时保留每个单元格的引用标记": how to
# present, if presenting) - unless 时 opens a noun (展示时间线, 呈现时序图). Production: the stock module parent was rejected
# NODE_MESSAGE_REQUIRED in 5 of 5 runs for such a clause although the program calls its message optional.
_MANNER = re.compile(r'时(?![间刻段区长序效钟期限速差机态点辰事])')
_NEGATION = re.compile(r'不要|不得|禁止|无需|不必|不应|不需要|不是|不$|\b(?:not|never|without)\b', re.I)
_QUOTED = re.compile(r'"[^"\n]*"|「[^」\n]*」|“[^”\n]*”|`[^`\n]*`')
_REQUEST = re.compile(
    r'^(?:请(?:你|您)?(?:回答|选择|确认|提供|输入)|(?:你|您)?(?:是否|需要|要不要)[^\n。！？?]{0,220}[？?]|'
    r'(?:would you like|do you want|please (?:answer|choose|confirm|provide|enter))\b[^\n]*)', re.I | re.M)


def obligations(view):
    out = dict(required_steps=[], conditional_steps=[], reply_required_steps=[], reply_conditional_steps=[])
    for step in (view or {}).get('steps', []):
        text = (step.get('assert') or {}).get('work') or step.get('text') or ''
        if not isinstance(text, str):
            continue
        # ASSERT preconditions are not conditions on the work after the separator.
        if text.lstrip().startswith('[ASSERT]') and '|' in text:
            text = text.split('|', 1)[1]
        for clause in re.split(r'[。；;\n]|(?<=\.)\s+', _QUOTED.sub('', text)):
            clause = clause.strip()
            for pattern, prefix in ((_ASK, 'reply_'), (_DISPLAY, '')):
                match = pattern.search(clause)
                if not match or _NEGATION.search(clause[:match.start()]):
                    continue
                # A later "if no reply, use default" never conditions the request itself.
                is_conditional = bool(_CONDITION.search(clause[:match.start()] if prefix else clause))
                if not prefix and _MANNER.match(clause, match.end()):   # display only: requests for a human reply keep their classification
                    is_conditional = True
                key = prefix + ('conditional_steps' if is_conditional else 'required_steps')
                if step['key'] not in out[key]:
                    out[key].append(step['key'])
    return out


def public_questions(payload):
    """Direct requests only; a quoted/rhetorical question is not automatically a gate."""
    text = '\n'.join([payload.get('user_summary') or '', *(payload.get('user_messages') or [])])
    return [m.group(0).strip() for m in _REQUEST.finditer(text)]


def is_request(text) -> bool:
    """alpha.98 fix A (04 series doc 236 §7): a program text that asks the user for a reply - the detector of public_questions - is a gate
    question: never a User Message candidate, never what a literal item stands for"""
    return bool(_REQUEST.search(' '.join(str(text or '').split())))


def write_receipt(cache, payload):
    record = (cache.get('continuations') or [cache])[-1]
    observed = {_absolute_path(a.get('path')) for a in (record.get('machine') or {}).get('artifacts', []) if a.get('sha256')}
    observed.discard(None)
    return any(_absolute_path(a.get('path')) in observed and a.get('kind') == 'file'
               and str(a.get('operation') or a.get('mutation') or '').lower() in
               {'created', 'updated', 'written', 'modified', 'deleted', 'create', 'update', 'write', 'modify', 'delete'}
               for a in (payload.get('evidence') or {}).get('artifacts', []))


# alpha.93 (doc 217 / 218): user-message HINTS read from the program text - candidates only, never a verdict (the executor declares)
# alpha.95 (doc 223): the item shape in one sentence - served as user_message_shape at the head of the reply and as the first sentence of
# the instruction, because the model reads a long reply through a 2 KB preview and selective reads (doc 216, doc 223 §2)
UM_SHAPE = ("user_message.items - one per text the program gives the user: {step: this node's steps[].key that produced it (must be in "
            "steps.done), kind: content | literal, what (content); a literal may leave text out - the engine finds its step's program "
            "text in user_messages}")
UM_INSTRUCTION = (
    UM_SHAPE + ". Declare user_message in this commit. has true: user_messages carries everything this node's program gives the user - generated "
    "content in full, quoted program texts verbatim with placeholders filled - listed in items as above. has false: "
    "none_reason says why the program gives the user nothing here (empty: recorded as n/a). A conditional text whose condition did not occur goes to "
    "not_applicable as {step, reason}: the engine records that step's program text. A literal item names its step and may leave text out: the engine then "
    "finds that step's program text in user_messages itself (alpha.98); a text you do give is the program's text verbatim, placeholders "
    "filled; a description goes in what. The candidates are hints from the program text, not a verdict. "
    # alpha.96 (doc 228): one fence is one entry (production caches 10 / 11 / 13), a literal keeps its Markdown marks (caches 9 / 14)
    "With user_messages set to the @host marker the whole :::message fence is ONE entry, host:message[0]; the items are its parts, never "
    "separate messages. A literal's text is copied exactly as streamed, Markdown marks included (backticks, bold).")
_UM_VERB = re.compile(r'(?:向|给|对)用户|输出|打印|展示|呈现|显示|告知|提示|告诉|回复|给出|附加|列出|'
                      r'\b(?:output|print|show|display|present|tell|inform|reply|respond)\b', re.I)
_UM_LITERAL = re.compile("'[^'\n]{6,}'|\u300c[^\u300d\n]{6,}\u300d|\u201c[^\u201d\n]{6,}\u201d")
_UM_MACHINE = re.compile(r'JSON|json|字段|变量|传递给|传给|下一节点|下游|L0|机器|\bto the next\b|\bfield\b|\bvariable\b|stdout|文件|file|路径|缓存|cache|返回值|\boutput\.[a-z_]', re.I)
_UM_COND = re.compile(r'如果|若|如需|如要|如仍|否则|失败|无效|缺失|为空|不存在|超出|当[^，,。]{0,30}时|[^，,。]{1,30}时[，,]|\b(?:if|when|unless|otherwise|on failure)\b', re.I)
_UM_NEG = re.compile(r'不要|不得|禁止|无需|不必|不应|绝不|\b(?:never|do not|don\'t|without)\b', re.I)
_UM_PAIRS = {"'": "'", "\u300c": "\u300d", "\u201c": "\u201d"}


def _split_outside_quotes(text):
    parts, buf, closing = [], [], None
    for ch in text:
        if closing is None and ch in _UM_PAIRS:
            closing = _UM_PAIRS[ch]
        elif closing is not None and ch == closing:
            closing = None
        if closing is None and ch in '。；;\n':
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append(''.join(buf))
    return [p.strip() for p in parts if p.strip()]


def user_message_hints(view, duties=None, limit=8):
    candidates = []
    for step in (view or {}).get('steps', []):
        text = (step.get('assert') or {}).get('work') or step.get('text') or ''
        if not isinstance(text, str):
            continue
        if text.lstrip().startswith('[ASSERT]') and '|' in text:
            text = text.split('|', 1)[1]
        for clause in _split_outside_quotes(text):
            bare = _UM_LITERAL.sub('', clause)
            match = _UM_VERB.search(bare)
            if not match or _UM_NEG.search(bare[:match.start()]):
                continue
            literal = _UM_LITERAL.search(clause)
            if not literal and _UM_MACHINE.search(bare[match.start():match.end() + 25]):
                continue
            if (literal and is_request(literal.group(0)[1:-1])) or _ASK.search(bare):   # alpha.98 fix A: a question to the user is a gate
                continue
            item = {'step': step['key'], 'kind': 'literal' if literal else 'content', 'conditional': bool(_UM_COND.search(bare)),
                    'text': (literal.group(0)[1:-1] if literal else clause)[:400]}
            if item not in candidates:
                candidates.append(item)
            if len(candidates) >= limit:
                break
        if len(candidates) >= limit:
            break
    return {'required': True, 'instruction': UM_INSTRUCTION, 'public_steps': list((duties or {}).get('required_steps') or []), 'candidates': candidates}
