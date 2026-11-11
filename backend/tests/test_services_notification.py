import pytest
from unittest.mock import AsyncMock, patch

from app.services.notification_service import (
    NotificationService,
    Notification,
    NotificationSeverity,
    LogChannel,
    SlackChannel,
    EmailChannel,
)
from app.domain.value_objects.priority import EscalationLevel


@pytest.fixture
def override_settings(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "slack_webhook_url", "https://hooks.slack.com/services/T/B/X")


@pytest.mark.asyncio
async def test_log_channel_send():
    channel = LogChannel()
    notif = Notification(title="Test", body="Body", severity=NotificationSeverity.INFO)
    
    with patch("app.services.notification_service.logger.info") as mock_info:
        success = await channel.send(notif)
        assert success is True
        mock_info.assert_called_once()


@pytest.mark.asyncio
async def test_slack_channel_send_success():
    channel = SlackChannel("https://hooks.slack.com/services/T/B/X")
    notif = Notification(title="Test", body="Body", severity=NotificationSeverity.CRITICAL)
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Mocking the response context manager
        mock_resp = AsyncMock()
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp
        
        success = await channel.send(notif)
        assert success is True
        mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_slack_channel_send_failure_returns_false():
    channel = SlackChannel("https://fake.url")
    notif = Notification(title="Test", body="Body", severity=NotificationSeverity.WARNING)
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = Exception("HTTP Error")
        success = await channel.send(notif)
        assert success is False


@pytest.mark.asyncio
async def test_email_channel_send():
    channel = EmailChannel()
    
    # Missing email logic
    notif1 = Notification(title="T", body="B", severity=NotificationSeverity.INFO)
    assert await channel.send(notif1) is False
    
    # Valid email logic
    notif2 = Notification(title="T", body="B", severity=NotificationSeverity.INFO, recipient_emails=["test@example.com"])
    assert await channel.send(notif2) is True


@pytest.mark.asyncio
async def test_notification_service_send_fanout():
    ch1 = AsyncMock()
    ch1.name = "mock1"
    ch1.send.return_value = True
    
    ch2 = AsyncMock()
    ch2.name = "mock2"
    ch2.send.return_value = False
    
    svc = NotificationService(channels=[ch1, ch2])
    notif = Notification(title="T", body="B", severity=NotificationSeverity.INFO)
    
    results = await svc.send(notif)
    assert results == {"mock1": True, "mock2": False}
    ch1.send.assert_awaited_once_with(notif)
    ch2.send.assert_awaited_once_with(notif)


@pytest.mark.asyncio
async def test_notification_service_helpers():
    mock_ch = AsyncMock()
    mock_ch.name = "mock"
    mock_ch.send.return_value = True
    
    svc = NotificationService(channels=[mock_ch])
    
    await svc.notify_blocker_detected(
        ticket_title="T1", ticket_id=1, idle_hours=12.5, level=EscalationLevel.TEAM_LEAD
    )
    assert mock_ch.send.await_count == 1
    
    await svc.notify_daily_report(report_summary={"velocity": 30, "completion_rate": 0.8})
    assert mock_ch.send.await_count == 2
    
    await svc.notify_comment_blocker(ticket_title="T1", ticket_id=1, summary="Stuck")
    assert mock_ch.send.await_count == 3
    
    await svc.notify_unanswered_question(ticket_title="T1", ticket_id=1, hours_waiting=25.0)
    assert mock_ch.send.await_count == 4
    
    await svc.notify_discussion_threshold(ticket_title="T1", ticket_id=1, comment_count=15)
    assert mock_ch.send.await_count == 5
