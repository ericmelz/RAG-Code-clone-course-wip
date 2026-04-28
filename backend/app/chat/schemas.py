from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    namespace: str
    username: str

class ChatResponse(BaseModel):
    response: str
