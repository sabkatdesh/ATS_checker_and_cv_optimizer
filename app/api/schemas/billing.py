from pydantic import BaseModel


class AddCoinsRequest(BaseModel):
    amount: int
    description: str = "Manual top-up"
