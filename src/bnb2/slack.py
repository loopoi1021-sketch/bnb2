"""7단계: 슬랙 봇. Socket Mode 로 질문을 받아 그래프를 돌리고, 질문 스레드에 답한다."""

import logging
import os
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from bnb2.graph import answer

MENTION = re.compile(r"<@[A-Z0-9]+>")
ERROR_REPLY = "⚠️ 지금은 답변할 수 없어요. 잠시 후 다시 물어봐 주세요."


def clean(text: str) -> str:
    """'<@U123> 수건 몇 장?' → '수건 몇 장?'"""
    return MENTION.sub("", text).strip()


def needs_owner(state: dict) -> bool:
    """사람이 봐야 하는 경우: 담당자 판단 질문, 또는 문서 질문인데 근거 검사에서 막힘."""
    return state["intent"] == "escalate" or (
        state["intent"] == "faq" and not (state.get("grounded") and state.get("direct"))
    )


def make_reply(state: dict) -> str:
    owner = os.getenv("SLACK_OWNER_ID")  # 담당자 슬랙 ID. 비워두면 멘션하지 않는다
    return f"{state['reply']}\n<@{owner}>" if owner and needs_owner(state) else state["reply"]


def react(client, channel: str, ts: str, name: str, remove: bool = False) -> None:
    # 이모지는 진행 표시일 뿐이라, 실패해도 답변은 계속 보낸다.
    try:
        (client.reactions_remove if remove else client.reactions_add)(channel=channel, timestamp=ts, name=name)
    except SlackApiError:
        pass


def handle(event: dict, client, logger: logging.Logger) -> None:
    question = clean(event.get("text", ""))
    if not question:
        return
    channel, ts = event["channel"], event["ts"]
    thread = event.get("thread_ts")  # 스레드 안에서 물으면 그 스레드에, 아니면 채널에 바로 답한다 (None 이면 채널)
    react(client, channel, ts, "eyes")
    try:
        state = answer(question, user_id=event.get("user"), session_id=f"{channel}-{thread or ts}", tags=["slack"])
        text, done = make_reply(state), "white_check_mark"
    except Exception:
        logger.exception("답변 실패: %s", question)
        text, done = ERROR_REPLY, "warning"
    client.chat_postMessage(channel=channel, thread_ts=thread, text=text)
    react(client, channel, ts, "eyes", remove=True)
    react(client, channel, ts, done)


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    app = App(token=os.environ["SLACK_BOT_TOKEN"])

    app.event("app_mention")(handle)  # 채널에서 @bnb2 멘션

    @app.event("message")
    def direct_message(event, client, logger):  # 봇과의 DM
        if event.get("channel_type") == "im" and not event.get("bot_id") and not event.get("subtype"):
            handle(event, client, logger)

    print("🤖 bnb2 슬랙 봇 실행 중 (Ctrl+C 로 종료)")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
