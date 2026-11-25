
from datetime import datetime, timezone
from pathlib import Path
import os

import requests
from dotenv import load_dotenv

# Load the project-root .env BEFORE reading environment variables.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE, override=True)

EMAIL_VALIDATION_API_URL = os.getenv(
    "EMAIL_VALIDATION_API_URL",
    "https://www.disify.com/api/email"
)


from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import engine, Base, get_db
from app.models import Ticket, Reply, Notification
from app.schemas import (
    TicketCreate,
    TicketResponse,
    ReplyCreate,
    ReplyResponse,
    NotificationResponse
)

from app.services.ai_service import analyse_ticket


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Ticket Triage Assistant",
    description="AI-powered customer support ticket management",
    version="1.0.0"
)


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Ticket Triage Assistant API is running"
    }


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected"
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable"
        )


# --------------------------------------------------
# CREATE TICKET
# --------------------------------------------------

@app.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=201
)
def create_ticket(
    ticket_data: TicketCreate,
    db: Session = Depends(get_db)
):
    
    domain_flag = "Unknown"

    try:
        response = requests.get(
            f"{EMAIL_VALIDATION_API_URL}/{ticket_data.customer_email}",
            timeout=4
        )

        response.raise_for_status()
        result = response.json()

        if isinstance(result, dict):
            if result.get("disposable") is True:
                domain_flag = "Disposable"
            elif result.get("disposable") is False:
                domain_flag = "Normal"

    except (requests.RequestException, ValueError, TypeError, AttributeError):
        domain_flag = "Unknown"


    new_ticket = Ticket(
        subject=ticket_data.subject,
        customer_email=str(ticket_data.customer_email),
        product_area=ticket_data.product_area,
        status="Open",
        priority="Medium",
        domain_flag=domain_flag,
        reply_count=0,
        synthesis_cost=0.0
    )

    try:
        db.add(new_ticket)
        db.commit()
        db.refresh(new_ticket)

        return new_ticket

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Unable to create ticket"
        )


# --------------------------------------------------
# GET ALL TICKETS
# --------------------------------------------------

@app.get(
    "/tickets",
    response_model=list[TicketResponse]
)
def get_tickets(db: Session = Depends(get_db)):
    return (
        db.query(Ticket)
        .order_by(Ticket.ticket_id.desc())
        .all()
    )


# --------------------------------------------------
# GET SINGLE TICKET
# --------------------------------------------------

