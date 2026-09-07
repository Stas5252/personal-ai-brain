"""Single-owner Telegram runner with durable inbox, history and honest failures."""
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
    '🎬 Идеи Reels': 'Придумай 5 идей Reels под мою нишу: цепляющий хук в первые 3 секунды, визуальный ряд, текст на экране и CTA.',
    '💬 Ответ клиенту': 'Помоги ответить клиенту на сообщение или возражение. Попроси прислать скриншот или текст переписки.',
    '📸 Подготовка съёмки': 'Помоги подготовить концепцию съёмки: уточни жанр, идею, локацию, и предложи схему света и референсы.',
    '✨ Мне нечего выложить': 'Мне кажется, что нечего выложить в блог. Предложи 3 свежих ракурса на основе моего опыта и съёмок.',
    '🔍 Разбор фото': 'Разбери мою фотографию: свет, композиция, эмоция, цвет и 3 конкретных шага, как сделать кадр в 2 раза сильнее.',
    '📅 План дня': 'Что мне сегодня делать? Собери 3 главных приоритета (съемки, клиенты, контент) без выдуманных событий.',
}
KEYBOARD = {
    'keyboard': [
        [{'text': '🎬 Идеи Reels'}, {'text': '💬 Ответ клиенту'}],
        [{'text': '📸 Подготовка съёмки'}, {'text': '✨ Мне нечего выложить'}],
        [{'text': '🔍 Разбор фото'}, {'text': '📅 План дня'}]
    ],
    'resize_keyboard': True
}


