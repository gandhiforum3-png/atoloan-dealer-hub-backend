from datetime import datetime

from pydantic import BaseModel, EmailStr


class DealerAdminOut(BaseModel):
    dealer_id: str
    email: str
    name: str
    dealership_name: str
    is_admin: bool
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None


class CreatedDealerOut(DealerAdminOut):
    # Shown to the admin exactly once; the dealer must change it at first sign-in.
    temporary_password: str


class CreateDealerRequest(BaseModel):
    email: EmailStr
    name: str
    dealership_name: str
    is_admin: bool = False


class UpdateDealerRequest(BaseModel):
    name: str | None = None
    dealership_name: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None
    is_admin: bool | None = None


class ResetPasswordOut(BaseModel):
    temporary_password: str
