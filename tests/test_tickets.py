
from unittest.mock import Mock

import app.main as main


def mock_email_validation(monkeypatch, disposable=False):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"disposable": disposable}

    monkeypatch.setattr(
        main.requests,
        "get",
        lambda *args, **kwargs: response,
    )


def mock_ai_analysis(monkeypatch, priority="Medium"):
    result = {
        "summary": "Test ticket summary",
        "priority": priority,
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "estimated_cost": 0.0001,
    }

    ai_mock = Mock(return_value=result)

    monkeypatch.setattr(
        main,
        "analyse_ticket",
        ai_mock,
    )

    return ai_mock


def create_test_ticket(client, monkeypatch):
    mock_email_validation(monkeypatch)

    response = client.post(
        "/tickets",
        json={
            "subject": "Test support issue",
            "customer_email": "test@example.com",
            "product_area": "Bug",
        },
    )

    assert response.status_code == 201
    return response.json()["ticket_id"]


def test_invalid_email_is_rejected(client, monkeypatch):
    email_api = Mock()

    monkeypatch.setattr(main.requests, "get", email_api)

    response = client.post(
        "/tickets",
        json={
            "subject": "Invalid email test",
            "customer_email": "not-an-email",
            "product_area": "Billing",
        },
    )

    assert response.status_code == 422
    email_api.assert_not_called()


def test_email_api_failure_does_not_block_ticket(
    client,
    monkeypatch,
):
    def failed_request(*args, **kwargs):
        raise main.requests.RequestException("API unavailable")

    monkeypatch.setattr(
        main.requests,
        "get",
        failed_request,
    )

    response = client.post(
        "/tickets",
        json={
            "subject": "Email API failure test",
            "customer_email": "test@example.com",
            "product_area": "Billing",
        },
    )

    assert response.status_code == 201
    assert response.json()["domain_flag"] == "Unknown"


def test_customer_reply_reopens_closed_ticket(
    client,
    monkeypatch,
):
    ticket_id = create_test_ticket(client, monkeypatch)

    ai_mock = mock_ai_analysis(monkeypatch)

    close_response = client.patch(
        f"/tickets/{ticket_id}/close"
    )

    assert close_response.status_code == 200

    reply_response = client.post(
        f"/tickets/{ticket_id}/replies",
        json={
            "sender_type": "Customer",
            "message": "The issue is still happening.",
        },
    )

    assert reply_response.status_code == 201

    ticket = client.get(f"/tickets/{ticket_id}").json()

    assert ticket["status"] == "Open"
    assert ticket["reply_count"] == 1
    assert ticket["ai_summary"] == "Test ticket summary"

    ai_mock.assert_called_once()

    notifications = client.get("/notifications").json()

    assert len(notifications) == 1
    assert notifications[0]["ticket_id"] == ticket_id


def test_agent_reply_does_not_reopen_closed_ticket(
    client,
    monkeypatch,
):
    ticket_id = create_test_ticket(client, monkeypatch)

    ai_mock = mock_ai_analysis(monkeypatch)

    close_response = client.patch(
        f"/tickets/{ticket_id}/close"
    )

    assert close_response.status_code == 200

    reply_response = client.post(
        f"/tickets/{ticket_id}/replies",
        json={
            "sender_type": "Agent",
            "message": "Internal support note.",
        },
    )

    assert reply_response.status_code == 201

    ticket = client.get(f"/tickets/{ticket_id}").json()

    assert ticket["status"] == "Closed"
    assert ticket["reply_count"] == 1

    ai_mock.assert_not_called()

    notifications = client.get("/notifications").json()

    assert notifications == []


def test_agent_reply_does_not_trigger_ai_or_notification(
    client,
    monkeypatch,
):
    ticket_id = create_test_ticket(client, monkeypatch)

    ai_mock = mock_ai_analysis(monkeypatch)

    reply_response = client.post(
        f"/tickets/{ticket_id}/replies",
        json={
            "sender_type": "Agent",
            "message": "We are investigating the issue.",
        },
    )

    assert reply_response.status_code == 201

    ticket = client.get(f"/tickets/{ticket_id}").json()

    assert ticket["reply_count"] == 1
    assert ticket["ai_summary"] is None
    assert ticket["synthesis_cost"] == 0

    ai_mock.assert_not_called()

    notifications = client.get("/notifications").json()

    assert notifications == []


def test_customer_reply_triggers_ai_and_notification(
    client,
    monkeypatch,
):
    ticket_id = create_test_ticket(client, monkeypatch)

    ai_mock = mock_ai_analysis(
        monkeypatch,
        priority="High",
    )

    reply_response = client.post(
        f"/tickets/{ticket_id}/replies",
        json={
            "sender_type": "Customer",
            "message": "My payment was deducted but my order is pending.",
        },
    )

    assert reply_response.status_code == 201

    ticket = client.get(f"/tickets/{ticket_id}").json()

    assert ticket["ai_summary"] == "Test ticket summary"
    assert ticket["priority"] == "High"
    assert ticket["synthesis_cost"] == 0.0001

    ai_mock.assert_called_once()

    notifications = client.get("/notifications").json()

    assert len(notifications) == 1
    assert notifications[0]["priority"] == "High"


def test_unexpected_email_api_response_does_not_block_ticket(
    client,
    monkeypatch,
):
    response_mock = Mock()
    response_mock.raise_for_status.return_value = None

    # API unexpectedly returns a JSON list instead of an object.
    response_mock.json.return_value = ["unexpected", "response"]

    monkeypatch.setattr(
        main.requests,
        "get",
        lambda *args, **kwargs: response_mock,
    )

    response = client.post(
        "/tickets",
        json={
            "subject": "Unexpected API response test",
            "customer_email": "test@example.com",
            "product_area": "Billing",
        },
    )

    assert response.status_code == 201
    assert response.json()["domain_flag"] == "Unknown"
