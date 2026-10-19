from app.agent.memory import InMemoryConversationWindow


def test_keeps_only_configured_message_window() -> None:
    memory = InMemoryConversationWindow(max_messages=4, max_sessions=10)

    memory.append_exchange("s1", "pergunta 1", "resposta 1")
    memory.append_exchange("s1", "pergunta 2", "resposta 2")
    memory.append_exchange("s1", "pergunta 3", "resposta 3")

    history = memory.get("s1")
    assert [message.content for message in history] == [
        "pergunta 2",
        "resposta 2",
        "pergunta 3",
        "resposta 3",
    ]


def test_evicts_least_recently_used_session() -> None:
    memory = InMemoryConversationWindow(max_messages=4, max_sessions=2)
    memory.append_exchange("s1", "p1", "r1")
    memory.append_exchange("s2", "p2", "r2")
    memory.get("s1")
    memory.append_exchange("s3", "p3", "r3")

    assert memory.get("s1")
    assert memory.get("s2") == ()
    assert memory.get("s3")


def test_clear_removes_session() -> None:
    memory = InMemoryConversationWindow()
    memory.append_exchange("s1", "p", "r")

    assert memory.clear("s1") is True
    assert memory.get("s1") == ()
    assert memory.clear("s1") is False
