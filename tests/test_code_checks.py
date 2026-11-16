"""第4回 宿題（実装）: コード判定（app/code_checks.py）と回答生成の trace 記録のテスト。API キーは使わない。"""

from pydantic_ai.models.test import TestModel

import app.agent
from app import code_checks, judge
from app.code_checks import body_length, run_checks
from app.judge import read_jsonl

MY_CASES = judge.ROOT / "data" / "eval" / "my_cases.jsonl"


def case(answer, **checks):
    return {"id": "x", "answer": answer, "checks": checks, "trace": [{"tool": "search_glossary", "args": {}}]}


def test_my_cases_are_well_formed():
    cases = read_jsonl(MY_CASES)
    assert len(cases) == 10 and len({c["id"] for c in cases}) == 10
    ids = {e["id"] for e in app.tools.load_glossary()}
    for c in cases:
        assert c["question"] and c["reference"]["expected"]
        assert set(c["reference"]["glossary"]) <= ids


def test_lecture_correct_detects_wrong_number():
    assert run_checks(case("…\n関係する回：第2回", lectures=[2]))["lecture_correct"]["verdict"] == "pass"
    assert run_checks(case("…\n関係する回：第2回・第6回", lectures=[2, 6]))["lecture_correct"]["verdict"] == "pass"
    r = run_checks(case("…\n関係する回：第3回", lectures=[2]))
    assert r["lecture_correct"]["verdict"] == "fail"
    assert r["lecture_mark"]["verdict"] == "pass"  # 「第N回がある」だけでは間違いに気づけない


def test_tools_called_uses_trace():
    assert run_checks(case("…", tools=["search_glossary"]))["tools_called"]["verdict"] == "pass"
    assert run_checks(case("…", tools=["make_quiz"]))["tools_called"]["verdict"] == "fail"
    assert run_checks({"id": "x", "answer": "…", "checks": {"tools": ["make_quiz"]}})["tools_called"]["verdict"] == "n/a"


def test_code_block_and_quiz_answer_leak():
    assert run_checks(case("```python\nprint(1)\n```", no_code_block=True))["no_code_block"]["verdict"] == "fail"
    assert run_checks(case("requires_approval を調べてみましょう", no_code_block=True))["no_code_block"]["verdict"] == "pass"
    lora = next(e for e in app.tools.load_glossary() if e["id"] == "lora")
    assert run_checks(case(f"問題：LoRAとは？\n答え：{lora['definition']}", hide_definitions_of=2))["hide_definitions"]["verdict"] == "fail"
    assert run_checks(case("問題：「LoRA」の意味は？", hide_definitions_of=2))["hide_definitions"]["verdict"] == "pass"


def test_body_length_ignores_code_and_lecture_line():
    assert body_length("あいう\n```\nxxxxxxxx\n```\n関係する回：第2回") == 3


def test_generate_records_trace(monkeypatch):
    monkeypatch.setattr(app.agent, "build_model", lambda: TestModel())
    cases = judge.generate_answers([{"id": "01", "question": "LoRAとは？"}], wait=0)
    tools_called = {t["tool"] for t in cases[0]["trace"]}
    assert "search_glossary" in tools_called
    assert cases[0]["usage"]["requests"] >= 1


def test_compare_markdown_runs_without_labels():
    cases = [{**case("…\n第2回", lectures=[2]), "category": "正常系"}]
    md = code_checks.compare(cases, {"x": run_checks(cases[0])}, None, None)
    assert "コード判定の一覧" in md
