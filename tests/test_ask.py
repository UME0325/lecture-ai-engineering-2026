"""app/ask.py のテスト（APIキー不要）。

実際の Gemini は呼ばず、generate_content に渡された contents を記録する
偽クライアントを使って、「履歴が毎回送られているか」を確かめる。
"""

from types import SimpleNamespace

from app.ask import Conversation, ask, chat_loop, format_usage


def usage(prompt, output, total=None, thoughts=None):
    if total is None and prompt is not None and output is not None:
        total = prompt + output
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=output,
        total_token_count=total,
        thoughts_token_count=thoughts,
    )


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        n = len(self.calls)
        return SimpleNamespace(text=f"回答{n}", usage_metadata=usage(10 * n, 5))


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


def texts(contents):
    return [(c.role, c.parts[0].text) for c in contents]


def test_format_usage():
    assert format_usage(usage(12, 34)) == "[tokens] 入力 12 / 出力 34 / 合計 46"
    assert "思考 7" in format_usage(usage(1, 2, 10, thoughts=7))
    assert "-" in format_usage(usage(None, None, None))
    assert "取得できません" in format_usage(None)


def test_ask_prints_tokens(capsys):
    client = FakeClient()
    assert ask("LoRAとは？", client=client) == "回答1"
    assert "[tokens] 入力 10 / 出力 5" in capsys.readouterr().out
    assert client.models.calls[0]["config"] is None


def test_temperature_is_passed():
    client = FakeClient()
    ask("LoRAとは？", temperature=1.5, client=client)
    assert client.models.calls[0]["config"].temperature == 1.5


def test_conversation_sends_history():
    client = FakeClient()
    conv = Conversation(client=client)
    conv.send("私の名前はタロウです")
    conv.send("私の名前は？")

    first, second = (c["contents"] for c in client.models.calls)
    assert texts(first) == [("user", "私の名前はタロウです")]
    assert texts(second) == [
        ("user", "私の名前はタロウです"),
        ("model", "回答1"),
        ("user", "私の名前は？"),
    ]
    assert len(conv.history) == 4


def test_failed_turn_is_not_kept():
    class Boom(Exception):
        pass

    class FailingModels(FakeModels):
        def generate_content(self, model, contents, config=None):
            raise Boom

    client = FakeClient()
    client.models = FailingModels()
    conv = Conversation(client=client)
    try:
        conv.send("hello")
    except Boom:
        pass
    assert conv.history == []


def test_chat_loop_until_exit(capsys):
    client = FakeClient()
    conv = Conversation(client=client)
    inputs = iter(["一つ目", "二つ目", "exit"])
    chat_loop(conv, input_fn=lambda _prompt: next(inputs))

    out = capsys.readouterr().out
    assert "回答1" in out and "回答2" in out
    assert len(client.models.calls) == 2
