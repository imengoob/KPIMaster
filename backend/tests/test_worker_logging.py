from app.infrastructure.workers import tasks


def test_worker_logger_accepts_structured_fields():
    tasks.logger.info("worker_log_smoke", task="scan_tickets", reports_sent=1)
