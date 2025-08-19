import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, date, timezone


DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "advocacia.db"))


def _ensure_directory_exists(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _enable_foreign_keys(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON;")


@contextmanager
def get_connection():
    _ensure_directory_exists(DB_PATH)
    connection = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    try:
        _enable_foreign_keys(connection)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                whatsapp_number TEXT UNIQUE NOT NULL,
                full_name TEXT,
                email TEXT,
                case_summary TEXT,
                lead_priority TEXT CHECK(lead_priority IN ('ALTA','MÃ‰DIA','BAIXA')),
                creation_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reunioes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                google_calendar_event_id TEXT,
                meeting_datetime DATETIME,
                status TEXT CHECK(status IN ('MARCADA','REALIZADA','CANCELADA','FOLLOW-UP_ENVIADO')),
                creation_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clientes(id) ON DELETE CASCADE
            );
            """
        )

        # Indexes for performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clientes_whatsapp ON clientes(whatsapp_number);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reunioes_meeting_datetime ON reunioes(meeting_datetime);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reunioes_status ON reunioes(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reunioes_client_id ON reunioes(client_id);")


def upsert_client(whatsapp_number: str, full_name: str | None = None, email: str | None = None,
                  case_summary: str | None = None, lead_priority: str | None = None) -> int:
    """
    Insere ou atualiza um cliente pelo nÃºmero de WhatsApp. Retorna o client_id.
    """
    with get_connection() as conn:
        cursor = conn.execute("SELECT id FROM clientes WHERE whatsapp_number = ?", (whatsapp_number,))
        row = cursor.fetchone()
        if row is None:
            cursor = conn.execute(
                "INSERT INTO clientes (whatsapp_number, full_name, email, case_summary, lead_priority) VALUES (?,?,?,?,?)",
                (whatsapp_number, full_name, email, case_summary, lead_priority),
            )
            return cursor.lastrowid
        client_id = row[0]

        # Atualiza somente os campos fornecidos
        updates = []
        params: list[str | None] = []
        if full_name is not None:
            updates.append("full_name = ?")
            params.append(full_name)
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        if case_summary is not None:
            updates.append("case_summary = ?")
            params.append(case_summary)
        if lead_priority is not None:
            updates.append("lead_priority = ?")
            params.append(lead_priority)

        if updates:
            params.append(client_id)
            conn.execute(f"UPDATE clientes SET {', '.join(updates)} WHERE id = ?", params)

        return client_id


def get_client_by_whatsapp(whatsapp_number: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM clientes WHERE whatsapp_number = ?", (whatsapp_number,))
        return cur.fetchone()


def get_client_by_id(client_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM clientes WHERE id = ?", (client_id,))
        return cur.fetchone()


def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        # Assume naive datetimes are in UTC already
        return dt.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def add_meeting(client_id: int, google_calendar_event_id: str, meeting_datetime: datetime,
                status: str = 'MARCADA') -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO reunioes (client_id, google_calendar_event_id, meeting_datetime, status) VALUES (?,?,?,?)",
            (client_id, google_calendar_event_id, _to_utc_iso(meeting_datetime), status),
        )
        return cur.lastrowid


def update_meeting_status(meeting_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE reunioes SET status = ? WHERE id = ?", (status, meeting_id))


def get_future_meetings(start_from: datetime) -> list[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT r.*, c.full_name, c.whatsapp_number FROM reunioes r JOIN clientes c ON r.client_id = c.id "
            "WHERE r.meeting_datetime >= ? AND r.status = 'MARCADA' ORDER BY r.meeting_datetime ASC",
            (_to_utc_iso(start_from),),
        )
        return cur.fetchall()


def get_meetings_between(start_dt: datetime, end_dt: datetime) -> list[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT r.*, c.full_name, c.whatsapp_number FROM reunioes r JOIN clientes c ON r.client_id = c.id "
            "WHERE r.meeting_datetime BETWEEN ? AND ? AND r.status = 'MARCADA' ORDER BY r.meeting_datetime ASC",
            (_to_utc_iso(start_dt), _to_utc_iso(end_dt)),
        )
        return cur.fetchall()


def get_yesterday_meetings_to_followup(today: date | None = None) -> list[sqlite3.Row]:
    if today is None:
        today = datetime.utcnow().date()
    start = datetime.combine(today - timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)
    end = datetime.combine(today - timedelta(days=1), datetime.max.time()).replace(tzinfo=timezone.utc)
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT r.*, c.full_name, c.whatsapp_number FROM reunioes r JOIN clientes c ON r.client_id = c.id "
            "WHERE r.meeting_datetime BETWEEN ? AND ? AND r.status = 'MARCADA'",
            (_to_utc_iso(start), _to_utc_iso(end)),
        )
        return cur.fetchall()


