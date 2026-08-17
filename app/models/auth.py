from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class DealerUserOut(BaseModel):
    dealer_id: str
    email: str
    name: str
    dealership_name: str
