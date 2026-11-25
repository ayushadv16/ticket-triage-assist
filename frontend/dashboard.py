
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def format_ist(timestamp):
    """
    Convert a UTC timestamp into Indian Standard Time.
    Assumes timezone-naive timestamps from the database are UTC.
    """
    if not timestamp:
        return "N/A"

    try:
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        ist_time = timestamp.astimezone(
            ZoneInfo("Asia/Kolkata")
        )

        return ist_time.strftime("%d %b %Y, %I:%M %p")

    except (ValueError, TypeError):
        return str(timestamp)
# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="Ticket Triage Assistant",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded"
)

DEFAULT_API_URL = "http://127.0.0.1:8001"

# --------------------------------------------------
# CUSTOM CSS
# --------------------------------------------------


st.markdown("""
<style>
/* Main background */
.stApp {
    background: #F8FAFC;
    color: #1E293B;
}

.main .block-container {
    max-width: 1450px;
    padding: 2rem 2.5rem 3rem;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #E2E8F0;
}

/* Typography */
h1, h2, h3 {
    color: #172554 !important;
    font-weight: 650 !important;
}

p, label, .stMarkdown {
    color: #334155;
}

[data-testid="stCaptionContainer"] {
    color: #64748B !important;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background: #FFFFFF;
    padding: 20px;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
}

div[data-testid="stMetric"] label {
    color: #64748B !important;
}

div[data-testid="stMetricValue"] {
    color: #172554 !important;
    font-weight: 700;
}

/* Buttons */
.stButton > button,
.stFormSubmitButton > button {
    background: #2563EB;
    color: white !important;
    border: 1px solid #2563EB;
    border-radius: 8px;
    font-weight: 600;
    min-height: 40px;
}

.stButton > button:hover,
.stFormSubmitButton > button:hover {
    background: #1D4ED8;
    border-color: #1D4ED8;
}

/* Inputs */
.stTextInput input,
.stTextArea textarea {
    background: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
}

/* Data tables */
div[data-testid="stDataFrame"] {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
}

/* Containers */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #FFFFFF;
    border-color: #E2E8F0;
    border-radius: 12px;
}

/* Dividers */
hr {
    border-color: #E2E8F0;
}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

if "api_url" not in st.session_state:
    st.session_state.api_url = DEFAULT_API_URL

if "selected_ticket" not in st.session_state:
    st.session_state.selected_ticket = None


# --------------------------------------------------
# API HELPERS
# --------------------------------------------------

def api_request(method, endpoint, **kwargs):
    url = f"{st.session_state.api_url.rstrip('/')}{endpoint}"

    try:
        response = requests.request(
            method,
            url,
            timeout=30,
            **kwargs
        )

        if response.status_code >= 400:
            try:
                error = response.json().get("detail", response.text)
            except ValueError:
                error = response.text

            return None, f"API Error {response.status_code}: {error}"

        if response.status_code == 204 or not response.content:
            return {}, None

        return response.json(), None

    except requests.exceptions.ConnectionError:
        return None, (
            "Cannot connect to FastAPI. "
            "Make sure the backend is running on port 8001."
        )

    except requests.exceptions.Timeout:
        return None, "The API request timed out."

    except requests.exceptions.RequestException as error:
        return None, str(error)


def get_tickets():
    data, error = api_request("GET", "/tickets")
    return data if data is not None else [], error


def get_notifications(unread_only=False):
    endpoint = (
        "/notifications/unread"
        if unread_only
        else "/notifications"
    )

    data, error = api_request("GET", endpoint)
    return data if data is not None else [], error


def get_replies(ticket_id):
    data, error = api_request(
        "GET",
        f"/tickets/{ticket_id}/replies"
    )
    return data if data is not None else [], error



def format_date(value):
    """Display database UTC timestamps in Indian Standard Time."""
    return format_ist(value)


def priority_label(priority):
    labels = {
        "Urgent": "🔴 Urgent",
        "High": "🟠 High",
        "Medium": "🟡 Medium",
        "Low": "🟢 Low"
    }
    return labels.get(priority, "⚪ Unknown")


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

with st.sidebar:
    st.title("🎫 Ticket Triage")
    st.caption("AI-powered customer support")

    st.divider()

    st.subheader("Backend Configuration")

    api_url = st.text_input(
        "FastAPI URL",
        value=st.session_state.api_url
    )

    if st.button("Connect to API", use_container_width=True):
        st.session_state.api_url = api_url.rstrip("/")
        st.rerun()

    if st.session_state.api_url != api_url.rstrip("/"):
        st.session_state.api_url = api_url.rstrip("/")

    health, health_error = api_request("GET", "/health")

    if health and health.get("status") == "healthy":
        st.success("Backend Connected")
    else:
        st.error("Backend Disconnected")
        if health_error:
            st.caption(health_error)

    st.divider()

    page = st.radio(
        "Navigation",
        [
            "Dashboard",
            "Create Ticket",
            "Ticket Management",
            "Notifications"
        ]
    )

    st.divider()

    st.caption("Ticket Triage Assistant")
    st.caption("Powered by FastAPI + Groq AI")


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

tickets, ticket_error = get_tickets()
notifications, notification_error = get_notifications()
unread_notifications, unread_error = get_notifications(
    unread_only=True
)

if ticket_error:
    st.error(ticket_error)

if notification_error:
    st.warning(notification_error)

# --------------------------------------------------
# DASHBOARD PAGE
# --------------------------------------------------

if page == "Dashboard":

    st.title("📊 Support Dashboard")
    st.caption("Overview of customer support operations")

    if st.button("🔄 Refresh Dashboard"):
        st.rerun()

    total_tickets = len(tickets)

    open_tickets = sum(
        1 for ticket in tickets
        if ticket.get("status") == "Open"
    )

    closed_tickets = sum(
        1 for ticket in tickets
        if ticket.get("status") == "Closed"
    )

    urgent_tickets = sum(
        1 for ticket in tickets
        if ticket.get("priority") == "Urgent"
    )

    unread_count = len(unread_notifications)

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Total Tickets", total_tickets)
    col2.metric("Open Tickets", open_tickets)
    col3.metric("Closed Tickets", closed_tickets)
    col4.metric("Urgent Tickets", urgent_tickets)
    col5.metric("Unread Alerts", unread_count)

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Ticket Status")

        status_data = pd.DataFrame({
            "Status": ["Open", "Closed"],
            "Tickets": [open_tickets, closed_tickets]
        })

        if total_tickets:
            st.bar_chart(
                status_data.set_index("Status")
            )
        else:
            st.info("No tickets available.")

    with right:
        st.subheader("Priority Distribution")

        priority_counts = {
            "Low": 0,
            "Medium": 0,
            "High": 0,
            "Urgent": 0
        }

        for ticket in tickets:
            priority = ticket.get("priority")

            if priority in priority_counts:
                priority_counts[priority] += 1

        priority_data = pd.DataFrame({
            "Priority": list(priority_counts.keys()),
            "Tickets": list(priority_counts.values())
        })

        if total_tickets:
            st.bar_chart(
                priority_data.set_index("Priority")
            )
        else:
            st.info("No priority data available.")

    st.divider()

    st.subheader("Recent Tickets")

    if tickets:
        recent = tickets[:10]

        display_data = []

        for ticket in recent:
            display_data.append({
                "ID": ticket["ticket_id"],
                "Subject": ticket["subject"],
                "Product": ticket["product_area"],
                "Status": ticket["status"],
                "Priority": ticket["priority"],
                "Replies": ticket["reply_count"]
            })

        st.dataframe(
            pd.DataFrame(display_data),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No tickets found.")


# --------------------------------------------------
# CREATE TICKET PAGE
# --------------------------------------------------

elif page == "Create Ticket":

    st.title("➕ Create Support Ticket")
    st.caption("Register a new customer support request")

    with st.form("create_ticket_form"):

        subject = st.text_input(
            "Ticket Subject",
            placeholder="Example: Payment deducted but order not confirmed"
        )

        customer_email = st.text_input(
            "Customer Email",
            placeholder="customer@example.com"
        )

        product_area = st.selectbox(
            "Product Area",
            [
                "Billing",
                "Bug",
                "Feature Request",
                "Account"
            ]
        )

        submitted = st.form_submit_button(
            "Create Ticket",
            use_container_width=True
        )

        if submitted:

            if not subject.strip() or not customer_email.strip():
                st.error("Please complete all required fields.")

            else:
                payload = {
                    "subject": subject.strip(),
                    "customer_email": customer_email.strip(),
                    "product_area": product_area
                }

                result, error = api_request(
                    "POST",
                    "/tickets",
                    json=payload
                )

                if result:
                    st.success(
                        f"Ticket #{result['ticket_id']} created successfully."
                    )

                    st.json(result)

                else:
                    st.error(error)


# --------------------------------------------------
# TICKET MANAGEMENT PAGE
# --------------------------------------------------

elif page == "Ticket Management":

    st.title("🎫 Ticket Management")

    if not tickets:
        st.info("No tickets available.")
    else:

        col1, col2 = st.columns(2)

        with col1:
            status_filter = st.selectbox(
                "Filter by Status",
                ["All", "Open", "Closed"]
            )

        with col2:
            priority_filter = st.selectbox(
                "Filter by Priority",
                ["All", "Urgent", "High", "Medium", "Low"]
            )

        search = st.text_input(
            "Search by ticket ID, subject or email"
        )

        filtered_tickets = []

        for ticket in tickets:

            if (
                status_filter != "All"
                and ticket["status"] != status_filter
            ):
                continue

            if (
                priority_filter != "All"
                and ticket["priority"] != priority_filter
            ):
                continue

            search_text = (
                f"{ticket['ticket_id']} "
                f"{ticket['subject']} "
                f"{ticket['customer_email']}"
            ).lower()

            if search and search.lower() not in search_text:
                continue

            filtered_tickets.append(ticket)

        st.write(
            f"Showing {len(filtered_tickets)} ticket(s)"
        )

        if not filtered_tickets:
            st.info("No tickets match your filters.")

        else:
            ticket_options = {
                f"#{t['ticket_id']} - {t['subject']}": t["ticket_id"]
                for t in filtered_tickets
            }

            selected_label = st.selectbox(
                "Select Ticket",
                list(ticket_options.keys())
            )

            selected_id = ticket_options[selected_label]

            ticket_data, ticket_error = api_request(
                "GET",
                f"/tickets/{selected_id}"
            )

            if ticket_error:
                st.error(ticket_error)

            elif ticket_data:

                st.divider()

                st.subheader(
                    f"Ticket #{ticket_data['ticket_id']}"
                )

                st.markdown(
                    f"### {ticket_data['subject']}"
                )

                col1, col2, col3 = st.columns(3)

                col1.metric(
                    "Status",
                    ticket_data["status"]
                )

                col2.metric(
                    "Priority",
                    ticket_data["priority"]
                )

                col3.metric(
                    "Reply Count",
                    ticket_data["reply_count"]
                )

                st.write(
                    "**Customer:**",
                    ticket_data["customer_email"]
                )

                st.write(
                    "**Product Area:**",
                    ticket_data["product_area"]
                )

                st.write(
                    "**Domain Flag:**",
                    ticket_data["domain_flag"]
                )

                st.write(
                    "**Created:**",
                    format_date(ticket_data["created_at"])
                )

                st.write(
                    "**Last Activity:**",
                    format_date(ticket_data["last_activity_at"])
                )

                st.divider()

                st.subheader("🤖 AI Analysis")

                st.info(
                    ticket_data.get("ai_summary")
                    or "AI summary is not available yet."
                )

                st.write(
                    "**AI Priority:**",
                    priority_label(ticket_data["priority"])
                )

                st.write(
                    "**Estimated Synthesis Cost (USD):**",
                    f"${ticket_data['synthesis_cost']:.8f}"
                )

                st.divider()

                # ------------------------------
                # CONVERSATION
                # ------------------------------

                st.subheader("💬 Conversation History")

                replies, replies_error = get_replies(selected_id)

                if replies_error:
                    st.error(replies_error)

                elif replies:

                    for reply in replies:

                        sender = reply["sender_type"]

                        with st.chat_message(
                            "user" if sender == "Customer" else "assistant"
                        ):

                            st.markdown(
                                f"**{sender}**"
                            )

                            st.write(reply["message"])

                            st.caption(
                                format_date(reply["created_at"])
                            )

                else:
                    st.info("No replies yet.")

                st.divider()

                # ------------------------------
                # ADD REPLY
                # ------------------------------

                st.subheader("✉️ Add Reply")

                with st.form(
                    f"reply_form_{selected_id}"
                ):

                    sender_type = st.selectbox(
                        "Sender Type",
                        ["Customer", "Agent"]
                    )

                    reply_message = st.text_area(
                        "Message",
                        placeholder="Enter reply message..."
                    )

                    send_reply = st.form_submit_button(
                        "Send Reply",
                        use_container_width=True
                    )

                    if send_reply:

                        if not reply_message.strip():
                            st.error("Message cannot be empty.")

                        else:
                            result, error = api_request(
                                "POST",
                                f"/tickets/{selected_id}/replies",
                                json={
                                    "sender_type": sender_type,
                                    "message": reply_message.strip()
                                }
                            )

                            if result:
                                st.success(
                                    "Reply saved successfully."
                                )

                                st.rerun()

                            else:
                                st.error(error)

                # ------------------------------
                # CLOSE TICKET
                # ------------------------------

                if ticket_data["status"] == "Open":

                    if st.button(
                        "🔒 Close Ticket",
                        use_container_width=True
                    ):

                        result, error = api_request(
                            "PATCH",
                            f"/tickets/{selected_id}/close"
                        )

                        if result:
                            st.success("Ticket closed successfully.")
                            st.rerun()

                        else:
                            st.error(error)

                else:
                    st.warning(
                        "This ticket is closed. "
                        "A new Customer reply will automatically reopen it."
                    )


# --------------------------------------------------
# NOTIFICATIONS PAGE
# --------------------------------------------------

elif page == "Notifications":

    st.title("🔔 Agent Notifications")
    st.caption("Customer reply alerts and ticket priority updates")

    col1, col2 = st.columns(2)

    col1.metric(
        "Total Notifications",
        len(notifications)
    )

    col2.metric(
        "Unread Notifications",
        len(unread_notifications)
    )

    st.divider()

    notification_filter = st.radio(
        "Show Notifications",
        ["All", "Unread"],
        horizontal=True
    )

    displayed_notifications = (
        unread_notifications
        if notification_filter == "Unread"
        else notifications
    )

    if not displayed_notifications:

        st.info("No notifications to display.")

    else:

        for notification in displayed_notifications:

            with st.container(border=True):

                col1, col2 = st.columns([4, 1])

                with col1:

                    st.markdown(
                        f"### Ticket #{notification['ticket_id']}"
                    )

                    st.write(
                        f"**Subject:** {notification['subject']}"
                    )

                    st.write(
                        f"**Latest Customer Reply:** "
                        f"{notification['reply_snippet']}"
                    )

                    st.write(
                        f"**Priority:** "
                        f"{priority_label(notification['priority'])}"
                    )

                    st.caption(
                        f"Assigned to: {notification['assigned_to']}"
                    )

                    st.caption(
                        f"Created: {format_date(notification['created_at'])}"
                    )

                with col2:

                    if notification["is_read"]:
                        st.success("Read")

                    else:
                        st.warning("Unread")

                        if st.button(
                            "Mark as Read",
                            key=f"read_{notification['notification_id']}"
                        ):

                            result, error = api_request(
                                "PATCH",
                                f"/notifications/{notification['notification_id']}/read"
                            )

                            if result:
                                st.success("Marked as read.")
                                st.rerun()

                            else:
                                st.error(error)
