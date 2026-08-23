from pydantic import BaseModel


class BankOut(BaseModel):
    id: int
    name: str


class DealerBankSelection(BaseModel):
    bank_ids: list[int]
