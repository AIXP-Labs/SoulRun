"""Public block rendering for v7 (A mode text; B mode reads the same data from _public/).

Every block is derived from machine fields plus the model's user_summary; the model never
composes these blocks (doc 01 v0.2 §6). Own implementation.

alpha.23 (04 series doc 45, user 2026-09-11 「继续增强 web 渲染 … 详细参考 v6.25.0」): the block shapes follow the
v6.25.0 render_contract.json where a v7 equivalent exists -
  * public_emission_protocol.boundary_guard: every public block is framed by the five-dot guard  ·····  with one
    blank line between guard and body (opening "·····\\n\\n", closing "\\n\\n·····");
  * business_next_node_plan: the nine-line PLAN with the User_Language / Thought_Output_MUST_USE lines;
  * business_node_info: the eight-part node info (separator, Node State with status glyph, For Audit, User Message,
    Report, Explain, Axiom Governance, End Separator); engine nodes use the engine_self ═══ [engine] frame;
  * substep_receipt: ┈┈┈ [sub k] … ┈┈┈ / body / tc | status | sha (alpha.94: **User Message:** / **Report:** when the sub node has a message);
  * robot_block (human_output_v5): every human-facing block (final answer, gate menu, run-ended report) starts with 🤖 and closes with the guard and the footer
    "🍁 <localized AI disclosure>  ⚓ Align Axiom 0: Human Sovereignty and Wellbeing · HSAW.dev".
Python renders from the committed cache only; it never rewrites the model's text.
"""
from __future__ import annotations

import re
import json
import html

AXIOM_LINE = "Align Axiom 0: Human Sovereignty and Wellbeing · HSAW.dev"   # alpha.27: signed, no period (doc 52 §5 / doc 53)
AXIOM_BARE = AXIOM_LINE
AXIOM_MARK = "⚓" + AXIOM_LINE   # alpha.27 R2: the one fixed line every block keeps
REF_OPEN, REF_CLOSE = "⟦engine:", "⟧"


def ref_line(cache_name: str, name: str) -> str:
    """alpha.27 R1 (doc 53): the one-line reference the model presents instead of a public block; the host expands it
    from .execution_cache/<cache>/_public/<name>. The cache name makes it resolvable across the runs of a session."""
    return f"{REF_OPEN}{cache_name}/{name}{REF_CLOSE}"
GUARD = "·····"                          # five U+00B7 (v6 boundary_guard)
NODE_RULE = "━━━━━━━━━━"                 # v6 business_node_info separator (ten U+2501)
ENGINE_RULE = "═══"                      # v6 engine_self opening/closing frame
SUB_RULE = "┈┈┈"                         # v6 substep_receipt frame
ROBOT = "🤖"
_CJK_RE = re.compile(r"[㐀-鿿぀-ヿ가-힯]")
_LATIN_RE = re.compile(r"[A-Za-z]")

LANGUAGE_LABEL = {"zh": "中文", "en": "English", "ja": "日本語", "ko": "한국어"}
# v6 ai_disclosure_map (short phrases used on the human_output_v5 footer line)
AI_DISCLOSURE_SHORT = {"zh": "AI生成内容", "en": "AI-generated content", "ja": "AI生成コンテンツ", "ko": "AI 생성 콘텐츠"}
# alpha.28 GA (doc 57 §7): every gate menu carries an explanation and a non-binding advice line, labelled in the user's language
GATE_LABELS = {"zh": {"explanation": "说明", "advice": "建议"}, "en": {"explanation": "Explanation", "advice": "Advice"},
               "ja": {"explanation": "説明", "advice": "提案"}, "ko": {"explanation": "설명", "advice": "제안"}}
STATUS_GLYPH = {"COMMITTED": "✓ COMMITTED", "PASS": "✓ PASS", "DEGRADED": "◐ DEGRADED", "FAILED": "✗ FAILED", "FAIL": "✗ FAIL",
                "WAITING_USER": "⏸ WAITING_USER", "PARTIAL": "PARTIAL", "ABANDONED": "ABANDONED"}


_DETECTION_STRIP = (
    re.compile(r"https?://\S+"),                                   # URLs
    re.compile(r"`[^`\n]*`"),                                      # inline code spans
    re.compile(r"\b[A-Za-z]:[\\/][^\s，。；、：！？（）]*"),           # Windows paths (stop at CJK punctuation)
    re.compile(r"(?<![\w])/(?:[\w.\-]+/)+[\w.\-]*"),               # POSIX paths
    re.compile(r"\b[A-Za-z0-9]+(?:[_.\-][A-Za-z0-9]+)+\b"),        # identifiers / file names: a_b, a.b, a-b, 0.1.0
)


def _detection_view(text: str) -> str:
    """A2a (32 号 r2): the language anchor is read from a derived view with URLs, paths, code spans and
    identifiers removed. The authoritative user_message is never modified; only the ratio input changes."""
    view = text
    for pattern in _DETECTION_STRIP:
        view = pattern.sub(" ", view)
    return view


