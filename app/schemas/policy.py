from pydantic import BaseModel


class PolicyRead(BaseModel):
    name: str
    content: dict
