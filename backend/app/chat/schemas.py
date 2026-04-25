from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    github_url: str
    username: str

class ChatResponse(BaseModel):
    response: str
