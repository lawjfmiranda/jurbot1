import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from ADV import database
from ADV import whatsapp_service


_scheduler: BackgroundScheduler | None = None


def _send_meeting_reminders():
    # Send reminders 24h before: find meetings in [now+24h, now+25h)
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    start = now + timedelta(hours=24)
    end = now + timedelta(hours=25)
    meetings = database.get_meetings_between(start, end)
    for m in meetings:
        name = m.get("full_name") or "Cliente"
        dt = datetime.fromisoformat(str(m["meeting_datetime"]).replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M")
        number = m["whatsapp_number"]
        text = (
            f"Olá {name}! Lembrando da nossa consulta agendada para {dt}. "
            "Se precisar reagendar, é só me avisar por aqui."
        )
        try:
            whatsapp_service.send_whatsapp_message(number, text)
        except Exception:
            pass


def _send_followups():
    meetings = database.get_yesterday_meetings_to_followup()
    for m in meetings:
        name = m.get("full_name") or "Cliente"
        number = m["whatsapp_number"]
        text = (
            f"Olá {name}! Passando para agradecer pela sua consulta de ontem. "
            "Esperamos que tenha sido produtiva. Se precisar de mais alguma informação ou desejar prosseguir, estamos à sua disposição."
        )
        try:
            whatsapp_service.send_whatsapp_message(number, text)
            database.update_meeting_status(m["id"], "FOLLOW-UP_ENVIADO")
        except Exception:
            pass


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=os.getenv("TIMEZONE", "America/Sao_Paulo"))
    # Run reminders hourly
    _scheduler.add_job(_send_meeting_reminders, "interval", minutes=30, id="meeting_reminders", replace_existing=True)
    # Daily followups at 09:00 local time
    _scheduler.add_job(_send_followups, "cron", hour=9, minute=0, id="daily_followups", replace_existing=True)
    _scheduler.start()


