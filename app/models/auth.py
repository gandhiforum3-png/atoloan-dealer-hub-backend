from pydantic import BaseModel, EmailStr, Field, field_validator

# bcrypt only reads the first 72 bytes and bcrypt>=5 raises beyond that —
# reject longer passwords as a 422 instead of letting them become a 500.
BCRYPT_MAX_BYTES = 72


def _bcrypt_sized(value: str) -> str:
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"password must be at most {BCRYPT_MAX_BYTES} bytes")
    return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    _size = field_validator("password")(_bcrypt_sized)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)

    _size = field_validator("current_password", "new_password")(_bcrypt_sized)


class DealerUserOut(BaseModel):
    dealer_id: str
    email: str
    name: str
    dealership_name: str
    is_admin: bool = False
    must_change_password: bool = False
