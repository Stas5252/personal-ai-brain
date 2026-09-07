"""
Standalone Telegram Bot Runner for Personal AI Brain.
Full Parity + Superset over Yaishka:
- AUTOMATIC FIRST-LAUNCH ACQUAINTANCE (БРИФ / ЗНАКОМСТВО ПРИ ПЕРВОМ ВХОДЕ):
  Natural step-by-step interview (10 questions) or 1-shot voice introduction.
- ZERO FAKE TEMPLATES: Never invents names or mockups. Uses real user profile.
- Persistent One-Touch Action Menu (Reels, Objections, Moodboard, Price, Audit, Daily Routine)
- Real Gemini Vision photo critique (upload photo)
- Voice transcript deconstruction (send voice note)
- Ingestion of courses, PDFs, videos, and guides into Knowledge Factory (send document/video)
"""
import time
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any

from src.brain.config import TELEGRAM_BOT_TOKEN
from src.brain.channels.telegram_adapter import TelegramAdapter
from src.brain.engines.profile_engine import ProfileEngine
from src.brain.knowledge.factory import KnowledgeIngestionFactory

# Active onboarding sessions: {chat_id: session_id}
active_onboarding: Dict[str, str] = {}

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "🎯 Пройти бриф заново"}, {"text": "👤 Мой профиль"}],
        [{"text": "🎬 5 идей для Reels"}, {"text": "💬 Отработать возражение"}],
        [{"text": "📸 Мудборд съёмки"}, {"text": "🏷️ Упаковка прайса"}],
        [{"text": "🚀 Аудит шапки профиля"}, {"text": "💡 «Мне нечего выложить»"}]
    ],
    "resize_keyboard": True
}

STEP_REACTIONS = {
    1: "🤝 Приятно познакомиться!",
    2: "📸 Отличная ниша, зафиксировал!",
    3: "📍 Прекрасный город для съёмок!",
    4: "💼 Услуги записал в память.",
    5: "💰 Прайс принят, буду учитывать его при ответах клиентам.",
    6: "🎯 Портрет твоей аудитории сохранен.",
    7: "🎨 Запомнил твой визуальный почерк.",
    8: "🗣️ Тон общения принят — буду общаться именно так.",
    9: "🚫 Запомнил стоп-слова, никогда не буду их использовать."
}

def download_telegram_file(adapter: TelegramAdapter, file_id: str, suffix: str = ".jpg") -> Optional[Path]:
    try:
        url = f"{adapter.api_base}/getFile?file_id={file_id}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                return None
            remote_path = data["result"]["file_path"]

        from src.brain.config import DATA_DIR
        import uuid
        upload_dir = DATA_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        local_file = upload_dir / f"tg_{uuid.uuid4()}{suffix}"

        download_url = f"https://api.telegram.org/file/bot{adapter.bot_token}/{remote_path}"
        urllib.request.urlretrieve(download_url, str(local_file))
        return local_file
    except Exception as e:
        print(f"[!] Telegram file download error: {e}")
        return None

