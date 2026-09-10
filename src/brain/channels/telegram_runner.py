"""Telegram runner v3 — Yaishka-style 4-section bot.

New features vs v2:
  - 4 category sections: Content / Sales / Shoots / Promo
  - /library (библиотека) — prompt library with navigation
  - /uroki (уроки) — sequential AI mini-lessons
  - /help (помощь) — command reference
  - ReminderScheduler — inactivity reminders after 3 days
  - Smart photo-caption routing
  - last_activity tracking
"""
import json
import logging
import os
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from src.brain.config import DATA_DIR, TELEGRAM_BOT_TOKEN, MAX_FILE_SIZE_BYTES
from src.brain.channels.runtime_state import RuntimeState, owner_allowed, process_request
from src.brain.channels.bot_config import (
    ACTIONS, KEYBOARD_MAIN, CATEGORY_KEYBOARDS, CATEGORY_INTROS,
    ACTIONS_CONTENT, ACTIONS_SALES, ACTIONS_SHOOTS, ACTIONS_PROMO,
)
from src.brain.channels.bot_features import (
    MINI_LESSONS, REMINDER_MESSAGES,
    KEYBOARD_LIBRARY, LIBRARY_CATEGORY_MAP,
    ReminderScheduler, format_prompt_library_category, get_prompt_by_number,
)

log = logging.getLogger(__name__)
UPLOADS = DATA_DIR / 'uploads'


