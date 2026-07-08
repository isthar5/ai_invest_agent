from app.multi_agent.base import AgentMessage


class Fusion:
    @staticmethod
    async def aggregate(messages: list) -> AgentMessage:
        valid_messages = [m for m in messages if isinstance(m, AgentMessage)]
        if not valid_messages:
            return AgentMessage(content="所有 Agent 执行失败或超时。")

        combined_metadata = {}
        combined_history = []
        contents = []

        for msg in valid_messages:
            combined_metadata.update(msg.metadata or {})
            combined_history.extend(msg.history or [])
            if msg.content:
                contents.append(msg.content)

        return AgentMessage(
            content=" | ".join(contents),
            metadata=combined_metadata,
            history=combined_history,
        )