def _classify_language(text: str) -> str | None:
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if cjk == 0 and latin == 0:
        return None
    if cjk > 0 and cjk * 2 >= latin:
        kana = len(re.findall(r"[぀-ヿ]", text))
        hangul = len(re.findall(r"[가-힯]", text))
        if hangul * 2 >= cjk:
            return "ko"
        return "ja" if kana * 2 >= cjk else "zh"
    return "en"


def detect_language(text: str | None) -> str | None:
    """Coarse first-message language anchor: 'zh' when CJK dominates, 'en' for Latin, else None.

    The ratio is computed on the detection view (technical tokens removed) so that a Chinese request that
    quotes paths or package identifiers is not diluted into 'en'. When the view carries no letters at all
    (pure path / code input) the raw text decides, exactly as before."""
    if not text:
        return None
    return _classify_language(_detection_view(text)) or _classify_language(text)


PLAN_ACTION_MAX = 320   # alpha.25 (doc 47 item 4): the PLAN carries the node's step text nearly whole


def _one_line(text: str, limit: int = 120) -> str:
    s = " ".join((text or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def language_label(user_language: str | None) -> str:
    return LANGUAGE_LABEL.get(user_language or "", LANGUAGE_LABEL["en"])


def disclosure_short(user_language: str | None) -> str:
    return AI_DISCLOSURE_SHORT.get(user_language or "", AI_DISCLOSURE_SHORT["en"])


def footer_line(user_language: str | None) -> str:
    """Disclosure marker only; real warnings and committed body text remain untouched."""
    return f"🍁{disclosure_short(user_language)} ⚓{AXIOM_LINE}"


def frame(body: str) -> str:
    """v6 envelope: guard, blank line, body, blank line, guard. A-mode blocks keep one outer blank line on each side so
    verbatim forwarding never glues two blocks; _public/ files hold exactly this text."""
    return "\n" + GUARD + "\n\n" + body.strip("\n") + "\n\n" + GUARD + "\n"


INLINE_EXECUTOR = "main agent (inline)"   # alpha.67 (doc 144): the executor text of a sub node the main agent runs itself


def executor_line(mode: dict | None, dispatch: dict | None) -> str | None:
    """doc 10 §4: the `executor` text of a PLAN block / SUB PLAN line; None when the main agent runs the node inline
    with no downgrade to report (the pre-P7 rendering stays byte-identical for those nodes)."""
    if not mode:
        return None
    if dispatch and dispatch.get("actor") == "sub_agent":
        return f"sub-agent ticket {dispatch['ticket']}"   # alpha.67: the id is the engine's dispatch ticket, not a host agent id
    if dispatch and dispatch.get("state") in ("ISSUED", "CLAIMED"):
        return f"sub-agent ticket {dispatch['ticket']} (attempt {dispatch.get('attempt')}{', waiting' if dispatch.get('wait') else ''})"
    if dispatch and dispatch.get("state") == "EXHAUSTED":
        return f"main agent (dispatch exhausted after attempt {dispatch.get('attempt')})"
    if mode.get("downgrade"):
        return f"main agent ({mode['downgrade']})"
    return None


def executor_note(machine_dispatch: dict | None, node_dispatch: dict | None) -> str | None:
    """doc 10 §4: the `executor` text of a NODE block / the `via` tail of a SUB receipt, from the commit's machine block."""
    if not machine_dispatch:
        if node_dispatch and node_dispatch.get("downgrade"):
            return f"main agent ({node_dispatch['downgrade']})"
        return None
    if machine_dispatch.get("actor") == "sub_agent":
        return f"sub-agent ticket {machine_dispatch['ticket']}"
    fb = machine_dispatch.get("fallback") or {}
    if fb:
        return f"main agent (fallback after dispatch {machine_dispatch.get('ticket')}: {_one_line(str(fb.get('reason')), 80)})"
    return f"main agent (ticket {machine_dispatch.get('ticket')})"


def position_label(position: dict) -> str:
    """alpha.84 (doc 176): the engine's track label - "3/8" main, "4.2" sub, "engine"; a caller that passes the bare n / total pair
    (the pre-alpha.84 shape) still reads n/total."""
    return position.get("label") or f"{position['n']}/{position['total']}"


def plan_block(position: dict, node: str, kind: str, mode: str, action: str, resume_kind: str, executor: str | None = None,
               user_language: str | None = None, notice: str | None = None) -> str:
    """v6 business_next_node_plan, nine lines, guarded (doc 45 §1.2)."""
    label = language_label(user_language)
    second = f"node={node} · kind={kind} · execute_mode={mode} · visit={position['visit']} · resume={resume_kind}"
    if executor:
        second += f" · executor={executor}"
    lines = [
        f"▶ NEXT-NODE PLAN — [{position_label(position)}] {node}",
        second,
        f"planned_action={_one_line('HOST_NO_AGENT_TOOL · ' + notice + ' ' + action if notice else action, PLAN_ACTION_MAX)}",
        f"User_Language={label}",
        f"Thought_Output_MUST_USE={label}",
        footer_line(user_language),   # alpha.29: the PLAN closes with the human-output footer (user 2026-09-11 「对齐 user message，加上 ⚠️AI生成内容」)
    ]
    return frame("\n".join(lines))


def sub_plan_line(position: dict, node_id: str, action: str, resume_kind: str, executor: str | None = None) -> str:
    """Sub-graph nodes (doc 05 §4.3) get a one-line plan instead of the full PLAN block (guarded like every block)."""
    tail = f" · executor {executor}" if executor else f" · executor {INLINE_EXECUTOR}"   # alpha.67: an inline sub node says so
    return frame(f"▹ SUB PLAN — [{position_label(position)}] {node_id} · visit {position['visit']} · resume {resume_kind}{tail} · {_one_line(action, 100)}")


def sub_receipt(*, position: dict, node_id: str, order: int, status: str, cache_sha256: str, logical_tool_calls: int,
                user_summary: str, next_node: str | None, executor: str | None = None, evidence_counts: dict | None = None,
                user_messages: list | None = None) -> str:
    """v6 substep_receipt frame with the complete user_summary (alpha.22 E6 fidelity kept): head, body, anchor line.
    alpha.94 (doc 220): when the sub node has a User Message the body is **User Message:** / the messages / **Report:** / the
    summary - the same labels as the node block, so the reader and the web UI see it in the receipt itself; without a message
    the receipt is the v6 shape, byte for byte.
    alpha.84: the head carries the one track label ("4.2" = second sub node of main node 4); the zero-based `[sub k]` beside a
    catalog-wide [n/N] is gone (`order` stays in the signature for the callers)."""
    head = f"{SUB_RULE} [{position_label(position)}] {node_id} {SUB_RULE}"
    anchor = f"tc={logical_tool_calls} | {status} | sha={cache_sha256[:8]}"
    anchor += " | tc basis: declared entries, not physical calls" + _evidence_count_note(evidence_counts)
    if executor:
        anchor += f" | via {executor}"
    if next_node:
        anchor += f" | → {next_node}"
    body = (user_summary or "").strip() or "N/A"
    messages = [str(m).rstrip() for m in (user_messages or []) if isinstance(m, str) and m.strip()]
    if messages:   # alpha.94 (doc 220): a sub node's User Message shows in its own receipt
        body = "**User Message:**\n\n" + "\n\n".join(messages) + "\n\n**Report:**\n\n" + body
    return frame(head + "\n\n" + body + "\n\n" + anchor)


def module_line(module: dict | None) -> str | None:
    if not module:
        return None
    counts = module.get("status_counts") or {}
    detail = ", ".join(f"{k} {v}" for k, v in counts.items() if v)
    sha = (module.get("manifest_sha256") or "—")[:8]
    return f"{module.get('sub_count', 0)} sub node(s) ({detail or '—'}) · status {module.get('status')} · manifest {sha} · dir {module.get('dir')}"


def _glyph(status: str | None) -> str:
    return STATUS_GLYPH.get(status or "", status or "—")


def _evidence_count_note(counts: dict | None) -> str:
    if not counts or not counts["process_references"]:
        return ""
    return (f" · process refs {counts['process_references']} ({counts['verified_references']} engine-hashed references)"
            f" · unique outputs {counts['unique_outputs']} · repeated refs {counts['repeated_references']}"
            f" · conflicts {counts['conflicting_paths']} · cross-scope reuse {counts['cross_scope_reuses']}"
            f" · unknown identity {counts['unknown_identity_references']}")


def node_block(*, position: dict, node: str, kind: str, status: str, cache_sha256: str, committed_at: str,
               elapsed_ms: int | None, logical_tool_calls: int, user_summary: str, user_messages: list,
               artifacts: list, anomalies: list, next_node: str | None, next_kind: str | None,
               module: dict | None = None, executor: str | None = None, explain: str | None = None,
               steps_done: int | None = None, steps_total: int | None = None, process_verified: int = 0,
               gate_question_id: str | None = None, user_message: str | None = None,
               waiting_gate: str | None = None, user_language: str | None = None, evidence_counts: dict | None = None) -> str:
    """v6 business_node_info eight parts (doc 45 §1.3), engine_self seven parts for engine nodes; v7 machine facts
    (sha256, elapsed, engine-hashed tool calls, artifacts, anomalies) live in For Audit and two extra labelled lines."""
    engine_node = kind == "engine"
    label = "engine" if engine_node else position_label(position)   # alpha.84: main "3/8", sub "4.2"
    opening = f"{ENGINE_RULE} [engine] {node} {ENGINE_RULE}" if engine_node else f"{NODE_RULE} [{label}] {node} {NODE_RULE}"
    closing = f"{ENGINE_RULE} end [engine] {node} {ENGINE_RULE}" if engine_node else f"{NODE_RULE} end [{label}] {node} {NODE_RULE}"
    mode_detail = executor or "inline"
    lines = [opening]
    if engine_node:
        lines.append(f"**Node State:** [engine] {node} {_glyph(status)}")
    else:
        lines.append(f"**Node State: [{label}] {node} ({mode_detail}) {_glyph(status)}**")
    completeness = f"{steps_done}/{steps_total}" if steps_done is not None and steps_total is not None else "N/A"
    tc = f"tc={logical_tool_calls} declared entries (not physical calls)"
    tc += _evidence_count_note(evidence_counts) if evidence_counts is not None else (f" ({process_verified} engine-hashed references)" if process_verified else "")
    audit = (f"**For Audit:** completeness {completeness} · {tc} · sha256 {cache_sha256[:16]} · committed {committed_at} · "
             f"elapsed {elapsed_ms if elapsed_ms is not None else '—'} ms · gate {gate_question_id or 'N/A'} · visit {position['visit']} · executor {mode_detail}")
    lines.append(audit)
    mod = module_line(module)
    if mod:
        lines.append(f"**Module:** {mod}")
    if not engine_node:
        lines.append("**User Message:**")   # alpha.93: renamed from Node Message
        lines.append("")
        if user_messages:
            lines.append("\n\n".join(str(m).rstrip() for m in user_messages))
        else:
            lines.append("N/A")
        lines.append("")
    lines.append("**Report:**")
    lines.append("")
    # alpha.47 (doc 97): the triggering request is no longer quoted at the top of Report (user: report 去掉用户对话内容);
    # `user_message` stays in the signature for the callers, unused
    lines.append((user_summary or "").rstrip() or "N/A")
    lines.append("")
    lines.append("**Explain:**")
    lines.append("")
    lines.append((explain or "").strip() or "N/A")
    lines.append("")
    lines.append("**Artifacts:**" + (" N/A" if not artifacts else ""))
    for a in artifacts or []:
        lines.append(f"- {a['path']} ({(a.get('sha256') or '—')[:16]})")
    lines.append("**Anomalies:**" + (" N/A" if not anomalies else ""))
    for a in anomalies or []:
        lines.append(f"- {a}")
    lines.append("**Axiom Governance:**")
    if waiting_gate:   # alpha.25: the mid-state block written at a pause (v6 node_engine step3_5)
        lines.append(f"- Next: ⏸ waiting for the human decision on gate {waiting_gate} — this node resumes after the answer")
    elif next_node:
        lines.append(f"- Next: {next_node} ({next_kind}) — execute the selected outer flow")
    else:
        lines.append("- Next: — (run ended: final answer or terminal state)")
    lines.append(f"- {footer_line(user_language)}")   # alpha.29: Next + the human-output footer (⚠️<disclosure> ⚓Align …)
    lines.append(closing)
    return frame("\n".join(lines))


def menu_block(gate: dict, hint: str | None = None, user_language: str | None = None, *, answered: bool | str = False,
               heading: str | None = None) -> str:
    """alpha.24: the gate menu is a human_output_v5 robot block (v6 persisted public_prompt): 🤖 + menu, guard, footer;
    the Axiom line lives in the footer, not in the body. Review round 3 of docs/05SoulRun 88 (R3): `answered` - the gate's
    answer is recorded and the next reply only completes it, so the reply grammar (cancel refuses, stop ends this run) is
    not offered; one line says what the next reply does. Review round 4 (W4): answered='close' - the recorded answer
    replaces nothing (a refused choice, or one whose ticket is gone): the next reply only closes this stop as recorded."""
    lines = [heading or "▣ GATE — 需要你的决定 / your decision is required", f"· question_id: {gate['question_id']} · node: {gate['node']} · source: {gate['source']}"]
    if gate.get("prompt_text"):
        lines.append(f"· program prompt: {gate['prompt_text']}")
    lines.append("")
    lines.append(gate["question"])
    for i, opt in enumerate(gate["options"], start=1):
        lines.append(f"  {i}. {opt['label']} [{opt['intent']}]")
        for note_line in (opt.get("note") or "").splitlines():   # alpha.50 (doc 104): the option's own sentences
            lines.append(f"     {note_line}")
    labels = GATE_LABELS.get(user_language or "", GATE_LABELS["en"])   # alpha.28 GA
    if gate.get("explanation"):
        lines.append(f"· {labels['explanation']}: {gate['explanation']}")
    if gate.get("recommendation"):
        lines.append(f"· recommendation: {gate['recommendation']} (a recommendation is not a choice)")
    if gate.get("advice"):
        lines.append(f"· {labels['advice']}: {gate['advice']}")
    from . import public_path_text
    for note in public_path_text.diagnostics({'gate':gate}):
        if note['code']=='PUBLIC_PATH_TEXT_AMBIGUOUS':
            lines.append(('· 路径文本疑点，请核对；未修写或确认路径：' if (user_language or '').startswith('zh')
                          else '· Verify ambiguous path text; no path was rewritten or confirmed: ') + note['field'])
    # Model closing remains in the gate record, not a second authorization grammar.
    if gate.get('source') == 'hsaw_doubt':
        from .hsaw_gate import closing_with_sentence
        lines.append('· ' + closing_with_sentence('', user_language))
    else:
        lines.append('· 沉默不构成授权。' if (user_language or '').startswith('zh') else '· Silence is not authorization.')
    zh = (user_language or '').startswith('zh')
    if answered == 'close':   # review round 4 (W4): nothing is replaced; the recorded answer only closes this stop
        lines.append('· 这道题的答复已经记下：下一次回复只会让引擎先按记下的结果关闭这道题（不换人），回复的内容（包括取消/cancel、终止/stop）不会被当作新的选择。'
                     if zh else
                     '· The answer to this stop is already recorded: your next reply only lets the engine first close this stop as '
                     'recorded (nothing is replaced); what the reply says (cancel or stop included) is not taken as a new choice.')
    elif answered:
        lines.append('· 这道题的答复已经记下：下一次回复只会让引擎先按记下的答复处理完，回复的内容（包括取消/cancel、终止/stop）不会被当作新的选择。'
                     if zh else
                     '· The answer to this stop is already recorded: your next reply only lets the engine complete the recorded answer '
                     'first; what the reply says (cancel or stop included) is not taken as a new choice.')
    elif gate.get('conditional_reply'):
        lines.append('· 本业务门明确声明条件回复：可回复编号/选项名/intent，或带条目ID和条件的具体要求。原文完整保留；解读仅校验来源和结构，不证明理解或履行正确。别名不授权；存疑停机询问。' if (user_language or '').startswith('zh') else
                     '· This declared business gate accepts exact choices or requirements with item IDs and conditions. The full original remains authoritative; interpretation checks source/structure, not semantic truth or actual compliance. Aliases do not authorize; doubt stops for the human.')
        lines.append('· items: ' + ', '.join(i['id'] + '=' + i['label'] for i in gate['conditional_reply']['items']))
    else:
        lines.append("· 仅完整编号、选项名或 intent 可授权；附言、组合或未匹配的具体要求保留待裁，不能拆取编号、补答子问题。集合简写如 all 不能作为额外权限的别名。取消/cancel 拒绝；终止/stop 结束本次运行。" if (user_language or '').startswith('zh') else
                     "· Only an exact number, label or intent authorizes a choice. Conditions, combinations and unmatched requirements remain pending: never extract a number or answer other questions. Collection aliases such as all grant no extra permissions. cancel refuses; stop ends this run.")
    if gate.get('clarification_reason'):
        lines.append('· clarification: ' + gate['clarification_reason'])
    if hint:
        lines.append(f"· {hint}")
    if not answered:
        lines.append("· 回复编号、选项名或 intent；回复 取消/cancel 拒绝；回复 终止/stop 结束本次运行。")
    return robot_frame("\n".join(lines), user_language)   # alpha.24: 🤖 + footer (the footer carries the Axiom line)


def final_block(text: str, user_language: str | None = None) -> str:
    """human_output_v5 (v6 robot_block): guard, blank, 🤖 body, blank, guard, footer line. The body is the model's
    final answer verbatim; the footer carries the localized AI disclosure and the Axiom line (doc 45 §1.4)."""
    return robot_frame(text, user_language)


def robot_frame(body: str, user_language: str | None = None) -> str:
    """alpha.24 (doc 46; v6.25.0 robot_block "direct/final/cancel/fatal human output"): the human_output_v5 envelope for
    every human-facing block — final answer, gate menu, run-ended report: guard, blank, 🤖 body, blank, guard, footer."""
    return "\n" + GUARD + "\n\n" + ROBOT + " " + (body or "").strip("\n") + "\n\n" + GUARD + "\n" + footer_line(user_language) + "\n"


# alpha.22 (v6.25.0 render_contract robot_block / ai_disclosure_map, doc 35 R4): one machine-provenance disclosure line
# per user language; the engine appends it to the evidence block, never to the model's final answer text.
AI_DISCLOSURE = {
    "zh": "【AI 生成内容】本回答由 soulrun_aiap依程序生成；执行过程、工具输出与来源已记入本次运行的证据账本。",
    "en": "[AI-generated content] This answer was produced by the soulrun_aiap running a program; the execution, tool outputs and sources are recorded in this run's evidence ledger.",
    "ja": "【AI生成コンテンツ】この回答は soulrun_aiapがプログラムに従って生成したものです。実行過程・ツール出力・出典は本実行の証拠台帳に記録されています。",
    "ko": "【AI 생성 콘텐츠】이 답변은 soulrun_aiap이 프로그램에 따라 생성했습니다. 실행 과정, 도구 출력, 출처는 이번 실행의 증거 원장에 기록되어 있습니다.",
}
EVIDENCE_LIST_MAX = 20


def _code_counts(counts: dict | None) -> str:
    """docs/05SoulRun 87: 'CODE n · CODE n' in the given order (most first); '—' when there is none."""
    return " · ".join(f"{code} {n}" for code, n in (counts or {}).items()) or "—"


def _moved_on_line(moved: dict) -> str:
    """docs/05SoulRun 88 (K1): the evidence line's marker for a stop the human's recheck retired. Review round 3 (R4): before
    the stop that follows opens it has no question. Review round 4 (W1, W2): with no question the code is the condition the
    recorded recheck named (never the retired stop's own); a linked stop whose code is one of the two a retired stop can
    have (DISPATCH_LIVENESS_UNKNOWN, SUBTREE_AGENT_CAPABILITY_UNAVAILABLE) may be that stop's own condition again (a
    recovered move), so the line then says only where and on what records the human was asked."""
    asked, code = moved.get('question_id'), moved.get('code')
    if not asked:
        return f" · recheck moved on: when the human rechecked, another condition ({code}) held this part; nothing was authorized"
    if code in ('DISPATCH_LIVENESS_UNKNOWN', 'SUBTREE_AGENT_CAPABILITY_UNAVAILABLE'):
        return f" · recheck moved on to {asked} ({code}), asked there on the records at that time; nothing was authorized"
    return f" · recheck moved on to {asked}, where another condition ({code}) then held this part; nothing was authorized"


def evidence_block(*, summary: dict, process: list, artifacts: list, sources: list, governance: dict | None,
                   degraded: list, user_language: str | None) -> str:
    """The engine-derived evidence block written once at run completion (_public/evidence.txt, doc 44 E7), guarded."""
    lines = [f"▤ EVIDENCE — {summary['nodes_committed']} nodes · {summary['process_verified']}/{summary['process_calls']} process outputs engine-hashed · "
             f"{summary['artifacts']} artifacts · {summary['sources']} sources · ledger {summary['events']} events sha {summary['ledger_sha256'][:16]}"]
    tracks = summary.get("node_tracks")
    independent = summary.get('independent_budget')
    if independent and independent['added']:
        lines.append(f"· Independent claims: base {independent['base_limit']} + human-authorized {independent['added']} "
                     f"= limit {independent['effective_limit']}; used {independent['used']}. Run-local only.")
    if tracks:   # alpha.84: "10 nodes" beside [n/9] headers and six main nodes was one count too many to reconcile
        lines[0] = lines[0].replace(f"{summary['nodes_committed']} nodes · ",
                                    f"{summary['nodes_committed']} nodes ({tracks['main']} main · {tracks['sub']} sub · {tracks['engine']} engine) · ", 1)
    counts = summary.get("evidence_counts")
    if counts is not None:
        lines[0] = lines[0].replace("process outputs engine-hashed", "unique process outputs engine-hashed")
        lines.append(f"· Basis: {counts['declared_entries']} declared entries; {counts['process_references']} references; "
                     f"{counts['repeated_references']} repeated references; physical business calls UNKNOWN. "
                     "Hashes verified at commit, not proof of separate executions or current file contents.")
        lines.append(f"· Output identity: {counts['conflicting_paths']} conflicting paths; "
                     f"{counts['cross_scope_reuses']} cross-scope reuses; {counts['unknown_identity_references']} unknown references.")

    def _section(title: str, items: list, fmt) -> None:
        if not items:
            lines.append(f"· {title}: —")
            return
        lines.append(f"· {title}:")
        for item in items[:EVIDENCE_LIST_MAX]:
            lines.append("  - " + fmt(item))
        if len(items) > EVIDENCE_LIST_MAX:
            lines.append(f"  … +{len(items) - EVIDENCE_LIST_MAX} more")

    def provenance(p):
        if "references" not in p:
            return ""
        refs = ", ".join(f"r{r['revision']}[{r['index']}]" for r in p['references'])
        return (f" · visit {p['visit']} · refs {refs}" + (" · CONFLICT" if p['conflict'] else "")
                + (" · CROSS_SCOPE_REUSE" if p['cross_scope_reuse'] else ""))

    _section("Process outputs", process, lambda p: f"{p['node']} · {p['tool']} · {p['stdout_path'] or '(no capture)'}" +
                                                    (f" → sealed {p['stdout_snapshot']}" if p.get('stdout_snapshot') else '') + f" · sha {(p['stdout_sha256'] or '—')[:16]} · "
                                                    f"{p['stdout_bytes'] if p['stdout_bytes'] is not None else '—'} B · exit {p['exit_code'] if p['exit_code'] is not None else '—'} · "
                                                    f"{'engine-hashed' if p['verified_by'] == 'engine' else 'self-reported'}" + provenance(p))
    _section("Artifacts", artifacts, lambda a: f"{a['path']} · sha {(a.get('sha256') or '—')[:16]} · {a['node']}")
    _section("Sources", sources, lambda s: f"[{s['ref']}] {s.get('url') or s.get('path')} · {s.get('retrieved_at') or ('local file' if s.get('path') else 'retrieval time unobserved')}"
             + (f" · {s['retrieval_time_basis']} · recorded {s['recorded_at']}" if s.get('retrieval_time_basis') else '')
             + (f" · sha {s['sha256'][:16]} (bytes only)" if s.get('path') and s.get('sha256') else '')
             + (f" · {s['title']}" if s.get('title') else "") + f" · {s['node']}")
    if governance and governance.get("computed"):
        state = "MATCH" if governance.get("match") is True else ("MISMATCH" if governance.get("match") is False else "UNDECLARED")
        lines.append(f"· Governance: {governance.get('package') or '—'} canonical {governance['computed'][:16]} · declared {(governance.get('declared') or '—')[:16]} · {state}")
    else:
        lines.append("· Governance: —")
    # docs/05SoulRun 87: both anomaly scopes by name, per code, with where their records are; never summed or merged by text
    revisions = summary.get('revision_anomalies')
    lines.append(f"· Anomalies: run index {summary['anomalies']}" + (f" · all node revisions {revisions['record_count']}" if revisions else "")
                 + (f" · DEGRADED nodes: {', '.join(degraded)}" if degraded else ""))
    if summary['anomalies'] or (revisions and revisions['record_count']):
        lines.append(f"  - Run index: {_code_counts(summary.get('anomaly_codes'))} · _index.json#/anomalies_summary "
                     "(the final revision of each committed node, and the engine's run records)")
        if revisions:
            lines.append(f"  - All node revisions: {_code_counts(summary.get('revision_anomaly_codes'))} · node caches "
                         "#/payload/anomalies and #/machine/engine_anomalies of every revision, gate pauses and module pre-work included")
        lines.append("  - Overlapping scopes, never summed; records, not incidents.")
    if summary.get('hsaw'):   # alpha.87 (doc 193 §6): the sovereignty doubt gate, graded
        h = summary['hsaw']
        lines.append(f"· HSAW: critical {h['critical']} · medium {h['medium']} · low {h['low']} · gates {h['gates']} · package open {h['open']}")
    if summary.get('cancelled'):   # alpha.88 (doc 196 F4'): the human's cancel closed the business work; the report and the answer still followed
        c = summary['cancelled']
        lines.append(f"· Cancelled: by the human at gate {c['question_id']} on {c['node']} · {len(c.get('dropped_nodes') or [])} planned nodes not run")
    if summary.get('protocol_attempts'):
        p = summary['protocol_attempts']
        decisions = summary.get('human_decisions') or {}
        count = decisions.get('count')
        # review of docs/05SoulRun 87: replacement choices that replaced nothing - refused (round 2, N2), not used (round 3, D2)
        unreplaced = [f'replacement choices {label}: {decisions[key]}' for key, label in
                      (('refused_replacement_choices', 'refused'), ('unused_replacement_choices', 'not used')) if decisions.get(key)]
        lines.append(f"  - Whole-run accounting: REJECTED={p['rejected_count']}; ERROR={p['error_count']}; "
                     f"unreadable receipts={p['unreadable_count']}; human decisions={count if count is not None else 'UNKNOWN'}"
                     + (f" ({'; '.join(unreplaced)})" if unreplaced else '') + ". "
                     "Includes earlier resumes and final retries; archived commits / resolved choices and free text, not business retries or all Provider failures.")
        for decision in decisions.get('records', []):
            unused = decision.get('replacement_not_used')
            lines.append(f"  - Human decision: {decision['question_id']} · {decision.get('node')} · "
                         f"{decision.get('chosen_intent') or decision.get('resolution_kind') or 'resolved'}"
                         + (" · replacement refused: the records it was offered on had changed; nothing was replaced"
                            if decision.get('replacement_refused') else '')
                         + ((" · replacement not used: the host recorded the old agent's return after this choice; this "
                             'choice replaced nothing' if unused.get('old_return_recorded_after_choice') else
                             ' · replacement not used: the records this choice was made on changed after it; this choice '
                             'replaced nothing') if unused else '')
                         # docs/05SoulRun 88 (K1): the human's recheck retired this stop
                         + (_moved_on_line(decision['recheck_moved_on']) if decision.get('recheck_moved_on') else ''))
    if summary.get('anomaly_groups'):
        groups = summary['anomaly_groups']
        lines.append(f"· Anomaly counting: run index {groups['record_count']} records / {groups['distinct_text_groups']} exact-text groups"
                     + (f"; all node revisions {revisions['record_count']} records / {revisions['distinct_text_groups']} exact-text groups"
                        if revisions else "") + "; incident count unassessed")
    lines.append(f"· {AI_DISCLOSURE.get(user_language or 'en', AI_DISCLOSURE['en'])}")
    lines.append(f"· {AXIOM_MARK}")
    return frame("\n".join(lines))


def error_report_block(termination: dict, node: str | None, findings: list, user_language: str | None = None,
                       gate: dict | None = None, report: str | None = None, messages: list | None = None,
                       execution_report: str | None = None, terminal_facts: dict | None = None,
                       compact: bool = False) -> str:
    """alpha.24: the run-ended report (cancel / fatal) is human output → human_output_v5 robot block.
    alpha.25 (doc 47 item 1): it also carries the landed content of the node the run stopped on — the rejected gate's
    question and options, the user response, the node's User Message and Report so far — so a cancel never shrinks the record."""
    lines = [f"✖ RUN ENDED — {termination.get('kind')} (by {termination.get('by')}) at {termination.get('at')}",
             f"· node: {node or '—'}", f"· reason: {termination.get('reason') or '—'}"]
    rr = termination.get("rejection_report")
    if rr and gate:
        lines.append(f"· user response: {rr.get('user_response') or '—'}")
    elif rr:
        lines.append(f"· rejected confirm: {rr.get('confirm_text') or '—'} · user response: {rr.get('user_response') or '—'}")
    for f in findings or []:
        lines.append(f"  - {f.get('severity', '')} {f.get('code', '')}: {f.get('detail', '')}")
    if gate:
        lines += ["", "**Question:**", "", (gate.get("question") or "").rstrip() or "N/A"]
        for i, opt in enumerate(gate.get("options") or [], start=1):
            lines.append(f"  {i}. {opt.get('label')} [{opt.get('intent')}]")
            for note_line in (opt.get("note") or "").splitlines():   # alpha.50
                lines.append(f"     {note_line}")
    if messages:
        lines += ["", "**User Message:**", "", "\n\n".join(str(m).rstrip() for m in messages)]
    human_end = termination.get('kind') == 'human_termination' and terminal_facts is not None
    if report and report.strip() and not human_end:
        lines += ["", "**Report:**", "", report.rstrip()]
    if execution_report and execution_report.strip() and not human_end:   # alpha.90 (doc 202 D): the committed execution report, when the run ended after it
        lines += ["", "**Execution report (committed):**", "", execution_report.rstrip()]
    if terminal_facts is not None:
        english = str(user_language or '').lower().startswith('en')
        lines += ['', '**Accepted execution facts:**' if english else '**已接受执行事实：**', '',
                  'These are cache facts, not an executed final-report node.' if english else '以下是机器缓存事实，不冒称已执行最终报告节点。']
        for stage in terminal_facts['stages']:
            lines.append(f"- `{stage['node']}@{stage['visit']}`: {stage['status']} · `{stage['cache']}` · SHA-256 `{stage['sha256']}`")
        if not terminal_facts['stages']:
            lines.append('No accepted stages verified.' if english else '没有可核验的已接受阶段。')
        lines += ['', '**Registered artifacts (verified at acceptance):**' if english else '**登记产物（接受时核验）：**', '']
        for artifact in terminal_facts['artifacts']:
            metadata = artifact['accepted_metadata']
            if terminal_facts.get('evidence_ref'):
                lines.append(f"- `{artifact['node']}@{artifact['visit']}`: `{metadata.get('path', 'N/A')}` · {metadata.get('kind', 'artifact')}")
            else:
                lines.append(f"- `{artifact['node']}@{artifact['visit']}`: `{json.dumps(metadata, ensure_ascii=False)}`")
        if terminal_facts.get('evidence_ref'):
            lines += ['', f"Full machine evidence ({len(terminal_facts['artifacts'])} registered artifacts): `{terminal_facts['evidence_ref']}`"]
        if not terminal_facts['artifacts']:
            lines.append('None registered; this does not prove no writes occurred.' if english else '未登记产物；这不证明没有实际写入。')
        answers = terminal_facts.get('unconsumed_answers') or []
        if answers:
            lines += ['', '**Received answers not consumed by a commit:**' if english else '**已收到、尚未被提交消费的答复：**', '',
                      'This records receipt only, not correct interpretation or execution.' if english else '仅记录收到答复，不证明解释正确或已经执行。']
            for answer in answers:
                lines.append(f"- `{answer['question_id']}` · `{answer['path']}` · SHA-256 `{answer['sha256']}`")
                lines.extend('> ' + line for line in answer['answer_text'].splitlines())
        for issue in terminal_facts['unavailable']:
            lines.append(f'- UNVERIFIABLE: {issue}')
        notice = ('Ended by your decision; prior Reports and accepted products remain preserved. This is not an execution failure. '
                  'Do not replay this run; unregistered writes are not covered by these facts.' if english else
                  '已按你的决定结束本次运行；此前 Report 和已接受产物完整保留，不把人类终止说成执行失败。不要重放；未登记写入不在这些事实的核验范围内。') if human_end else (
                  'This run failed. Preserve evidence and partial products; do not replay this run. A repair, rollback or fresh run requires new authorization. '
                   'Unregistered writes are not covered by the cache facts.' if english else
                   '本运行失败。保留证据与半成品，不重放旧运行。修复、回退或新运行须另行授权；未登记写入不在上述缓存事实的核验范围内。')
        lines += ['', '**Final notice:**' if english else '**终止说明：**', '', notice,
                  f"`{terminal_facts['cache']}`"]
    if compact and terminal_facts and terminal_facts.get('evidence_ref'):
        # Native details keep the exact full report accessible without another model or request.
        overview = lines[:3] + [line for line in lines[3:] if line.startswith(('· user response:', '· rejected confirm:'))]
        overview += ['', '**Report:**', '', ('Accepted stages / registered artifacts: ' if english else '已接受阶段 / 登记产物：')
            + f"{len(terminal_facts['stages'])} / {len(terminal_facts['artifacts'])}", '', notice]
        overview.extend(f"- {f.get('severity', '')} {f.get('code', '')}: {f.get('detail', '')}" for f in findings or [])
        overview.extend(f'- UNVERIFIABLE: {issue}' for issue in terminal_facts['unavailable'])
        for answer in terminal_facts.get('unconsumed_answers') or []:
            overview += ['', ('Received, not executed: ' if english else '已收到、尚未被提交消费（不证明解释正确或已经执行）：') + answer['question_id']]
            overview.extend('> ' + line for line in answer['answer_text'].splitlines())
        title = 'Full preserved report and execution evidence' if english else '完整报告与执行证据（原文保全）'
        preserved = html.escape('\n'.join(lines)).replace('\n', '&#10;')
        lines = overview + ['', '<details>', f'<summary>{title}</summary>', f'<pre>{preserved}</pre>', '</details>']
    return robot_frame("\n".join(lines), user_language)   # alpha.24 envelope