class TelegramHTTP:
    def __init__(self, token):
        self.base = 'https://api.telegram.org/bot' + token
        self.files_base = 'https://api.telegram.org/file/bot' + token + '/'

    def call(self, method, payload):
        request = urllib.request.Request(
            self.base + '/' + method,
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(request, timeout=40) as response:
            data = json.load(response)
        if not data.get('ok'):
            raise RuntimeError(f'Telegram rejected: {data}')
        return data['result']

    def send(self, chat, text, keyboard=None, parse_mode=None):
        kb = keyboard if keyboard is not None else KEYBOARD_MAIN
        for offset in range(0, max(len(text), 1), 1800):
            payload = {
                'chat_id': chat,
                'text': text[offset:offset + 1800] or '...',
                'reply_markup': kb,
            }
            if parse_mode:
                payload['parse_mode'] = parse_mode
            try:
                self.call('sendMessage', payload)
            except Exception:
                payload.pop('parse_mode', None)
                self.call('sendMessage', payload)

    def typing(self, chat):
        try:
            self.call('sendChatAction', {'chat_id': chat, 'action': 'typing'})
        except Exception:
            pass

    def typing_loop(self, chat, stop_event: threading.Event):
        while not stop_event.is_set():
            self.typing(chat)
            stop_event.wait(4.0)

    def download(self, file, suffix):
        if file.get('file_size', 0) > MAX_FILE_SIZE_BYTES:
            raise ValueError('Файл слишком большой для установленного лимита.')
        remote = self.call('getFile', {'file_id': file['file_id']})
        UPLOADS.mkdir(parents=True, exist_ok=True)
        target = UPLOADS / (uuid.uuid4().hex + suffix)
        try:
            with urllib.request.urlopen(self.files_base + remote['file_path'], timeout=60) as r:
                with target.open('xb') as out:
                    size = 0
                    while chunk := r.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE_SIZE_BYTES:
                            raise ValueError('Файл слишком большой.')
                        out.write(chunk)
            if not target.stat().st_size:
                raise ValueError('Получен пустой файл.')
            return target
        except BaseException:
            target.unlink(missing_ok=True)
            raise


class Bot:
    def __init__(self, api, brain, state, owner):
        self.api = api
        self.brain = brain
        self.state = state
        self.owner = owner

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #
    def _track_activity(self):
        self.state.put('last_activity', str(time.time()))
        self.state.put('reminder_sent_at', '')

    def _current_keyboard(self):
        cat = self.state.get(f'category:{self.owner}')
        if cat == 'library':
            return KEYBOARD_LIBRARY
        return CATEGORY_KEYBOARDS.get(cat, KEYBOARD_MAIN)

    # ------------------------------------------------------------------ #
    #  Main entry point
    # ------------------------------------------------------------------ #
    def reply(self, message):
        if not owner_allowed(message, self.owner):
            return None

        text = message.get('text', '').strip()
        caption = message.get('caption', '').strip()
        chat_id = (
            message.get('chat', {}).get('id')
            or message.get('from', {}).get('id')
        )
        session_key = f'onboarding:{self.owner}'
        profile = self.brain.profile_engine

        self._track_activity()

        # ---------------------------------------------------------------- #
        # NAVIGATION: main categories
        # ---------------------------------------------------------------- #
        if text in CATEGORY_INTROS:
            self.state.put(f'category:{self.owner}', text)
            intro = CATEGORY_INTROS[text]
            kb = CATEGORY_KEYBOARDS[text]
            self.api.send(chat_id, intro, keyboard=kb)
            return None  # already sent

        if text == '⬅️ Назад':
            self.state.put(f'category:{self.owner}', None)
            self.api.send(chat_id, 'Главное меню:', keyboard=KEYBOARD_MAIN)
            return None

        # ---------------------------------------------------------------- #
        # PROMPT LIBRARY navigation
        # ---------------------------------------------------------------- #
        if text == 'Назад' and self.state.get(f'category:{self.owner}') == 'library':
            self.state.put(f'category:{self.owner}', None)
            self.api.send(chat_id, 'Главное меню:', keyboard=KEYBOARD_MAIN)
            return None

        if text in LIBRARY_CATEGORY_MAP:
            cat_key = LIBRARY_CATEGORY_MAP[text]
            self.state.put(f'lib_cat:{self.owner}', cat_key)
            msg = format_prompt_library_category(cat_key)
            self.api.send(chat_id, msg, keyboard=KEYBOARD_LIBRARY)
            return None

        # Check if user types a number to get full library prompt
        lib_cat = self.state.get(f'lib_cat:{self.owner}')
        if lib_cat and text.isdigit():
            full_prompt = get_prompt_by_number(lib_cat, int(text))
            if full_prompt:
                self.api.send(chat_id, full_prompt, keyboard=KEYBOARD_LIBRARY)
                return None

        # ---------------------------------------------------------------- #
        # COMMANDS
        # ---------------------------------------------------------------- #
        if text in ['/reset', '/start_over']:
            from src.brain.models.profile import UserProfile
            self.state.put(session_key, 'freeform')
            self.state.put(f'category:{self.owner}', None)
            profile.save_profile(UserProfile())
            self.api.send(chat_id, (
                'Профиль полностью сброшен! 🔄\n\n'
                'Давай познакомимся с чистого листа. Напиши текстом или отправь голосовое:\n'
                '• Как тебя зовут?\n• Город?\n• Ниша и средний чек?\n• Главная цель?'
            ), keyboard=KEYBOARD_MAIN)
            return None

        if text == '/start':
            p = profile.get_profile()
            if p.identity and p.niche:
                self.api.send(chat_id, (
                    f'Привет, {p.identity}! Твой личный ИИ-напарник по фотобизнесу на базе ChatGPT. \ud83d\udcf8\n\n'
                    f'Твой профиль: {p.niche} ({p.city or "город не указан"}).\n'
                    'Выбирай раздел ниже или просто напиши голосовое!\n\n'
                    '📋 Команды: /profile | /brief | /library | /uroki | /help | /reset'
                ), keyboard=KEYBOARD_MAIN)
            else:
                self.state.put(session_key, 'freeform')
                self.api.send(chat_id, (
                    'Привет! Я твой личный ИИ-напарник по фотобизнесу на базе ChatGPT. \ud83d\udcf8\n'
                    'Давай познакомимся — напиши или отправь голосовое:\n\n'
                    '• Как тебя зовут?\n• Город?\n• Ниша и средний чек?\n• Главная цель?'
                ), keyboard=KEYBOARD_MAIN)
            return None

        if text == '/cancel':
            self.state.put(session_key, None)
            self.api.send(chat_id, 'Бриф остановлен. /brief — начать заново, /profile — посмотреть.', keyboard=KEYBOARD_MAIN)
            return None

        if text == '/profile':
            p = profile.get_profile()
            prices_str = ', '.join([f'{k}: {v}' for k, v in (p.pricing or p.prices or {}).items()]) or 'не указан'
            goals_str = ', '.join(p.goals) if p.goals else 'не указаны'
            services_str = ', '.join(p.services) if p.services else 'не указаны'
            self.api.send(chat_id, (
                '👤 Профиль фотографа:\n'
                f'• Имя: {p.identity or "не указано"}\n'
                f'• Город: {p.city or "не указан"}\n'
                f'• Ниша: {p.niche or "не указана"}\n'
                f'• Услуги: {services_str}\n'
                f'• Прайс: {prices_str}\n'
                f'• Цели: {goals_str}\n\n'
                'Обновить: /brief | Сбросить: /reset'
            ), keyboard=KEYBOARD_MAIN)
            return None

        if text == '/brief':
            self.state.put(session_key, 'freeform')
            self.api.send(chat_id, (
                'Давай обновим данные! Отправь голосовое или напиши текстом:\n'
                'Кто ты, где и что снимаешь, цены и над чем работаешь?\n/cancel — отмена.'
            ), keyboard=KEYBOARD_MAIN)
            return None

        if text in ['/знания', '/knowledge']:
            self.api.send(chat_id, (
                '📚 Загрузка материалов в базу знаний:\n\n'
                'Отправь мне файл (PDF, DOCX, PPTX, видео, аудио) — '
                'я изучу его и буду учитывать в ответах!'
            ), keyboard=KEYBOARD_MAIN)
            return None

        if text in ['/library', '/библиотека', '/biblioteka']:
            self.state.put(f'category:{self.owner}', 'library')
            self.api.send(chat_id, (
                '📚 Библиотека промптов\n\n'
                'Готовые промпты для любой задачи. Выбери категорию:'
            ), keyboard=KEYBOARD_LIBRARY)
            return None

        if text in ['/uroki', '/уроки', '/urok']:
            idx = int(self.state.get(f'lesson_idx:{self.owner}') or 0)
            lesson = MINI_LESSONS[idx % len(MINI_LESSONS)]
            self.state.put(f'lesson_idx:{self.owner}', str((idx + 1) % len(MINI_LESSONS)))
            total = len(MINI_LESSONS)
            self.api.send(chat_id, (
                f'🎓 {lesson["title"]} ({idx + 1}/{total})\n\n{lesson["body"]}\n\n'
                f'Следующий урок: /uroki'
            ), keyboard=KEYBOARD_MAIN)
            return None

        if text in ['/help', '/помощь', '/pomosh']:
            self.api.send(chat_id, (
                '📌 Команды:\n\n'
                '/start — запуск бота\n'
                '/profile — мой профиль\n'
                '/brief — обновить профиль\n'
                '/library — библиотека промптов\n'
                '/uroki — мини-уроки по работе с ИИ\n'
                '/reset — сбросить профиль\n'
                '/знания — загрузить материал (ПДФ, видео)\n'
                '/cancel — отмена ввода\n\n'
                '🎛️ Разделы в меню:\n'
                '✍️ Контент | 💰 Продажи | 📸 Съемки | 📢 Продвижение'
            ), keyboard=KEYBOARD_MAIN)
            return None

        # ---------------------------------------------------------------- #
        # MEDIA HANDLING
        # ---------------------------------------------------------------- #
        local = None
        try:
            voice = message.get('voice') or message.get('audio')
            if voice:
                from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
                import tempfile
                suffix = '.ogg' if message.get('voice') else (
                    Path(voice.get('file_name', 'voice.mp3')).suffix or '.mp3'
                )
                local = self.api.download(voice, suffix)
                with tempfile.TemporaryDirectory(prefix='brain-voice-') as derived:
                    result = AudioExtractor().extract(local, str(uuid.uuid4()), Path(derived))
                if not result.success or not result.raw_text.strip():
                    return 'Не удалось распознать речь. Проверь запись звука и повтори.'
                text = (caption + '\n' + result.raw_text).strip()

            # Onboarding session
            session = self.state.get(session_key)
            if session == 'freeform' and text:
                res = profile.extract_profile_from_freeform(text)
                if res.get('is_complete'):
                    self.state.put(session_key, None)
                return res['friendly_summary']

            if session and session != 'freeform' and text:
                result = profile.answer_onboarding(session, text)
                if result.get('completed'):
                    self.state.put(session_key, None)
                    return 'Профиль сохранён! Теперь приступим к первой задаче.'
                return result['next_question']['question']

            # Documents / video → knowledge base
            document = message.get('document') or message.get('video')
            if document:
                from src.brain.knowledge.factory import KnowledgeIngestionFactory
                filename = document.get('file_name') or (
                    'video.mp4' if message.get('video') else 'document.bin'
                )
                local = self.api.download(document, Path(filename).suffix.lower())
                source, chunks = KnowledgeIngestionFactory().ingest_file(local, title=filename)
                return (
                    f'✅ Материал добавлен в базу знаний: *{filename}*\n'
                    f'Обработано фрагментов: {len(chunks)}\n'
                    'Теперь я учитываю эти знания во всех ответах!'
                )

            # Photos
            images = None
            if message.get('photo'):
                local = self.api.download(message['photo'][-1], '.jpg')
                images = [str(local)]
                c_low = (caption or '').lower()
                if any(w in c_low for w in ['профиль', 'аккаунт', 'шапк', 'лент', 'сетк', 'инста', 'хайлайт', 'аудит']):
                    text = caption or 'Сделай детальный аудит профиля и ленты по скриншоту.'
                elif any(w in c_low for w in ['спор', 'конфликт', 'клиент', 'переписк', 'претензи', 'диалог']):
                    text = caption or 'Помоги разобрать диалог с клиентом на скриншоте.'
                elif any(w in c_low for w in ['прайс', 'цена', 'стоимость', 'тариф']):
                    text = caption or 'Помоги составить прайс-лист по трём тарифам.'
                else:
                    text = caption or 'Разбери эту фотографию по 5 аспектам: свет, композиция, поза, цвет, техника.'

            if not text:
                return 'Пришли текст, голосовое, фото или документ.'

            query = ACTIONS.get(text, text)
            result = process_request(
                self.brain, query, UPLOADS,
                images=images,
                conversation_history=self.state.get(f'history:{self.owner}', []),
            )
            self.state.remember(self.owner, query, result['response'])
            return result['response']

        finally:
            if local:
                local.unlink(missing_ok=True)


def run_polling():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError('Set TELEGRAM_BOT_TOKEN in .env before starting.')
    from src.brain.services.brain_service import BrainService

    state = RuntimeState(DATA_DIR / 'telegram_runtime.db')
    owner = os.environ.get('TELEGRAM_OWNER_ID', '').strip()
    if not owner.isdigit():
        stored = state.get('owner_id')
        if stored and str(stored).isdigit():
            owner = str(stored)
        else:
            owner = ''

    api = TelegramHTTP(TELEGRAM_BOT_TOKEN)
    bot = Bot(api, BrainService(), state, owner)

    # Start reminder scheduler
    reminder = ReminderScheduler(api, state, owner)
    reminder.start()

    stop = threading.Event()

    def worker():
        while not stop.is_set():
            pending = state.next_update()
            if not pending:
                stop.wait(0.5)
                continue
            ident, update, attempts = pending
            try:
                cache_key = f'reply:{ident}'
                reply = state.get(cache_key)
                if reply is None:
                    msg = update.get('message', {})
                    chat_id = (
                        msg.get('chat', {}).get('id')
                        or msg.get('from', {}).get('id')
                        or (int(bot.owner) if bot.owner else None)
                    )
                    typing_stop = threading.Event()
                    if chat_id:
                        threading.Thread(
                            target=api.typing_loop,
                            args=(chat_id, typing_stop),
                            daemon=True,
                        ).start()
                    try:
                        reply = bot.reply(msg)
                        if reply is None:
                            state.finish(ident, True)
                            state.put(cache_key, '')
                            continue
                    except (ValueError, RuntimeError) as exc:
                        reply = str(exc)
                    except Exception:
                        log.error('Processing failed for update %s', ident)
                        reply = 'Не удалось обработать запрос. Проверь настройки и повтори.'
                    finally:
                        typing_stop.set()
                    state.put(cache_key, reply)

                if reply and bot.owner:
                    kb = bot._current_keyboard()
                    api.send(bot.owner, reply, keyboard=kb)
                state.finish(ident, True)
                state.put(cache_key, '')
            except Exception:
                state.finish(ident, False)
                log.error('Delivery failed for update %s (attempt %s)', ident, attempts + 1)

    thread = threading.Thread(target=worker, name='brain-worker', daemon=True)
    thread.start()
    log.info('Brain Telegram bot v3 started (Yaishka-style).')

    try:
        while not stop.is_set():
            try:
                updates = api.call('getUpdates', {
                    'offset': state.get('offset', 0),
                    'timeout': 25,
                    'allowed_updates': ['message'],
                })
                for update in updates:
                    msg = update.get('message', {})
                    if not bot.owner:
                        sender_id = msg.get('from', {}).get('id')
                        if msg.get('chat', {}).get('type') == 'private' and sender_id:
                            bot.owner = str(sender_id)
                            state.put('owner_id', bot.owner)
                            reminder.owner = bot.owner
                            log.info('Auto-registered owner: %s', bot.owner)
                    if not owner_allowed(msg, bot.owner):
                        update = {'update_id': update['update_id']}
                    state.enqueue(update)
                if updates:
                    state.put('offset', updates[-1]['update_id'] + 1)
            except Exception:
                log.error('Polling error; retrying in 3s...')
                stop.wait(3)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        reminder.stop()
        thread.join(timeout=10)
        log.info('Bot stopped.')


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    run_polling()
