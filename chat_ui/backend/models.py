from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    new_messages: list[dict]
