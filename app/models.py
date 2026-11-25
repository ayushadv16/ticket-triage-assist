
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
    Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(255), nullable=False)
    customer_email = Column(String(255), nullable=False, index=True)
    product_area = Column(String(50), nullable=False)
    status = Column(String(20), default="Open", nullable=False)
    priority = Column(String(20), default="Medium")
    ai_summary = Column(Text, nullable=True)
    synthesis_cost = Column(Float, default=0.0)
    domain_flag = Column(String(30), default="Unknown")
    reply_count = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    last_activity_at = Column(DateTime, nullable=True)

    replies = relationship(
        "Reply",
        back_populates="ticket",
        cascade="all, delete-orphan"
    )


class Reply(Base):
    __tablename__ = "replies"

    reply_id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(
        Integer,
        ForeignKey("tickets.ticket_id"),
        nullable=False
    )
    sender_type = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    ticket = relationship("Ticket", back_populates="replies")


class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(Integer, primary_key=True, index=True)

    ticket_id = Column(
        Integer,
        ForeignKey("tickets.ticket_id"),
        nullable=False,
        index=True
    )

    assigned_to = Column(
        String(100),
        nullable=False,
        default="Support Team"
    )

    subject = Column(String(255), nullable=False)
    reply_snippet = Column(Text, nullable=False)
    priority = Column(String(20), nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    is_read = Column(Boolean, default=False, nullable=False)