@app.get(
    "/tickets/{ticket_id}",
    response_model=TicketResponse
)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db)
):
    ticket = (
        db.query(Ticket)
        .filter(Ticket.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found"
        )

    return ticket


# --------------------------------------------------
# ADD REPLY + AI + NOTIFICATION
# --------------------------------------------------

@app.post(
    "/tickets/{ticket_id}/replies",
    response_model=ReplyResponse,
    status_code=201
)
def add_reply(
    ticket_id: int,
    reply_data: ReplyCreate,
    db: Session = Depends(get_db)
):
    ticket = (
        db.query(Ticket)
        .filter(Ticket.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found"
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    new_reply = Reply(
        ticket_id=ticket_id,
        sender_type=reply_data.sender_type,
        message=reply_data.message,
        created_at=now
    )

    ticket.reply_count = (ticket.reply_count or 0) + 1
    ticket.last_activity_at = now

    # Reopen a closed ticket only for customer replies.
    if (
        ticket.status == "Closed"
        and reply_data.sender_type == "Customer"
    ):
        ticket.status = "Open"

    # Save reply first so an AI or notification failure
    # cannot remove the customer's message.
    try:
        db.add(new_reply)
        db.commit()
        db.refresh(new_reply)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Unable to save reply"
        )

    # AI and notification are triggered only by customers.
    if reply_data.sender_type == "Customer":

        try:
            replies = (
                db.query(Reply)
                .filter(Reply.ticket_id == ticket_id)
                .order_by(
                    Reply.created_at.asc(),
                    Reply.reply_id.asc()
                )
                .all()
            )

            ai_result = analyse_ticket(
                subject=ticket.subject,
                product_area=ticket.product_area,
                replies=replies
            )

            ticket.ai_summary = ai_result["summary"]
            ticket.priority = ai_result["priority"]

            ticket.synthesis_cost = (
                ticket.synthesis_cost or 0.0
            ) + ai_result["estimated_cost"]

            db.commit()

            print(
                f"AI analysis successful for ticket {ticket_id}"
            )

            print(f"Priority: {ai_result['priority']}")
            print(f"Tokens: {ai_result['total_tokens']}")
            print(
                f"Estimated cost: "
                f"${ai_result['estimated_cost']:.8f}"
            )

        except Exception as error:
            db.rollback()

            print(
                f"AI processing failed for ticket "
                f"{ticket_id}: {error}"
            )

        # Reload ticket so the notification uses the latest
        # successfully saved priority.
        ticket = (
            db.query(Ticket)
            .filter(Ticket.ticket_id == ticket_id)
            .first()
        )

        try:
            notification = Notification(
                ticket_id=ticket_id,
                assigned_to="Support Team",
                subject=ticket.subject,
                reply_snippet=reply_data.message[:300],
                priority=ticket.priority or "Medium",
                is_read=False
            )

            db.add(notification)
            db.commit()

            print(
                f"Notification created for ticket {ticket_id}"
            )

        except Exception as error:
            db.rollback()

            print(
                f"Notification creation failed for ticket "
                f"{ticket_id}: {error}"
            )

    db.refresh(new_reply)
    return new_reply


# --------------------------------------------------
# GET TICKET REPLIES
# --------------------------------------------------

@app.get(
    "/tickets/{ticket_id}/replies",
    response_model=list[ReplyResponse]
)
def get_replies(
    ticket_id: int,
    db: Session = Depends(get_db)
):
    ticket = (
        db.query(Ticket)
        .filter(Ticket.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found"
        )

    return (
        db.query(Reply)
        .filter(Reply.ticket_id == ticket_id)
        .order_by(
            Reply.created_at.asc(),
            Reply.reply_id.asc()
        )
        .all()
    )


# --------------------------------------------------
# CLOSE TICKET
# --------------------------------------------------

@app.patch("/tickets/{ticket_id}/close")
def close_ticket(
    ticket_id: int,
    db: Session = Depends(get_db)
):
    ticket = (
        db.query(Ticket)
        .filter(Ticket.ticket_id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found"
        )

    ticket.status = "Closed"

    try:
        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Unable to close ticket"
        )

    return {
        "message": "Ticket closed successfully",
        "ticket_id": ticket_id,
        "status": ticket.status
    }


# --------------------------------------------------
# GET ALL NOTIFICATIONS
# --------------------------------------------------

@app.get(
    "/notifications",
    response_model=list[NotificationResponse]
)
def get_notifications(db: Session = Depends(get_db)):
    return (
        db.query(Notification)
        .order_by(Notification.notification_id.desc())
        .all()
    )


# --------------------------------------------------
# GET UNREAD NOTIFICATIONS
# --------------------------------------------------

@app.get(
    "/notifications/unread",
    response_model=list[NotificationResponse]
)
def get_unread_notifications(db: Session = Depends(get_db)):
    return (
        db.query(Notification)
        .filter(Notification.is_read == False)
        .order_by(Notification.notification_id.desc())
        .all()
    )


# --------------------------------------------------
# MARK NOTIFICATION AS READ
# --------------------------------------------------

@app.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db)
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.notification_id == notification_id
        )
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=404,
            detail="Notification not found"
        )

    notification.is_read = True

    try:
        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Unable to update notification"
        )

    return {
        "message": "Notification marked as read",
        "notification_id": notification_id,
        "is_read": True
    }
