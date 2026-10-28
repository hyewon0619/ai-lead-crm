"""푸시 알림.

알림 본문에는 사건 내용을 싣지 않는다. 잠금화면·알림센터에 남기 때문이다.
"새 리드가 있습니다" 수준의 문구와 lead_id만 보내고, 내용은 로그인 후 앱에서 본다.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PushMessage:
    user_id: int
    kind: str
    lead_id: str
    title: str = "새 리드 알림"
    body: str = ""  # 의도적으로 비워 둔다


@dataclass
class Notifier:
    sent: list[PushMessage] = field(default_factory=list)

    def lead_assigned(self, user_id: int, lead_id: str) -> PushMessage:
        msg = PushMessage(user_id=user_id, kind="lead_assigned", lead_id=lead_id)
        self.sent.append(msg)  # 실제 운영에서는 사내 푸시 게이트웨이로 전송
        return msg


notifier = Notifier()
