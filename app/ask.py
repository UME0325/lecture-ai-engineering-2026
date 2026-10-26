"""第1回: 素のLLMに質問するスクリプト。

使い方:
    uv run python -m app.ask "LoRAとは何ですか？"
    uv run python -m app.ask            # 質問を省略すると、講座に固有の質問をする
    uv run python -m app.ask --chat     # 会話履歴を保ったまま続けて質問する（宿題：実装）
    uv run python -m app.ask --temperature 1.5 "LoRAとは何ですか？"

ツールを持たない「素の」呼び出し。
講座に固有のことを聞くと、「分からない」と答えるか、一般論でもっともらしく答える
（講座の実際とは違う）ことを確かめよう。
（第3回で、用語集を検索できるエージェントにして改善する）
"""

import argparse

from google import genai
from google.genai import errors, types

from app.config import MODEL, api_error_message, get_api_key

# 講座に固有の質問。正しい答えは data/glossary.json の homework-levels にある
DEFAULT_QUESTION = "AIE2026の講座の宿題にある「3レベル」とは何ですか？"

# 会話モードを終える入力
EXIT_WORDS = {"exit", "quit", "q", "終了"}


def format_usage(usage) -> str:
    """response.usage_metadata を「入力 / 出力 / 合計」の1行にする。

    モデルや API の状態によっては usage_metadata や各値が None のことがあるので、
    その場合は「-」と表示する。思考（thinking）トークンがあれば併記する。
    """
    if usage is None:
        return "[tokens] 取得できませんでした"

    def n(value):
        return "-" if value is None else str(value)

    text = (
        f"[tokens] 入力 {n(usage.prompt_token_count)}"
        f" / 出力 {n(usage.candidates_token_count)}"
        f" / 合計 {n(usage.total_token_count)}"
    )
    thoughts = getattr(usage, "thoughts_token_count", None)
    if thoughts:
        text += f"（うち思考 {thoughts}）"
    return text


def make_config(temperature: float | None) -> types.GenerateContentConfig | None:
    """temperature を指定したときだけ config を作る（指定なしはモデルの既定値）。"""
    if temperature is None:
        return None
    return types.GenerateContentConfig(temperature=temperature)


def ask(question: str, temperature: float | None = None, client=None) -> str:
    """1回だけ質問する。会話履歴は持たない。"""
    client = client or genai.Client(api_key=get_api_key())
    response = client.models.generate_content(
        model=MODEL, contents=question, config=make_config(temperature)
    )

    # 第1回 演習: 入力トークン数と出力トークン数を表示する
    print(format_usage(response.usage_metadata))

    return response.text


class Conversation:
    """会話履歴を保ったまま続けて質問する（第1回 宿題：実装）。

    LLM の API 自体は前の会話を覚えていない。そこで、これまでの質問（user）と
    回答（model）を history に積み、毎回その全部を contents として送る。
    そのため、ターンを重ねるほど入力トークン数が増える。
    """

    def __init__(self, client=None, temperature: float | None = None):
        self.client = client or genai.Client(api_key=get_api_key())
        self.config = make_config(temperature)
        self.history: list[types.Content] = []

    def send(self, question: str) -> str:
        user_turn = types.Content(role="user", parts=[types.Part(text=question)])
        response = self.client.models.generate_content(
            model=MODEL, contents=[*self.history, user_turn], config=self.config
        )
        answer = response.text or ""

        # 成功したときだけ履歴に積む（APIエラーで失敗したターンは残さない）
        self.history.append(user_turn)
        self.history.append(
            types.Content(role="model", parts=[types.Part(text=answer)])
        )

        print(format_usage(response.usage_metadata))
        return answer


def chat_loop(conversation: Conversation, input_fn=input) -> None:
    """標準入力から質問を読み、空行または exit で終わるまで会話を続ける。"""
    print("会話モードです。終了するには exit（または空行）を入力してください。\n")
    turn = 1
    while True:
        try:
            question = input_fn(f"[{turn}] あなた> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in EXIT_WORDS:
            break
        try:
            print(conversation.send(question))
        except errors.APIError as e:
            # 1回の失敗で会話全体を終わらせない。履歴は失敗前のまま残る
            print(api_error_message(e.code, e.message))
            continue
        print()
        turn += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="素のLLMに質問する")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument(
        "--chat", action="store_true", help="会話履歴を保ったまま続けて質問する"
    )
    parser.add_argument(
        "--temperature", type=float, default=None, help="生成の temperature（省略時は既定値）"
    )
    args = parser.parse_args()

    print(f"[model] {MODEL}")
    if args.temperature is not None:
        print(f"[temperature] {args.temperature}")

    if args.chat:
        chat_loop(Conversation(temperature=args.temperature))
        return

    print(f"[質問] {args.question}\n")
    try:
        print(ask(args.question, temperature=args.temperature))
    except errors.APIError as e:
        print(api_error_message(e.code, e.message))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
