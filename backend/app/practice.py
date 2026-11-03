"""Persistent multi-question practice, stale-answer protection and safe public mapping."""

from copy import deepcopy
from hashlib import sha256

from .models import Unit

RULE_VERSION = "choice-v2"


class StalePractice(ValueError):
    pass


def questions(unit: Unit) -> list[dict]:
    return [unit.material["practice"], *unit.material.get("practice_variants", [])]


def state_for(unit: Unit) -> dict:
    if unit.practice_state is not None:
        return deepcopy(unit.practice_state)
    return _new_state(unit, 0)


def _new_state(unit: Unit, round_number: int) -> dict:
    count = len(questions(unit))
    start = round_number % count
    return {"round": round_number, "turn": 0, "queue": list(range(start, count)) + list(range(start)),
            "correct": [], "wrong": []}


def restart_practice(unit: Unit) -> None:
    unit.practice_state = _new_state(unit, state_for(unit)["round"] + 1)


def option_order(unit: Unit, state: dict, index: int) -> list[int]:
    positions = list(range(len(questions(unit)[index]["options"])))
    if len(questions(unit)) == 1:
        return positions  # Preserve answer-only clients of existing single-question courses.
    return sorted(positions, key=lambda position: sha256(
        f"{unit.id}:{state['round']}:{state['turn']}:{index}:{position}".encode()
    ).digest())


def public_practice(unit: Unit) -> dict:
    bank, state = questions(unit), state_for(unit)
    active = state["queue"][0] if state["queue"] else None
    result = {"question_id": f"q{active + 1}" if active is not None else None,
              "token": f"{state['round']}:{state['turn']}", "total": len(bank),
              "correct": len(state["correct"]), "remaining": len(state["queue"]),
              "round": state["round"] + 1, "attempt": state["turn"] + 1,
              "is_retry": active in state["wrong"], "legacy": len(bank) == 1,
              "question": "本轮练习已完成", "options": []}
    if active is not None:
        result.update(question=bank[active]["question"],
                      options=[bank[active]["options"][i] for i in option_order(unit, state, active)])
    return result


def grade_practice(unit: Unit, answer: str, question_id: str | None, token: str | None) -> dict:
    bank, state = questions(unit), state_for(unit)
    current = public_practice(unit)
    if (not state["queue"] or
            (len(bank) > 1 and (question_id is None or token is None)) or
            (question_id is not None and question_id != current["question_id"]) or
            (token is not None and token != current["token"])):
        raise StalePractice("题目已更新或缺少题目标识，请同步最新记录后重新作答。")
    if not answer.isdecimal() or len(answer) > 2 or int(answer) >= len(current["options"]):
        raise ValueError("请选择一个有效选项。")
    chosen = int(answer)
    index = state["queue"].pop(0)
    item = bank[index]
    passed = option_order(unit, state, index)[chosen] == item["correct_index"]
    if passed:
        state["correct"].append(index)
    else:
        state["queue"].append(index)
        if index not in state["wrong"]:
            state["wrong"].append(index)
    state["turn"] += 1
    unit.practice_state = state
    complete = not state["queue"]
    if complete:
        lead = "本轮练习已通过，可以进入实战。" if len(bank) > 1 else "旧版单题练习已通过；这不代表已通过多题检验。"
    elif passed:
        lead = f"这题回答正确。还有 {len(state['queue'])} 道题需要完成。"
    else:
        lead = "这题尚未答对，已安排补练。请先理解解析，再完成接下来的题目。"
    evidence = {"source": "answer_key", "provider": None, "model": None, "requested_model": None,
                "rule_version": RULE_VERSION, "passed": passed,
                "question_id": current["question_id"], "question": current["question"],
                "options": current["options"], "selected_answer": current["options"][chosen],
                "correct_answer": item["options"][item["correct_index"]],
                "round": current["round"], "attempt": current["attempt"], "was_retry": current["is_retry"],
                "question_source": unit.material.get("question_source", {"source": "unknown"})}
    return {"score": 100 if passed else 0, "passed": passed, "complete": complete,
            "feedback": lead + "\n\n" + item.get("explanation", "请回到讲解，对照例子重新思考。"),
            "assessment": evidence}
