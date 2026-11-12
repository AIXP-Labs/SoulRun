"""Host entry metadata is distinct from gate resolution or execution authority."""


def valid_wait(answer: dict) -> bool:
    return (answer.get('status') == 'WAITING_USER' and answer.get('answer_valid') is True
            and answer.get('conditions_satisfied') is False)


def entry_mode(answer: dict) -> str:
    if valid_wait(answer):
        return 'resume_waiting_conditions'
    return {'ANSWERED': 'resume', 'ROUTED': 'resume', 'WAITING_USER': 'resume_invalid_answer',
            'TERMINATED': 'terminal', 'REJECTED_BY_USER': 'terminal'}.get(answer.get('status'), 'resume')


def context(answer: dict, question_id: str) -> dict:
    result = dict(question_id=question_id, status=answer.get('status'))
    for key in ('answer_valid', 'conditions_satisfied', 'answer_disposition', 'answer_hint'):
        if key in answer:
            result[key] = answer[key]
    gate = answer.get('gate') or {}
    if gate.get('question_id') == question_id and gate.get('public_prompt_ref'):
        result['public_prompt_ref'] = gate['public_prompt_ref']
    return result
