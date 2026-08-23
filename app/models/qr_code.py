from datetime import datetime

from pydantic import BaseModel


class QRCodeLabelUpdate(BaseModel):
    label: str


class QRCodeOut(BaseModel):
    dealer_id: str
    label: str
    token: str
    url: str
    image_data_url: str
    updated_at: datetime


class PublicDealerOut(BaseModel):
    dealer_id: str
    dealership_name: str
