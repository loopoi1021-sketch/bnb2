"""7·8단계: 슬랙 봇. Socket Mode 로 질문을 받아 그래프를 돌려 답하고, 👍/👎 피드백을 Langfuse 점수로 남긴다."""

import json
import logging
import os
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from bnb2 import feedback, store
from bnb2.graph import answer
from bnb2.tracing import client as langfuse, mask_text

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


def reply_blocks(text: str, trace_id: str | None, question: str = "") -> list[dict]:
    """답변 + 👍/👎 버튼. 버튼에 Langfuse 트레이스 ID 와 질문을 담아 두고, 누르면 그 트레이스에 점수를 붙인다."""
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
    if trace_id:
        value = json.dumps({"t": trace_id, "q": question[:300]}, ensure_ascii=False)  # 버튼 value 는 2,000자 제한
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "action_id": "feedback_up", "value": value,
             "text": {"type": "plain_text", "text": "👍 정확해요"}},
            {"type": "button", "action_id": "feedback_down", "value": value,
             "text": {"type": "plain_text", "text": "👎 틀렸어요"}},
        ]})
    return blocks


def save_feedback(trace_id: str, user: str, good: bool, question: str, reply: str,
                  comment: str | None = None) -> None:
    """Langfuse 점수(대시보드용, 30일 보관) + 우리 DB(원본 영구 보관)에 함께 남긴다.
    같은 사람이 다시 누르면(👍→👎, 코멘트 추가) 새로 쌓지 않고 덮어쓴다."""
    lf = langfuse()
    lf.create_score(
        score_id=f"{trace_id}-{user}", trace_id=trace_id, name="user_feedback", value=1 if good else 0,
        data_type="NUMERIC", comment=mask_text(comment) if comment else None, metadata={"slack_user": user},
    )
    feedback.save(trace_id, user, good, comment, question, reply, lf.get_trace_url(trace_id=trace_id))


def notify_owner(client, user: str, question: str, reply: str, comment: str, trace_id: str) -> None:
    """코멘트가 달린 👎 만 담당자에게 DM 으로 모아 보낸다. 담당자 ID 가 없으면 보내지 않는다."""
    owner = os.getenv("SLACK_OWNER_ID")
    if not owner:
        return
    url = langfuse().get_trace_url(trace_id=trace_id)
    text = (f"👎 피드백이 왔어요 — <@{user}>\n❓ *질문*: {question}\n🤖 *봇 답변*: {reply}\n💬 *코멘트*: {comment}"
            f"\n🔗 <{url}|Langfuse에서 자세히 보기>")
    client.chat_postMessage(channel=owner, text=text, unfurl_links=False)


def mark_feedback(client, body: dict, label: str) -> None:
    """버튼을 지우고 '👍 피드백 고마워요' 표시로 바꾼다 (중복 클릭 방지)."""
    msg = body["message"]
    blocks = [b for b in msg["blocks"] if b["type"] != "actions"]
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"{label} — <@{body['user']['id']}>"}]})
    client.chat_update(channel=body["channel"]["id"], ts=msg["ts"], text=msg["text"], blocks=blocks)


COMMENT_VIEW = {
    "type": "modal", "callback_id": "feedback_comment",
    "title": {"type": "plain_text", "text": "어떤 점이 틀렸나요?"},
    "submit": {"type": "plain_text", "text": "보내기"},
    "blocks": [{"type": "input", "block_id": "comment", "optional": True,
                "label": {"type": "plain_text", "text": "맞는 정보나 틀린 부분 (선택)"},
                "element": {"type": "plain_text_input", "action_id": "text", "multiline": True}}],
}


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
    session = f"{channel}-{thread or ts}"
    try:
        state = answer(question, user_id=event.get("user"), session_id=session, tags=["slack"])
        text, done, trace_id = make_reply(state), "white_check_mark", state["trace_id"]
    except Exception as e:
        logger.exception("답변 실패: %s", question)
        state = {"question": question, "error": f"{type(e).__name__}: {e}"}
        text, done, trace_id = ERROR_REPLY, "warning", None
    store.record({**state, "reply": text}, channel="slack", user=event.get("user"), thread=session)
    client.chat_postMessage(channel=channel, thread_ts=thread, text=text,
                            blocks=reply_blocks(text, trace_id, question))
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

    @app.action("feedback_up")
    def feedback_up(ack, body, client):
        ack()
        value = json.loads(body["actions"][0]["value"])
        save_feedback(value["t"], body["user"]["id"], good=True, question=value["q"], reply=body["message"]["text"])
        mark_feedback(client, body, "👍 피드백 고마워요")

    @app.action("feedback_down")
    def feedback_down(ack, body, client):
        ack()
        value, user = json.loads(body["actions"][0]["value"]), body["user"]["id"]
        trace_id = value["t"]
        meta = {"t": trace_id, "q": value["q"], "a": body["message"]["text"][:1500]}  # private_metadata 3,000자 제한
        # trigger_id 는 3초 안에 써야 해서 입력 창부터 연다
        client.views_open(trigger_id=body["trigger_id"],
                          view={**COMMENT_VIEW, "private_metadata": json.dumps(meta, ensure_ascii=False)})
        save_feedback(trace_id, user, good=False, question=meta["q"], reply=meta["a"])  # 창을 닫아도 👎 는 남긴다
        mark_feedback(client, body, "👎 피드백 고마워요")

    @app.view("feedback_comment")
    def feedback_comment(ack, body, view, client):
        ack()
        comment = view["state"]["values"]["comment"]["text"]["value"]
        if comment:
            meta, user = json.loads(view["private_metadata"]), body["user"]["id"]
            save_feedback(meta["t"], user, good=False, question=meta["q"], reply=meta["a"], comment=comment)
            notify_owner(client, user, meta["q"], meta["a"], comment, meta["t"])

    print("🤖 bnb2 슬랙 봇 실행 중 (Ctrl+C 로 종료)")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
