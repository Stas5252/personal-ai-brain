"""Single-owner Telegram runner with typing indicator (v2).

KEY IMPROVEMENT: Shows 'typing...' animation while Brain processes request.
User always knows the bot is working — huge UX win vs dead silence.
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

log = logging.getLogger(__name__)
UPLOADS = DATA_DIR / 'uploads'

ACTIONS = {
    '🎥 Идеи Reels': 'Придумай 5 идей Reels под мою нишу: цепляющий хук в первые 3 секунды, визуальный ряд, текст на экране и CTA.',
    '💬 Ответ клиенту': 'Помоги ответить клиенту на сообщение или возражение. Попроси прислать скриншот или текст переписки.',
    '📸 Мудборд съёмки': 'Составь подробный мудборд съёмки: концепция, цветовая палитра из 5 HEX-оттенков, 7 сочетаний образов, локация, 5 идей кадров и блок «Важно ♡».',
    '✨ Разбор аккаунта': 'Сделай профессиональный аудит моего профиля или прислали скриншот: шапка, УТП, навигация актуального и шахматный ритм ленты.',
    '🔍 Разбор фото': 'Разбери эту фотографию по 5 аспектам: свет и тень, композиция и ракурс, поза и эмоция, цвет и скинтон, и 3 конкретных шага как сделать кадр в 2 раза сильнее.',
    '🎵 Подбор треков': 'Подбери 4-5 атмосферных трека для фотосессии, Reels или Stories с художественным объяснением.',
    '⚖️ Спорная ситуация': 'Помоги разобрать спорную или конфликтную ситуацию с клиентом: где моя просадка, где она перегибает и готовый скрипт ответа.',
    '📅 План дня': 'Что мне сегодня делать? Собери 3 главных приоритета (съёмки, клиенты, контент) без выдуманных событий.',
    '💰 Прайс-лист': 'Составь красивый прайс-лист по правилу трёх тарифов: ЛАЙТ, ОПТИМАЛЬНЫЙ и ПРЕМИУМ с наполнением, гарантиями и слоганом.',
    '📝 Контент-план': 'Составь контент-план на 7 дней: чередование рубрик (сторителлинг, экспертиза, бэкстейдж, продажи), форматы и хуки.',
}

KEYBOARD = {
    'keyboard': [
        [{'text': '🎥 Идеи Reels'}, {'text': '💬 Ответ клиенту'}],
        [{'text': '📸 Мудборд съёмки'}, {'text': '✨ Разбор аккаунта'}],
        [{'text': '🔍 Разбор фото'}, {'text': '🎵 Подбор треков'}],
        [{'text': '⚖️ Спорная ситуация'}, {'text': '📅 План дня'}],
        [{'text': '💰 Прайс-лист'}, {'text': '📝 Контент-план'}],
    ],
    'resize_keyboard': True
}


class TelegramHTTP:
    def __init__(self, token):
        self.base = 'https://api.telegram.org/bot' + token
        self.files = 'https://api.telegram.org/file/bot' + token + '/'

    def call(self, method, payload):
        request = urllib.request.Request(
            self.base + '/' + method,
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(request, timeout=40) as response:
            data = json.load(response)
        if not data.get('ok'):
            raise RuntimeError(f'Telegram rejected: {data}')
        return data['result']

    def send(self, chat, text, parse_mode: str = None):
        for offset in range(0, max(len(text), 1), 1800):
            payload = {
                'chat_id': chat,
                'text': text[offset:offset + 1800] or '...',
                'reply_markup': KEYBOARD
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
            with urllib.request.urlopen(self.files + remote['file_path'], timeout=60) as response:
                with target.open('xb') as output:
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE_SIZE_BYTES:
                            raise ValueError('Файл слишком большой.')
                        output.write(chunk)
            if not target.stat().st_size:
                raise ValueError('Получен пустой файл.')
            return target
        except BaseException:
            target.unlink(missing_ok=True)
            raise


class Bot:
    def __init__(self, api, brain, state, owner):
        self.api, self.brain, self.state, self.owner = api, brain, state, owner

    def reply(self, message):
        if not owner_allowed(message, self.owner):
            return None
        text = message.get('text', '').strip()
        caption = message.get('caption', '').strip()
        chat_id = message.get('chat', {}).get('id') or message.get('from', {}).get('id')
        session_key = f'onboarding:{self.owner}'
        profile = self.brain.profile_engine

        if text in ['/reset', '/start_over']:
            from src.brain.models.profile import UserProfile
            self.state.put(session_key, 'freeform')
            profile.save_profile(UserProfile())
            return (
                'Профиль полностью сброшен! 🔄\n\n'
                'Давай познакомимся с чистого листа. Напиши текстом или отправь голосовое:\n'
                '• Как тебя зовут?\n'
                '• В каком городе снимаешь?\n'
                '• Какая ниша и средний чек?\n'
                '• Главная цель на ближайшее время?'
            )

        if text == '/start':
            p = profile.get_profile()
            if p.identity and p.niche:
                return (
                    f'Привет, {p.identity}! Я твой личный ИИ-напарник по фотобизнесу. 📸\n\n'
                    f'Твой профиль: {p.niche} ({p.city or "город не указан"}).\n'
                    'Чем займёмся сегодня? Выбирай кнопку внизу или просто напиши голосовое!\n\n'
                    '📋 Команды: /profile | /brief | /reset'
                )
            self.state.put(session_key, 'freeform')
            return (
                'Привет! Я твой личный ИИ-напарник по фотобизнесу. 📸\n'
                'Давай познакомимся — напиши или отправь голосовое:\n\n'
                '• Как тебя зовут?\n'
                '• В каком городе снимаешь?\n'
                '• Твоя ниша и средний чек?\n'
                '• Главная цель на ближайшее время?'
            )

        if text == '/cancel':
            self.state.put(session_key, None)
            return 'Бриф остановлен. Начать заново: /brief или /reset. Посмотреть профиль: /profile.'

        if text == '/profile':
            p = profile.get_profile()
            prices_str = ', '.join([f'{k}: {v}' for k, v in (p.pricing or p.prices or {}).items()]) or 'не указан'
            goals_str = ', '.join(p.goals) if p.goals else 'не указаны'
            services_str = ', '.join(p.services) if p.services else 'не указаны'
            return (
                f'👤 Профиль фотографа:\n'
                f'• Имя: {p.identity or "не указано"}\n'
                f'• Город: {p.city or "не указан"}\n'
                f'• Ниша: {p.niche or "не указана"}\n'
                f'• Услуги: {services_str}\n'
                f'• Прайс: {prices_str}\n'
                f'• Тон: {p.tone or "Тёплый, искренний"}\n'
                f'• Цели: {goals_str}\n\n'
                'Обновить: /brief | Сбросить: /reset'
            )

        if text == '/brief':
            self.state.put(session_key, 'freeform')
            return (
                'Давай обновим твои данные! Отправь голосовое или напиши текстом:\n'
                'Кто ты, где и что снимаешь, цены и над чем сейчас работаешь?\n'
                '/cancel — отмена.'
            )

        if text in ['/знания', '/knowledge']:
            return (
                '📚 Загрузка материалов в базу знаний:\n\n'
                'Отправь мне файл (PDF, DOCX, PPTX, видео, аудио) — '
                'я изучу его и буду учитывать эти знания во всех ответах.'
            )

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
                    return 'Не удалось распознать речь. Проверь запись звука и повтори сообщение.'
                text = (caption + '\n' + result.raw_text).strip()

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
                    return 'Профиль сохранён! Теперь приступим к первой рабочей задаче.'
                return result['next_question']['question']

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
                    f'Теперь я учитываю эти знания во всех ответах!'
                )

            images = None
            if message.get('photo'):
                local = self.api.download(message['photo'][-1], '.jpg')
                images = [str(local)]
                c_low = (caption or '').lower()
                if any(w in c_low for w in ['профиль', 'аккаунт', 'шапк', 'лент', 'сетк', 'инста', 'хайлайт', 'аудит']):
                    text = caption or 'Сделай детальный аудит профиля и ленты по скриншоту.'
                elif any(w in c_low for w in ['спор', 'конфликт', 'клиент', 'переписк', 'претензи', 'диалог']):
                    text = caption or 'Помоги разобрать диалог с клиентом на скриншоте.'
                else:
                    text = caption or 'Разбери эту фотографию по 5 аспектам.'

            if not text:
                return 'Пришли текст, голосовое сообщение, фотографию или обучающий документ.'

            query = ACTIONS.get(text, text)
            result = process_request(
                self.brain, query, UPLOADS,
                images=images,
                conversation_history=self.state.get(f'history:{self.owner}', [])
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
        stored_owner = state.get('owner_id')
        if stored_owner and str(stored_owner).isdigit():
            owner = str(stored_owner)
        else:
            owner = ''

    api = TelegramHTTP(TELEGRAM_BOT_TOKEN)
    bot = Bot(api, BrainService(), state, owner)
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
                    # Start typing indicator
                    typing_stop = threading.Event()
                    if chat_id:
                        threading.Thread(
                            target=api.typing_loop,
                            args=(chat_id, typing_stop),
                            daemon=True
                        ).start()
                    try:
                        reply = bot.reply(msg) or ''
                    except (ValueError, RuntimeError) as exc:
                        reply = str(exc)
                    except Exception:
                        log.error('Processing failed for update %s', ident)
                        reply = 'Не удалось обработать запрос. Проверь настройки и повтори сообщение.'
                    finally:
                        typing_stop.set()  # Stop typing animation
                    state.put(cache_key, reply)

                if reply and bot.owner:
                    api.send(bot.owner, reply)
                state.finish(ident, True)
                state.put(cache_key, '')
            except Exception:
                state.finish(ident, False)
                log.error('Delivery failed for update %s (attempt %s)', ident, attempts + 1)

    thread = threading.Thread(target=worker, name='brain-worker', daemon=True)
    thread.start()
    log.info('🧠 Brain Telegram bot started. Waiting for messages...')
    try:
        while not stop.is_set():
            try:
                updates = api.call('getUpdates', {
                    'offset': state.get('offset', 0),
                    'timeout': 25,
                    'allowed_updates': ['message']
                })
                for update in updates:
                    msg = update.get('message', {})
                    if not bot.owner:
                        sender_id = msg.get('from', {}).get('id')
                        if msg.get('chat', {}).get('type') == 'private' and sender_id:
                            bot.owner = str(sender_id)
                            state.put('owner_id', bot.owner)
                            log.info('Auto-registered Telegram owner: %s', bot.owner)
                    if not owner_allowed(msg, bot.owner):
                        update = {'update_id': update['update_id']}
                    state.enqueue(update)
                if updates:
                    state.put('offset', updates[-1]['update_id'] + 1)
            except Exception:
                log.error('Telegram polling error; retrying in 3s...')
                stop.wait(3)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        thread.join(timeout=10)
        log.info('Bot stopped.')


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    run_polling()
