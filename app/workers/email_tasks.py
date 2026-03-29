from app.core.celery_worker import celery_app
from app.services.email_service import send_email

@celery_app.task
def send_email_task(to_email, subject, body):
    return send_email(to_email, subject, body)