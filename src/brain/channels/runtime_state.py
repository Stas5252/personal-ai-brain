"""Durable single-owner transport state. No network dependencies."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def owner_allowed(message, owner_id):
    return bool(owner_id) and (
        message.get('chat', {}).get('type') == 'private'
        and str(message.get('from', {}).get('id', '')) == str(owner_id)
        and str(message.get('chat', {}).get('id', '')) == str(owner_id)
    )


def confined_file(value, root):
    root = Path(root).resolve()
    candidate = Path(value).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError('File must be an existing upload inside the upload directory.')
    return candidate


class RuntimeState:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS transport_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS telegram_inbox (
                    id INTEGER PRIMARY KEY, payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0);
            ''')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM transport_state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO transport_state VALUES (?,?)', (key, json.dumps(value)))

    def remember(self, user, query, response):
        key = f'history:{user}'
        history = self.get(key, [])
        history.extend([{'role': 'user', 'content': query}, {'role': 'assistant', 'content': response}])
        self.put(key, history[-12:])

    def enqueue(self, update):
        ident = int(update['update_id'])
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO telegram_inbox(id,payload) VALUES (?,?)',
                       (ident, json.dumps(update)))
            previous = db.execute("SELECT value FROM transport_state WHERE key='offset'").fetchone()
            offset = max(ident + 1, json.loads(previous[0]) if previous else 0)
            db.execute("INSERT OR REPLACE INTO transport_state VALUES ('offset',?)", (json.dumps(offset),))

    def next_update(self):
        with self.connect() as db:
            row = db.execute("SELECT id,payload,attempts,retry_at FROM telegram_inbox "
                             "WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
        if not row or row[3] > time.time():
            return None
        return row[0], json.loads(row[1]), row[2]

    def finish(self, ident, success):
        with self.connect() as db:
            if success:
                db.execute("UPDATE telegram_inbox SET status='done',payload='{}' WHERE id=?", (ident,))
            else:
                db.execute("UPDATE telegram_inbox SET attempts=attempts+1,retry_at=?,"
                           "status=CASE WHEN attempts>=2 THEN 'failed' ELSE 'pending' END WHERE id=?",
                           (time.time() + 15, ident))
            db.execute("DELETE FROM telegram_inbox WHERE status='done' AND id < "
                       "(SELECT COALESCE(MAX(id),0)-1000 FROM telegram_inbox)")


def process_request(brain, query, upload_root, images=None, audio_path=None, **kwargs):
    """Media failures stop the request instead of producing an invented answer."""
    import tempfile
    if audio_path:
        from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
        path = confined_file(audio_path, upload_root)
        with tempfile.TemporaryDirectory(prefix='brain-audio-') as derived:
            result = AudioExtractor().extract(path, 'voice', Path(derived))
        if not result.success or not result.raw_text.strip():
            raise ValueError('Не удалось распознать аудио. Проверь запись и установку Whisper/FFmpeg.')
        query += '\nТранскрипт пользователя:\n' + result.raw_text
    if len(images or []) > 4:
        raise ValueError('Прикрепи не больше четырёх фотографий за раз.')
    for image in images or []:
        path = confined_file(image, upload_root)
        result = brain.shooting_engine.critique_shot(str(path), prompt=query)
        if result.get('status') != 'AVAILABLE' or not result.get('description'):
            raise ValueError('Анализ изображения недоступен. Проверь ключ и доступность модели.')
        query += '\nРезультат анализа приложенного изображения:\n' + result['description']
    result = brain.process_chat(query=query, **kwargs)
    if result.get('status_code') != 200 or not result.get('response'):
        raise RuntimeError('Модель не ответила. Проверь ключ, квоту и выбранную модель, затем повтори запрос.')
    return result