def run_polling():
    if not TELEGRAM_BOT_TOKEN:
        print("[!] TELEGRAM_BOT_TOKEN is not set in environment or .env file.")
        return

    adapter = TelegramAdapter(bot_token=TELEGRAM_BOT_TOKEN)
    profile_engine = ProfileEngine()
    knowledge_factory = KnowledgeIngestionFactory()

    print(f"[*] Starting Personal AI Brain Telegram Bot polling (token: {TELEGRAM_BOT_TOKEN[:10]}...)...")
    offset = 0

    while True:
        try:
            url = f"{adapter.api_base}/getUpdates?offset={offset}&timeout=20"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("ok"):
                    time.sleep(2)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message")
                    if not msg:
                        continue

                    chat_id = str(msg["chat"]["id"])
                    user_text = msg.get("text", "").strip()

                    # Check current profile status
                    current_prof = profile_engine.get_profile()
                    has_profile = bool(current_prof and current_prof.identity and len(current_prof.identity.strip()) > 0 and "Не настроен" not in current_prof.identity)

                    # --- MODE A: Onboarding In Progress ---
                    if chat_id in active_onboarding and user_text:
                        if user_text.lower() in ["/cancel", "отмена", "стоп"]:
                            active_onboarding.pop(chat_id, None)
                            adapter.send_message(chat_id, "Бриф приостановлен. Ты можешь продолжить в любой момент, написав /brief.", reply_markup=MAIN_KEYBOARD)
                            continue

                        session_id = active_onboarding[chat_id]
                        try:
                            res = profile_engine.answer_onboarding(session_id, user_text)
                            if res.get("completed"):
                                active_onboarding.pop(chat_id, None)
                                prof = res.get("profile", {})
                                adapter.send_message(
                                    chat_id,
                                    f"🎉 <b>Бриф успешно завершен! Очень приятно познакомиться!</b>\n\n"
                                    f"Твой профиль сохранен в долгосрочную память:\n"
                                    f"• <b>Фотограф:</b> {prof.get('identity')}\n"
                                    f"• <b>Город:</b> {prof.get('city')}\n"
                                    f"• <b>Ниша:</b> {prof.get('niche')}\n"
                                    f"• <b>Тон общения:</b> {prof.get('tone')}\n\n"
                                    f"Теперь я готов помогать тебе как персональный маркетолог и продюсер! Выбирай, с чего начнем:",
                                    parse_mode="HTML",
                                    reply_markup=MAIN_KEYBOARD
                                )
                            else:
                                nq = res.get("next_question", {})
                                progress = res.get("progress", "")
                                cur_step = int(progress.split("/")[0]) if "/" in progress else 1
                                prev_step = cur_step - 1
                                reaction = STEP_REACTIONS.get(prev_step, "✅ Принято!")

                                adapter.send_message(
                                    chat_id,
                                    f"{reaction}\n\n"
                                    f"📋 <b>Вопрос [{progress}]:</b>\n\n"
                                    f"{nq.get('question')}\n\n"
                                    f"<i>Пример: {nq.get('example')}</i>\n\n"
                                    f"💡 <i>(Можешь ответить текстом или наговорить голосовое 🎙️)</i>",
                                    parse_mode="HTML"
                                )
                            continue
                        except Exception as e:
                            print(f"[!] Onboarding error: {e}")
                            active_onboarding.pop(chat_id, None)

                    # --- COMMAND: /start or FIRST TIME GREETING ---
                    if user_text.startswith("/start") or (not has_profile and chat_id not in active_onboarding and not msg.get("document") and not msg.get("photo")):
                        # If profile is not yet completed: START ACQUAINTANCE IMMEDIATELY!
                        if not has_profile:
                            session, first_q = profile_engine.start_onboarding()
                            active_onboarding[chat_id] = session.session_id
                            greeting = (
                                "👋 <b>Привет! Я твой персональный AI-ассистент и маркетолог для фотографа.</b>\n\n"
                                "Я знаю всё о фотобизнесе: помогаю с контентом, сценариями Reels, подготовкой съемок, упаковкой прайса и переписками с клиентами.\n\n"
                                "В отличие от обычного ChatGPT, я не даю шаблонных советов, а работаю <b>строго под твой стиль, твои цены и твоих клиентов</b>.\n\n"
                                "Давай познакомимся, чтобы я всё запомнил! 🤝\n\n"
                                f"📋 <b>Вопрос [1/10]:</b>\n"
                                f"{first_q.question}\n\n"
                                f"<i>Пример: {first_q.example}</i>\n\n"
                                f"💡 <i>(Можешь написать текстом или просто наговорить голосовое сообщение 🎙️)</i>"
                            )
                            adapter.send_message(chat_id, greeting, parse_mode="HTML")
                            continue

                        # If profile is already configured
                        name_str = f", {current_prof.identity}" if current_prof.identity else ""
                        welcome = (
                            f"👋 С возвращением{name_str}! Я твой <b>Personal AI Brain</b>.\n\n"
                            f"Твой профиль: <b>{current_prof.niche}</b> ({current_prof.city}).\n\n"
                            f"⚡ <b>Выбирай действие в меню внизу или просто напиши свою задачу:</b>\n"
                            f"• 🎬 <b>5 идей для Reels</b> — сценарии с хуками для клиентов\n"
                            f"• 💬 <b>Отработать возражение</b> — ответы на «дорого», «мы подумаем»\n"
                            f"• 📸 <b>Мудборд съёмки</b> — палитра, схемы света, образы\n"
                            f"• 🏷️ <b>Упаковка прайса</b> — декомпозиция пакетов и защита ценности\n"
                            f"• 🚀 <b>Аудит шапки профиля</b> — конвертящее позиционирование\n"
                            f"• 💡 <b>«Мне нечего выложить»</b> — живые идеи из рутины фотографа\n\n"
                            f"📥 <i>Также присылай сюда фото на разбор или PDF/видео курсов для базы знаний!</i>"
                        )
                        adapter.send_message(chat_id, welcome, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- COMMAND: /brief or restart onboarding ---
                    if user_text.startswith("/brief") or user_text.startswith("/quiz") or "пройти бриф" in user_text.lower():
                        session, first_q = profile_engine.start_onboarding()
                        active_onboarding[chat_id] = session.session_id
                        adapter.send_message(
                            chat_id,
                            f"🎯 <b>Начинаем персональный бриф фотографа!</b>\n\n"
                            f"Отвечай на вопросы текстом или голосовыми. Для отмены напиши /cancel.\n\n"
                            f"📋 <b>Вопрос [1/10]:</b>\n\n"
                            f"{first_q.question}\n\n"
                            f"<i>Пример: {first_q.example}</i>",
                            parse_mode="HTML"
                        )
                        continue

                    # --- COMMAND: /profile or button ---
                    if user_text.startswith("/profile") or user_text.startswith("/me") or "мой профиль" in user_text.lower():
                        prof = profile_engine.get_profile()
                        adapter.send_message(
                            chat_id,
                            f"👤 <b>Твой профиль фотографа:</b>\n\n"
                            f"• Имя: <b>{prof.identity or 'Не задано'}</b>\n"
                            f"• Город: <b>{prof.city or 'Не задан'}</b>\n"
                            f"• Ниша: <b>{prof.niche or 'Не задана'}</b>\n"
                            f"• Жанры: {', '.join(prof.genres) if prof.genres else 'Не указаны'}\n"
                            f"• Тон общения: <i>{prof.tone}</i>\n"
                            f"• Запретные слова: {', '.join(prof.forbidden_words) if prof.forbidden_words else 'нет'}\n\n"
                            f"Чтобы обновить, нажми 🎯 Пройти бриф заново или надиктуй голосовое о себе.",
                            parse_mode="HTML",
                            reply_markup=MAIN_KEYBOARD
                        )
                        continue

                    # --- FAST ACTION: Reels ideas ---
                    if "5 идей для reels" in user_text.lower() or "идеи для reels" in user_text.lower() or "идеи для рилс" in user_text.lower():
                        adapter.send_message(chat_id, "🎬 Генерирую 5 сценариев для Reels с хуками под твою нишу...")
                        prompt = "Придумай 5 цепляющих сценариев для Reels с хуками в первые 2 секунды, которые привлекают реальных клиентов на съемку (а не других фотографов). Укажи: хук, визуальный ряд, текст и призыв к действию."
                        res = adapter.handle_text(user_id=chat_id, text=prompt)
                        adapter.send_message(chat_id, res.get("response", "Не удалось сформировать идеи."), reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- FAST ACTION: Objection handling ---
                    if user_text.strip() == "💬 Отработать возражение" or user_text.lower() == "отработать возражение":
                        info = (
                            "💬 <b>Разбор клиентского возражения:</b>\n\n"
                            "Какое возражение прислал клиент? Например:\n"
                            "• <i>«Спасибо, мы подумаем»</i>\n"
                            "• <i>«Это слишком дорого для нас»</i>\n"
                            "• <i>«Мы не умеем позировать и будем деревянными»</i>\n"
                            "• <i>«Муж не хочет фотографироваться»</i>\n"
                            "• <i>«А отдадите все исходники?»</i>\n\n"
                            "<b>Просто отправь мне текст сообщения клиента или скриншот переписки</b>, и я напишу тактичный ответ с заботой, без навязывания и без скидок!"
                        )
                        adapter.send_message(chat_id, info, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- FAST ACTION: Moodboard & Concept ---
                    if user_text.strip() == "📸 Мудборд съёмки" or user_text.lower() == "мудборд съемки":
                        info = (
                            "📸 <b>Разработка мудборда и концепции съёмки:</b>\n\n"
                            "Напиши кратко, какую съемку планируешь (локация, идея или стиль). Например:\n"
                            "• <i>«Индивидуальная в студии с жестким графичным светом»</i>\n"
                            "• <i>«Семейная съемка в осеннем парке/лесу»</i>\n"
                            "• <i>«Лавстори в кофейне и на вечерних улицах»</i>\n"
                            "• <i>«Кампейн для бренда одежды»</i>\n\n"
                            "И я соберу для тебя полную концепцию: световую схему, цветовую гамму, стиль в одежде, локации и шот-лист кадров!"
                        )
                        adapter.send_message(chat_id, info, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- FAST ACTION: Pricing Packaging ---
                    if "упаковка прайса" in user_text.lower() or "упаковать прайс" in user_text.lower():
                        adapter.send_message(chat_id, "🏷️ Составляю структуру пакетов услуг и ценностное позиционирование...")
                        prompt = "Помоги мне упаковать прайс-лист: предложи 3 понятных пакета (Базовый, Оптимальный, Премиум), обоснуй ценность каждого, чтобы клиенты не выбирали только самый дешевый, и дай совет по оформлению."
                        res = adapter.handle_text(user_id=chat_id, text=prompt)
                        adapter.send_message(chat_id, res.get("response", "Не удалось составить прайс."), reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- FAST ACTION: Profile Bio Audit ---
                    if "аудит шапки профиля" in user_text.lower() or "аудит профиля" in user_text.lower():
                        info = (
                            "🚀 <b>Аудит шапки профиля и позиционирования:</b>\n\n"
                            "Пришли текст своей текущей шапки (Bio) или ссылку на аккаунт. Я разберу её глазами клиента:\n"
                            "1. Понятно ли за 3 секунды, кто ты и в каком городе снимаешь?\n"
                            "2. В чем твое УТП и отличие от конкурентов?\n"
                            "3. Есть ли понятный призыв записаться?\n\n"
                            "И сразу предложу <b>3 продающих варианта шапки</b> под твою нишу!"
                        )
                        adapter.send_message(chat_id, info, parse_mode="HTML", reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- FAST ACTION: No content emergency ---
                    if "мне нечего выложить" in user_text.lower() or "нет идей" in user_text.lower():
                        adapter.send_message(chat_id, "💡 Достаю живые идеи из рутины и закулисья фотографа...")
                        prompt = "Мне нечего выложить сегодня в сторис и соцсети. Предложи 3 честных, вовлекающих сюжета из реального дня фотографа с хуками и визуалом."
                        res = adapter.handle_text(user_id=chat_id, text=prompt)
                        adapter.send_message(chat_id, res.get("response", "Не удалось составить идеи."), reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- 2. Documents & Videos (KNOWLEDGE INGESTION) ---
                    doc = msg.get("document")
                    video = msg.get("video")
                    if doc or video:
                        file_obj = doc or video
                        file_name = file_obj.get("file_name", "uploaded_file.pdf")
                        file_id = file_obj.get("file_id")
                        suffix = Path(file_name).suffix.lower() or (".mp4" if video else ".pdf")

                        adapter.send_message(
                            chat_id,
                            f"📥 <b>Получил файл «{file_name}»</b>.\n"
                            f"Начинаю обработку и индексацию в твою персональную базу знаний...",
                            parse_mode="HTML"
                        )

                        local_path = download_telegram_file(adapter, file_id, suffix=suffix)
                        if local_path and local_path.exists():
                            try:
                                source, chunks = knowledge_factory.ingest_file(local_path, title=file_name)
                                adapter.send_message(
                                    chat_id,
                                    f"✅ <b>Материал успешно изучен и сохранен!</b>\n\n"
                                    f"• Файл: <code>{file_name}</code>\n"
                                    f"• Смысловых фрагментов в базе: <b>{len(chunks)}</b>\n"
                                    f"• Слой знаний: <b>{source.layer.value if hasattr(source, 'layer') and source.layer else 'PROFESSIONAL'}</b>\n\n"
                                    f"Теперь ты можешь задавать вопросы по материалам этого курса или документа!",
                                    parse_mode="HTML",
                                    reply_markup=MAIN_KEYBOARD
                                )
                            except Exception as e:
                                adapter.send_message(chat_id, f"❌ Ошибка индексации: {e}", reply_markup=MAIN_KEYBOARD)
                        else:
                            adapter.send_message(chat_id, "Не удалось скачать файл из Telegram.", reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- 3. Photos (GEMINI VISION) ---
                    photos = msg.get("photo")
                    if photos:
                        caption = msg.get("caption") or "Проанализируй этот кадр: свет, позу, композицию и что можно улучшить."
                        adapter.send_message(chat_id, "🔍 Анализирую светотеневой рисунок, позу и композицию через Gemini Vision...")
                        best_photo = photos[-1]
                        file_id = best_photo["file_id"]
                        local_path = download_telegram_file(adapter, file_id, suffix=".jpg")
                        if local_path and local_path.exists():
                            res = adapter.handle_photo(user_id=chat_id, photo_path=local_path, caption=caption)
                            reply_text = res.get("response", "Не удалось проанализировать фото.")
                            adapter.send_message(chat_id, reply_text, reply_markup=MAIN_KEYBOARD)
                        else:
                            adapter.send_message(chat_id, "Не удалось загрузить фото из Telegram.", reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- 4. Voice / Audio ---
                    voice = msg.get("voice") or msg.get("audio")
                    if voice:
                        caption = msg.get("caption")
                        file_id = voice["file_id"]
                        suffix = ".ogg" if msg.get("voice") else ".mp3"
                        local_path = download_telegram_file(adapter, file_id, suffix=suffix)

                        if local_path and local_path.exists():
                            from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
                            ae = AudioExtractor()
                            t_res = ae.extract(local_path)
                            transcript_text = t_res.get("text", "")

                            # Check if user is in onboarding or voice brief
                            if chat_id in active_onboarding and transcript_text:
                                session_id = active_onboarding[chat_id]
                                res = profile_engine.answer_onboarding(session_id, transcript_text)
                                if res.get("completed"):
                                    active_onboarding.pop(chat_id, None)
                                    prof = res.get("profile", {})
                                    adapter.send_message(
                                        chat_id,
                                        f"🎉 <b>Бриф завершен по голосовому!</b>\n\n"
                                        f"• Имя: <b>{prof.get('identity')}</b>\n"
                                        f"• Город: <b>{prof.get('city')}</b>\n"
                                        f"• Ниша: <b>{prof.get('niche')}</b>\n\n"
                                        f"Я всё запомнил! Теперь я готов работать как твой личный маркетолог.",
                                        parse_mode="HTML",
                                        reply_markup=MAIN_KEYBOARD
                                    )
                                else:
                                    nq = res.get("next_question", {})
                                    progress = res.get("progress", "")
                                    adapter.send_message(chat_id, f"🎙️ <i>Услышал: «{transcript_text[:60]}...»</i>\n\n📋 <b>Вопрос [{progress}]:</b>\n{nq.get('question')}", parse_mode="HTML")
                                continue

                            # Check if voice note is a free-form self introduction (e.g. 1-minute express brief)
                            if not has_profile and transcript_text:
                                adapter.send_message(chat_id, "🎙️ Распознаю твой голосовой рассказ и настраиваю профиль...")
                                new_prof = profile_engine.parse_profile_from_freetext(transcript_text)
                                adapter.send_message(
                                    chat_id,
                                    f"🎉 <b>Очень приятно познакомиться! Я всё заполнил по твоему голосовому:</b>\n\n"
                                    f"• Фотограф: <b>{new_prof.identity}</b>\n"
                                    f"• Город: <b>{new_prof.city}</b>\n"
                                    f"• Ниша: <b>{new_prof.niche}</b>\n"
                                    f"• Тон: {new_prof.tone}\n\n"
                                    f"Теперь твой Brain готов к работе! Выбирай действие в меню внизу:",
                                    parse_mode="HTML",
                                    reply_markup=MAIN_KEYBOARD
                                )
                                continue

                            adapter.send_message(chat_id, "🎙️ Слушаю голосовую заметку и формирую контент-пак...")
                            res = adapter.handle_voice(user_id=chat_id, audio_path=local_path, caption=caption)
                            reply_text = res.get("response", "Не удалось разобрать голосовую заметку.")
                            adapter.send_message(chat_id, reply_text, reply_markup=MAIN_KEYBOARD)
                        else:
                            adapter.send_message(chat_id, "Не удалось загрузить аудиозапись.", reply_markup=MAIN_KEYBOARD)
                        continue

                    # --- 5. General Text Processing ---
                    if user_text:
                        print(f"[*] Incoming text from {chat_id}: {user_text[:60]}...")
                        # Check if user is telling about themselves to setup profile
                        if any(w in user_text.lower() for w in ["меня зовут", "мой бренд", "я фотограф из", "снимаю в городе"]):
                            adapter.send_message(chat_id, "⚙️ Распознаю твой рассказ и настраиваю профиль...")
                            new_prof = profile_engine.parse_profile_from_freetext(user_text)
                            adapter.send_message(
                                chat_id,
                                f"🎉 <b>Профиль фотографа успешно настроен!</b>\n\n"
                                f"• Имя: <b>{new_prof.identity}</b>\n"
                                f"• Город: <b>{new_prof.city}</b>\n"
                                f"• Ниша: <b>{new_prof.niche}</b>\n"
                                f"• Тон: {new_prof.tone}\n\n"
                                f"Теперь Brain настроен лично под тебя. Выбирай любое действие в меню!",
                                parse_mode="HTML",
                                reply_markup=MAIN_KEYBOARD
                            )
                            continue

                        res = adapter.handle_text(user_id=chat_id, text=user_text)
                        reply_text = res.get("response", "Не удалось сформировать ответ.")
                        adapter.send_message(chat_id, reply_text, reply_markup=MAIN_KEYBOARD)
                        continue

        except KeyboardInterrupt:
            print("\n[*] Stopping Telegram polling bot.")
            break
        except Exception as e:
            print(f"[!] Polling error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    run_polling()
