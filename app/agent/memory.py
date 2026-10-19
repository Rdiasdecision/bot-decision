from collections import OrderedDict, deque
from dataclasses import dataclass
from threading import RLock
from typing import Literal


@dataclass(frozen=True)
class ConversationMessage:
    role: Literal["user", "assistant"]
    content: str


def format_history(messages: tuple[ConversationMessage, ...]) -> str:
    if not messages:
        return "(nenhuma mensagem anterior)"
    labels = {"user": "Usuario", "assistant": "Assistente"}
    return "\n".join(
        f"{labels[message.role]}: {message.content}" for message in messages
    )


class InMemoryConversationWindow:
    """Janela LRU, thread-safe e limitada, adequada ao prototipo local."""

    def __init__(self, max_messages: int = 8, max_sessions: int = 1_000) -> None:
        if max_messages < 2:
            raise ValueError("max_messages deve ser >= 2")
        if max_sessions < 1:
            raise ValueError("max_sessions deve ser >= 1")
        self._max_messages = max_messages
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, deque[ConversationMessage]] = OrderedDict()
        self._lock = RLock()

    def get(self, session_id: str) -> tuple[ConversationMessage, ...]:
        with self._lock:
            messages = self._sessions.get(session_id)
            if messages is None:
                return ()
            self._sessions.move_to_end(session_id)
            return tuple(messages)

    def append_exchange(self, session_id: str, question: str, answer: str) -> None:
        with self._lock:
            messages = self._sessions.get(session_id)
            if messages is None:
                if len(self._sessions) >= self._max_sessions:
                    self._sessions.popitem(last=False)
                messages = deque(maxlen=self._max_messages)
                self._sessions[session_id] = messages
            else:
                self._sessions.move_to_end(session_id)

            messages.append(ConversationMessage(role="user", content=question))
            messages.append(ConversationMessage(role="assistant", content=answer))

    def clear(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None