class TelegramHTTP:
    def __init__(self, token):
        self.base = f'https://api.telegram.org/bot{token}'
        self.files = f'https://api.telegram.org/file/bot{token}/'

    def call(self, method, payload):
        request = urllib.request.Request(self.base + '/' + method,
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=40) as response:
            data = json.load(response)
        if not data.get('ok'):
            raise RuntimeError('Telegram rejected the request.')
        return data['result']

    def send(self, chat, text):
        for offset in range(0, len(text), 1800):
            self.call('sendMessage', {'chat_id': chat, 'text': text[offset:offset + 1800],
                                      'reply_markup': KEYBOARD})

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
        session_key = f'onboarding:{self.owner}'
        profile = self.brain.profile_engine

        if text in ['/reset', '/start_over']:
            from src.brain.models.profile import UserProfile
            self.state.put(session_key, 'freeform')
            profile.save_profile(UserProfile())
            return (
                "Профиль полностью сброшен! 🔄\n\n"
                "Давай познакомимся с чистого листа. Напиши текстом или отправь голосовое:\n"
                "• Как тебя зовут?\n"
                "• В каком городе снимаешь?\n"
                "• Какая ниша (свадьбы, семьи, портреты, контент)?\n"
                "• Твой текущий чек и над чем сейчас работаешь?"
            )

        if text == '/start':
            p = profile.get_profile()
            if p.identity and p.niche:
                return (
                    f"Привет, {p.identity}! Я твой личный ИИ-напарник по фотобизнесу. 📸\n\n"
                    f"Твой профиль: {p.niche} ({p.city or 'город не указан'}).\n"
                    "Чем займемся сегодня? Выбирай кнопку внизу или просто наговори голосовое со съёмки!\n\n"
                    "Сбросить профиль и заполнить заново: /reset"
                )
            self.state.put(session_key, 'freeform')
            return (
                "Привет! Я твой личный ИИ-напарник по фотобизнесу. 📸\n"
                "Я обучен на полной базе курсов по фотографии (свет, продажи, закрытие возражений, Reels, Stories, мудборды и прайс).\n\n"
                "Давай познакомимся, чтобы я знал твои цели и стиль:\n\n"
                "Напиши текстом или отправь голосовое обычным языком:\n"
                "• Как тебя зовут?\n"
                "• В каком городе снимаешь?\n"
                "• Твоя ниша и средний чек?\n"
                "• Главная цель на ближайшее время?"
            )

        if text == '/cancel':
            self.state.put(session_key, None)
            return 'Бриф остановлен. Начать заново: /brief или /reset. Посмотреть профиль: /profile.'

        if text == '/profile':
            p = profile.get_profile()
            prices_str = ", ".join([f"{k}: {v}" for k, v in (p.prices or p.pricing or {}).items()]) or "не указан"
            goals_str = ", ".join(p.goals) if p.goals else "не указаны"
            return (
                f"👤 Профиль фотографа:\n"
                f"• Имя: {p.identity or 'не указано'}\n"
                f"• Город: {p.city or 'не указан'}\n"
                f"• Ниша: {p.niche or 'не указана'}\n"
                f"• Жанры: {', '.join(p.genres) if p.genres else 'не указаны'}\n"
                f"• Прайс: {prices_str}\n"
                f"• Тон общения: {p.tone or 'Теплый'}\n"
                f"• Цели: {goals_str}\n\n"
                f"Обновить профиль: отправь новое голосовое или напиши /brief."
            )

        if text == '/brief':
            self.state.put(session_key, 'freeform')
            return (
                "Давай обновим твои данные! Отправь голосовое или напиши текстом:\n"
                "Кто ты, где и что снимаешь, текущие цены и над какой задачей сейчас работаешь?\n"
                "/cancel — отмена."
            )

        local = None
        try:
            voice = message.get('voice') or message.get('audio')
            if voice:
                from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
                import tempfile
                local = self.api.download(voice, '.ogg' if message.get('voice') else Path(voice.get('file_name', 'voice.mp3')).suffix or '.mp3')
                with tempfile.TemporaryDirectory(prefix='brain-voice-') as derived:
                    result = AudioExtractor().extract(local, str(uuid.uuid4()), Path(derived))
                if not result.success or not result.raw_text.strip():
                    return 'Не удалось распознать речь. Проверь запись звука и повтори сообщение.'
                text = (caption + '\n' + result.raw_text).strip()

            session = self.state.get(session_key)
            # Free-form adaptive onboarding (like Yaishka)
            if session == 'freeform' and text:
                res = profile.extract_profile_from_freeform(text)
                if res.get('is_complete'):
                    self.state.put(session_key, None)
                    return res['friendly_summary']
                else:
                    return res['friendly_summary']

            # Step-by-step onboarding fallback if uuid session
            if session and session != 'freeform' and text:
                result = profile.answer_onboarding(session, text)
                if result.get('completed'):
                    self.state.put(session_key, None)
                    return 'Профиль сохранён! Теперь пришли первую рабочую задачу.'
                return result['next_question']['question']

            document = message.get('document') or message.get('video')
            if document:
                from src.brain.knowledge.factory import KnowledgeIngestionFactory
                filename = document.get('file_name') or ('video.mp4' if message.get('video') else 'document.bin')
                local = self.api.download(document, Path(filename).suffix.lower())
                source, chunks = KnowledgeIngestionFactory().ingest_file(local, title=filename)
                return f'Материал добавлен в базу знаний: {filename}. Обработано фрагментов: {len(chunks)}. Теперь я учитываю эти знания в ответах!'

            images = None
            if message.get('photo'):
                local = self.api.download(message['photo'][-1], '.jpg')
                images = [str(local)]
                text = caption or 'Разбери эту фотографию по 5 аспектам: свет и тень, композиция и ракурс, поза и эмоция, цвет и скинтон, и 3 шага как сделать кадр в 2 раза сильнее.'

            if not text:
                return 'Пришли текст, голосовое сообщение, фотографию или обучающий документ.'

            query = ACTIONS.get(text, text)
            result = process_request(self.brain, query, UPLOADS, images=images,
                                     conversation_history=self.state.get(f'history:{self.owner}', []))
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
            log.info('Loaded existing Telegram owner ID: %s', owner)
        else:
            owner = ''
            log.info('TELEGRAM_OWNER_ID is not configured. First user to send a private message will become the owner.')
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
                # Cache complete responses so a delivery retry does not call the LLM again.
                cache_key = f'reply:{ident}'
                reply = state.get(cache_key)
                if reply is None:
                    try:
                        reply = bot.reply(update.get('message', {})) or ''
                    except (ValueError, RuntimeError) as exc:
                        reply = str(exc)
                    except Exception:
                        log.error('Message processing failed for update %s', ident)
                        reply = 'Не удалось обработать запрос. Проверь настройки и повтори сообщение.'
                    state.put(cache_key, reply)
                if reply and bot.owner:
                    api.send(bot.owner, reply)
                state.finish(ident, True)
                state.put(cache_key, '')
            except Exception:
                state.finish(ident, False)
                log.error('Telegram delivery failed for update %s (attempt %s)', ident, attempts + 1)

    thread = threading.Thread(target=worker, name='brain-worker', daemon=True)
    thread.start()
    try:
        while not stop.is_set():
            try:
                updates = api.call('getUpdates', {'offset': state.get('offset', 0), 'timeout': 25,
                                                 'allowed_updates': ['message']})
                for update in updates:
                    msg = update.get('message', {})
                    if not bot.owner:
                        sender_id = msg.get('from', {}).get('id')
                        if msg.get('chat', {}).get('type') == 'private' and sender_id:
                            bot.owner = str(sender_id)
                            state.put('owner_id', bot.owner)
                            log.info('Auto-registered Telegram owner ID: %s', bot.owner)
                    if not owner_allowed(msg, bot.owner):
                        update = {'update_id': update['update_id']}
                    state.enqueue(update)
            except Exception:
                log.error('Telegram polling failed; check token, network and webhook configuration.')
                stop.wait(3)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        thread.join(timeout=10)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_polling()
