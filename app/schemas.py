
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Literal, Optional
from datetime import datetime


class TicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=255)
    customer_email: EmailStr
    product_area: Literal[
        "Billing",
        "Bug",
        "Feature Request",
        "Account"
    ]


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket_id: int
    subject: str
    customer_email: str
    product_area: str
    status: str
    priority: Optional[str]
    ai_summary: Optional[str]
    synthesis_cost: float
    domain_flag: str
    reply_count: int
    created_at: Optional[datetime]
    last_activity_at: Optional[datetime]


class ReplyCreate(BaseModel):
    sender_type: Literal["Customer", "Agent"]
    message: str = Field(min_length=1)


class ReplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reply_id: int
    ticket_id: int
    sender_type: str
    message: str
    created_at: Optional[datetime]


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_id: int
    ticket_id: int
    assigned_to: str
    subject: str
    reply_snippet: str
    priority: str
    created_at: Optional[datetime]
    is_read: bool
