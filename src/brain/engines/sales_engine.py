"""
Specialized Sales and Client Engine for Personal AI Brain.
Handles client conversation analysis, contextual objection handling,
pricing architecture, package optimization, and positioning audits.
"""
from typing import Dict, Any, List, Optional
from src.brain.models.client import Client, ClientStatus
from src.brain.models.profile import UserProfile

class SalesEngine:
    def __init__(self):
        pass

    def analyze_client_dialogue(self, dialogue_text: str, client: Optional[Client] = None, use_llm: bool = True) -> Dict[str, Any]:
        """
        Analyzes client messages from text or OCR screenshot via LLM.
        Identifies sales stage, emotional temperature, hidden objections, what client really means,
        drop-off point, and consultative response strategy.
        """
        d_lower = dialogue_text.lower().replace("ё", "е")
        
        # Detect objections (rule baseline)
        objections = []
        if "дорого" in d_lower or "скидк" in d_lower or "цен" in d_lower:
            objections.append("дорого")
        if "подума" in d_lower:
            objections.append("подумаем")
        if "посовет" in d_lower or "муж" in d_lower or "партнер" in d_lower:
            objections.append("посоветуемся")
        if "дешев" in d_lower:
            objections.append("нашли дешевле")
        if any(w in d_lower for w in ["позиров", "стесня", "не фотогеничн", "деревянн", "зажат", "скованн", "боюсь"]):
            objections.append("не умеем позировать")
        if "позже" in d_lower or "весной" in d_lower or "летом" in d_lower or "осенью" in d_lower:
            objections.append("позже")

        # Sales stage detection (rule baseline)
        if any(w in d_lower for w in ["оплат", "предоплат", "бронь", "карту", "счет", "чек"]):
            stage = ClientStatus.BOOKED
        elif objections:
            stage = ClientStatus.THINKING
        elif any(w in d_lower for w in ["сколько", "прайс", "пакет", "условия"]):
            stage = ClientStatus.PROPOSAL
        elif any(w in d_lower for w in ["здравствуйте", "привет", "добрый"]):
            stage = ClientStatus.CONTACTED
        else:
            stage = ClientStatus.INTERESTED

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                client_info = f"Имя клиента: {client.name}. Услуга: {client.service}." if client else "Клиент пока не идентифицирован."
                prompt = (
                    f"Ты — коммерческий наставник и психолог продаж для фотографов, как в лучших методиках фотобизнеса.\n"
                    f"Проанализируй диалог или сообщение клиента ({client_info}):\n"
                    f"«««\n{dialogue_text}\n»»»\n\n"
                    f"Задача:\n"
                    f"1. Выяви реальную стадию и скрытые сомнения (не только поверхностные слова).\n"
                    f"2. Объясни, что клиент имеет в виду на самом деле (страх камеры, непонимание ценности, страх неловкости, неуверенность в результате).\n"
                    f"3. Опиши риск потери сделки (где фотограф может всё испортить).\n"
                    f"4. Предложи стратегию ответа без давления, выпрашивания и моментального падения в скидки.\n"
                    f"5. Напиши 3 готовых варианта ответа:\n"
                    f"   - Мягкий и заботливый\n"
                    f"   - Уверенный и раскрывающий ценность\n"
                    f"   - Альтернативный (предложение более компактного формата или подборки)\n"
                    f"6. Укажи, чего категорически нельзя писать (анти-пример).\n\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект (без markdown блоков ```json):\n"
                    f"{{\n"
                    f'  "detected_stage": "{stage.value}",\n'
                    f'  "detected_objections": {json.dumps(objections, ensure_ascii=False)},\n'
                    f'  "emotional_temperature": "сомневающаяся / теплая / прохладная",\n'
                    f'  "what_client_really_means": "что скрывается за словами клиента",\n'
                    f'  "drop_off_point": "в чем главный риск потери клиента",\n'
                    f'  "recommended_strategy": "стратегия продолжения диалога",\n'
                    f'  "response_options": {{\n'
                    f'    "caring": "готовый текст ответа в кавычках",\n'
                    f'    "value_focused": "готовый текст ответа в кавычках",\n'
                    f'    "alternative": "готовый текст ответа в кавычках"\n'
                    f'  }},\n'
                    f'  "what_not_to_say": "чего говорить категорически нельзя",\n'
                    f'  "next_step": "следующее действие фотографа"\n'
                    f"}}"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.3)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "recommended_strategy" in parsed:
                        return parsed
            except Exception:
                pass

        # Fallback strategy
        if "дорого" in objections:
            strategy = "Раскрыть ценность подготовки и сервиса, не ронять цену сразу. Предложить гибкие условия или оптимизированный формат."
            what_means = "Клиент сравнивает с абстрактной суммой и пока не понимает, почему эта фотосессия изменит его состояние или бизнес."
            caring_resp = "Я вас прекрасно понимаю! Съёмка — это осознанное решение. Давайте я подробнее расскажу, как строится процесс и почему вам будет легко."
            val_resp = "В эту стоимость уже входит детальная подготовка мудборда, помощь со стилем и аренда студии, поэтому на самой съемке вам останется только наслаждаться."
            alt_resp = "Если хочется познакомиться с моим стилем в более компактном формате, мы можем сделать часовую экспресс-съемку на 25 кадров."
        elif "не умеем позировать" in objections:
            strategy = "Снять страх камеры. Объяснить процесс бережного ведения на съёмке: подсказываю каждое движение и ракурс."
            what_means = "Клиент боится выглядеть неловко, скованно или получить неудачные снимки."
            caring_resp = "Почти все мои герои говорят это перед съемкой! Вам совершенно не нужно уметь позировать — я направляю каждый шаг, движение и поворот головы."
            val_resp = "Моя задача как фотографа — создать расслабленную атмосферу и поймать ваши естественные живые эмоции в динамике."
            alt_resp = "Мы можем начать с чашки кофе в уютном кафе, чтобы вы привыкли ко мне и камере перед основной частью съёмки."
        elif "подумаем" in objections:
            strategy = "Мягко присоединиться, выяснить ключевое сомнение (дата, бюджет, формат) и оставить легкий открытый вопрос."
            what_means = "Клиент взял паузу из-за нерешенного сомнения или сравнивает с другими фотографами."
            caring_resp = "Конечно, не торопитесь! Если возникнут любые вопросы по образу или выбору дат — я всегда на связи."
            val_resp = "Понимаю! Если вы подбираете конкретную дату под повод, напишите мне, чтобы я успела забронировать за вами предварительную бронь."
            alt_resp = "Могу прислать вам короткий гайд по подготовке или подборку кадров в похожем стиле, чтобы было легче определиться."
        else:
            strategy = "Уточнить желаемую дату, повод для съёмки и помочь выбрать оптимальный пакет."
            what_means = "Клиент проявляет первичный интерес, но ему нужна помощь в выборе лучшего формата."
            caring_resp = "С удовольствием помогу всё спланировать! Расскажите, для чего планируете съемку — для себя, контента или семьи?"
            val_resp = "Мы подберем идеальную локацию и образ под вашу задачу, чтобы результат превзошел ожидания."
            alt_resp = "Если сложно выбрать пакет, я могу предложить 2 наиболее комфортных варианта под ваш запрос."

        return {
            "detected_stage": stage.value,
            "detected_objections": objections,
            "emotional_temperature": "теплая / сомневающаяся" if objections else "активная",
            "what_client_really_means": what_means,
            "drop_off_point": "Давление, попытка спорить или мгновенная скидка, обесценивающая работу фотографа.",
            "recommended_strategy": strategy,
            "response_options": {
                "caring": caring_resp,
                "value_focused": val_resp,
                "alternative": alt_resp
            },
            "what_not_to_say": "Не пишите 'У других еще дороже', 'Ну хотите сделаю скидку 50%?' или 'Так вы будете бронировать или нет?'.",
            "next_step": "Отправить клиенту один из 3 вариантов ответа и подождать реакции."
        }

    def generate_objection_response(
        self,
        objection_type: str,
        profile: Optional[UserProfile] = None,
        client: Optional[Client] = None,
        use_llm: bool = True
    ) -> str:
        """
        Generates bespoke, empathic responses to common photographer objections,
        dynamically personalized via LLM to the client's situation, service, and photographer's profile.
        """
        obj = objection_type.lower()
        c_name = client.name.strip() if client and client.name else ""
        c_service = client.service.strip() if client and client.service else ""
        niche = profile.niche if profile and profile.niche else "авторскую съемку"
        tone = profile.tone if profile and profile.tone else "Теплый, заботливый, без давления"

        if use_llm:
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                name_clause = f"Клиента зовут {c_name}." if c_name else "Имя клиента неизвестно."
                service_clause = f"Услуга: '{c_service}'." if c_service else "Услуга: съемка."
                prompt = (
                    f"Ты — фотограф ({niche}). Твой тон: {tone}.\n"
                    f"Клиент озвучил сомнение / возражение: «{objection_type}».\n"
                    f"{name_clause} {service_clause}\n\n"
                    f"Напиши один живой, искренний, заботливый ответ в Direct / мессенджер.\n"
                    f"Правила:\n"
                    f"- Никакого давления, манипуляций и канцелярита.\n"
                    f"- Присоединись к чувству клиента и покажи ценность подготовки/результата.\n"
                    f"- Закончи мягким открытым вопросом.\n"
                    f"Верни ТОЛЬКО текст ответа в кавычках."
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and len(text.strip()) > 30 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("«") and clean.endswith("»"):
                        return clean
                    return f"«{clean.strip('\"\'«»')}»"
            except Exception:
                pass

        if "дорого" in obj:
            service_mention = f" на {c_service}" if c_service else ""
            name_prefix = f"{c_name}, понимаю вас!" if c_name else "Понимаю вас!"
            budget_hint = f" Если есть комфортная для вас планка бюджета, мы можем адаптировать формат или время съемки." if client and client.budget else ""
            return (
                f"«{name_prefix} Выбор фотографа — это вложение, и важно быть на 100% уверенным в результате. "
                f"В стоимость{service_mention} входит не просто время с камерой: я полностью беру на себя концепцию, подбор образов, "
                f"помощь с локацией и мягкое ведение в кадре, чтобы вам не пришлось ни о чем переживать.{budget_hint} "
                f"Подскажите, какой формат съёмки для вас сейчас ближе всего? Мы можем подобрать комфортное решение»."
            )
        elif "подума" in obj:
            name_prefix = f"{c_name}, конечно, не торопитесь!" if c_name else "Конечно, не торопитесь!"
            return (
                f"«{name_prefix} Съёмка должна быть в удовольствие, поэтому важно всё взвесить. "
                f"Если у вас есть любые сомнения по локации, одежде или формату — я с радостью подскажу. "
                f"Кстати, на какую дату или месяц вы ориентируетесь, чтобы я проверила свободные окошки?»"
            )
        elif "не умеем позировать" in obj or "боимся камеры" in obj or "позиров" in obj:
            name_prefix = f"{c_name}, это" if c_name else "Это"
            return (
                f"«{name_prefix} абсолютно нормально! 95% моих героев приходят с этой фразой и никогда раньше не были на профессиональных съёмках. "
                f"Вам совершенно не нужно уметь позировать. Моя задача — включить приятную музыку, создать легкую атмосферу "
                f"и подсказывать каждое движение: куда посмотреть, как повернуться, куда деть руки. "
                f"Всё проходит легко, как обычная прогулка или встреча за кофе!»"
            )
        elif "посовет" in obj or "муж" in obj:
            name_prefix = f"{c_name}, прекрасно" if c_name else "Прекрасно"
            return (
                f"«{name_prefix} понимаю, семейные и парные съёмки здорово планировать вместе! "
                f"Давайте я пришлю вам короткую подборку кадров и несколько готовых концепций, чтобы вам было удобнее показать "
                f"и выбрать то, что откликнется обоим?»"
            )
        elif "дешев" in obj:
            return (
                f"«Да, предложений на рынке сейчас много, и здорово, что вы сравниваете. "
                f"Разница обычно кроется в уровне подготовки, авторской обработке, помощи с гардеробом и гарантии предсказуемого результата. "
                f"Для меня главное, чтобы вы получили кадры, которые захочется пересматривать спустя годы. "
                f"Буду рада сохранить для вас эту историю, если мой подход вам близок!»"
            )
        else:
            name_greeting = f"{c_name}, спасибо" if c_name else "Спасибо"
            return (
                f"«{name_greeting} за честную обратную связь! Буду рада ответить на любые вопросы и подобрать для вас идеальный вариант съёмки»."
            )

    def evaluate_pricing_ladder(self, packages: List[Dict[str, Any]], use_llm: bool = True) -> Dict[str, Any]:
        """
        Evaluates photographer's package structure (Basic, Optimal, Premium)
        and detects cannibalization or missing upsells.
        """
        if not packages:
            return {
                "status": "NO_DATA",
                "recommendations": ["Добавьте 3 ясных пакета: Минимальный (знакомство), Оптимальный (базовый выбор 70% клиентов), Премиум (максимум сервиса)."]
            }

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    "Ты — эксперт по ценообразованию и упаковке услуг фотографов.\n"
                    f"Проанализируй тарифную сетку фотографа:\n{json.dumps(packages, ensure_ascii=False, indent=2)}\n\n"
                    "Оцени:\n"
                    "1. Каннибализацию (не забирает ли младший тариф клиентов у среднего).\n"
                    "2. Ясность разделения ценности (почему средний выгоднее).\n"
                    "3. Апселлы и допродажи (фотокнига, срочность, стилист).\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    f'  "total_packages": {len(packages)},\n'
                    '  "issues_detected": ["проблема 1", "проблема 2"],\n'
                    '  "recommendations": ["рекомендация 1", "рекомендация 2"],\n'
                    '  "pricing_anchor_advice": "главный совет по ценовому якорю"\n'
                    "}"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.3)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "pricing_anchor_advice" in parsed:
                        return parsed
            except Exception:
                pass

        issues = []
        recommendations = []
        if len(packages) < 3:
            issues.append("Меньше 3 пакетов: клиент не видит контраста цен и сложнее ориентируется.")
            recommendations.append("Создайте трехпакетную линейку: Экспресс / Стандарт / Премиум.")

        # Check cannibalization: if package 1 offers too much
        p1 = packages[0]
        if p1.get("duration_hours", 1) >= 2 or p1.get("retouched_photos", 10) >= 30:
            issues.append("Первый (младший) пакет перегружен: клиентам незачем брать средний тариф.")
            recommendations.append("Сократите первый пакет до 40-50 минут и 15 кадров, чтобы Оптимальный тариф стал самым привлекательным.")

        recommendations.append("Добавьте апселлы: фотокнига в твердой обложке, ускоренная отдача за 48 часов, подбор стилиста.")

        return {
            "total_packages": len(packages),
            "issues_detected": issues,
            "recommendations": recommendations,
            "pricing_anchor_advice": "Сделайте средний пакет наиболее выгодным по соотношению времени и отдачи кадров."
        }

    def audit_profile_positioning(self, profile_text: str, profile_data: Optional[UserProfile] = None, use_llm: bool = True) -> Dict[str, Any]:
        """
        10-point account audit assessing clarity, positioning, CTA, and trust
        through the eyes of a potential photography client.
        """
        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                city_hint = f"Город: {profile_data.city}. Ниша: {profile_data.niche}." if profile_data else ""
                prompt = (
                    "Ты — требовательный потенциальный клиент и маркетолог фотографов.\n"
                    f"Посмотри на описание профиля / шапку фотографа ({city_hint}):\n"
                    f"«««\n{profile_text}\n»»»\n\n"
                    "Оцени глазами клиента за первые 3 секунды:\n"
                    "1. Понятно ли, кто это, что снимает, для кого, в каком городе и как записаться?\n"
                    "2. Есть ли отстройка от сотен других фотографов или сплошные клише?\n"
                    "3. Поставь честную оценку от 1 до 10.\n"
                    "4. Дай 3-4 конкретные рекомендации по улучшению конверсии.\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    '  "score": 8,\n'
                    '  "clarity": "Высокая / Средняя / Низкая",\n'
                    '  "detected_strengths": ["сильная сторона 1", "сильная сторона 2"],\n'
                    '  "recommendations": ["рекомендация 1", "рекомендация 2", "рекомендация 3"],\n'
                    '  "first_3_seconds_verdict": "вердикт первых 3 секунд"\n'
                    "}"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.3)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "score" in parsed and "first_3_seconds_verdict" in parsed:
                        return parsed
            except Exception:
                pass

        p_lower = profile_text.lower().replace("ё", "е")
        has_geo = any(w in p_lower for w in ["москва", "спб", "питер", "город", "мск", "сочи"])
        has_genre = any(w in p_lower for w in ["портрет", "свадеб", "семейн", "love story", "контент", "женск"])
        has_cta = any(w in p_lower for w in ["запис", "директ", "ссылк", "бронь", "пиши", "tg", "telegram"])
        has_value = any(w in p_lower for w in ["раскрываю", "без поз", "настоящие", "атмосфер", "эмоции", "кино"])

        score = 6
        if has_geo: score += 1
        if has_genre: score += 1
        if has_cta: score += 1
        if has_value: score += 1

        recommendations = []
        if not has_geo:
            recommendations.append("Укажите город в первой строке описания — клиенты сразу ищут локацию.")
        if not has_genre:
            recommendations.append("Четко сформулируйте вашу нишу (например, 'Кинематографичные женские портреты без заученных поз').")
        if not has_cta:
            recommendations.append("Добавьте явный призыв к действию: 'Запись на сезон в Direct' или ссылку на сайт/портфолио.")
        if not has_value:
            recommendations.append("Сформулируйте ценность: почему именно к вам (бережная атмосфера, помощь с гардеробом, готовые фото за 5 дней).")

        return {
            "score": min(score, 10),
            "clarity": "Высокая" if score >= 8 else "Средняя",
            "detected_strengths": ["Живой авторский слог", "Узнаваемый стиль"],
            "recommendations": recommendations,
            "first_3_seconds_verdict": "Клиент за 3 секунды должен понять: Кто вы, Что снимаете, Где и как записаться."
        }

    def handle_objection_yaishka_style(
        self,
        objection_text: str,
        client_name: Optional[str] = None,
        service: Optional[str] = None,
        base_price: Optional[int] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Handles client objections (price, husband/partner, fear of posing) using Yaishka's signature methodology:
        1. Empathic emotional validation with emoji 🤍.
        2. Strict price and professional boundary protection (zero discounting on core service).
        3. Rule of Two Choices: offer exactly TWO comfortable alternatives.
        4. Warm open-door closing.
        5. Methodological advice for the photographer explaining the psychological mechanism.
        Matches Yaishka screens 08 & 11.
        """
        c_name = client_name or "Имя"
        serv = service or "семейную съёмку"
        price_clause = f"Базовый пакет: {base_price} ₽." if base_price else ""
        obj_lower = objection_text.lower().replace("ё", "е")

        is_partner = any(w in obj_lower for w in ["муж", "партнер", "посовет", "советоваться", "парень", "супруг"])
        is_posing = any(w in obj_lower for w in ["позиров", "деревянн", "бревн", "боюсь камер", "стесня", "не уме", "зажат", "скованн", "не фотогеничн"])
        obj_category = "partner" if is_partner else ("fear_of_posing" if is_posing else "budget")

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                if is_partner:
                    specific_guidance = (
                        "Возражение: 'надо посоветоваться с мужем/партнером'.\n"
                        "Методология: валидируй совместное решение. Мужчины боятся, что их заставят неестественно позировать 2 часа. "
                        "Предложи два комфортных выбора: (1) короткий 1-минутный мудборд с атмосферой для мужа, "
                        "(2) опция, где муж участвует только первые 15-20 минут для общих кадров, а остальное время посвящено клиентке."
                    )
                elif is_posing:
                    specific_guidance = (
                        "Возражение: страх камеры / 'не умею позировать, деревянная'.\n"
                        "Методология: скажи, что 95% героев говорят это перед съемкой 🤍. Сними ответственность: позирование — на 100% задача фотографа. "
                        "Никаких застывших поз, только жизнь, динамика, музыка и кофе. "
                        "Предложи два комфортных выбора: (1) адаптационный старт за чашкой кофе, (2) заранее собранный персональный мудборд легких поз в движении."
                    )
                else:
                    specific_guidance = (
                        "Возражение по цене / бюджету.\n"
                        "Методология: защищай ценность, не давай скидок. Примени 'Правило двух выборов': "
                        "(1) мини-съемка в более коротком формате [длительность, стоимость, сколько фото], "
                        "(2) сохранить основной формат с делением оплаты на 2 части / через сервис 'Долями'."
                    )

                prompt = (
                    f"Ты — опытный наставник по продажам для фотографов в сервисе «Яишка».\n"
                    f"Клиент ({c_name}) озвучил сомнение по поводу {serv} ({price_clause}):\n"
                    f"«««\n{objection_text}\n»»»\n\n"
                    f"{specific_guidance}\n\n"
                    "Оформи ответ строго в виде двух карточек:\n"
                    "Карточка 1: Эмпатичное сообщение клиентке с эмодзи 🤍 и открытой дверью.\n"
                    "Карточка 2: Методический совет фотографу (почему именно так и психологический эффект).\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    '  "client_message": "готовый текст сообщения для отправки клиенту с эмодзи 🤍",\n'
                    '  "methodological_advice": "методический совет фотографу",\n'
                    '  "example_numbers_breakdown": "пример расчета или вариантов",\n'
                    '  "what_not_to_say": "чего категорически нельзя писать",\n'
                    f'  "objection_category": "{obj_category}"\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.4)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "client_message" in parsed:
                        return parsed
            except Exception:
                pass

        if is_partner:
            client_msg = (
                f"{c_name}, это замечательно, когда такие решения принимаются вместе! 🤍 "
                f"Понимаю вас: для мужчин съёмка часто кажется чем-то утомительным и сложным.\n\n"
                f"Чтобы мужу было проще определиться и не переживать, могу предложить два комфортных варианта:\n\n"
                f"• я пришлю короткий визуальный мудборд на 1 минуту с настроением и атмосферой — чтобы он увидел, что всё проходит легко, живо и без мучительного застывания в позах;\n\n"
                f"• либо мы можем спланировать съёмку так, чтобы муж поучаствовал только первые 15–20 минут (сделаем тёплые общие кадры), а остальное время посвятим индивидуальным портретам для вас.\n\n"
                f"Посоветуйтесь спокойно, а если останутся любые вопросы по процессу — я всегда на связи 🤍"
            )
            advice = (
                "Партнёры обычно боятся двух вещей: что их заставят неестественно позировать часами и что это будет неловко. "
                "Никогда не обесценивайте мужа фразами 'Решайте сами' или 'А что он решает?'. Дайте клиентке лёгкие аргументы для диалога дома: "
                "понимание, что мужчине не придётся страдать 2 часа, и опцию экспресс-участия на 15 минут."
            )
            return {
                "client_message": client_msg,
                "methodological_advice": advice,
                "example_numbers_breakdown": "Опция 1: 1-минутный мудборд для мужа; Опция 2: 15–20 минут совместных кадров + индивидуальная съемка клиентки.",
                "what_not_to_say": "Не пишите: 'Мужчины всё равно ничего не понимают в фотосессиях' или 'Вы же для себя снимаете, решайте сами'.",
                "objection_category": "partner"
            }

        if is_posing:
            client_msg = (
                f"{c_name}, понимаю вас, правда 🤍 Вы даже не представляете, как часто я это слышу — 95% моих героев говорят ровно то же самое перед первой съемкой!\n\n"
                f"Вам вообще не нужно уметь позировать — это на 100% моя профессиональная работа и забота. "
                f"Мы не будем стоять в напряжённых искусственных позах. Мы включим вашу любимую музыку, возьмём кофе, будем двигаться, общаться и смеяться. Я бережно подскажу каждое движение, поворот головы и куда деть руки.\n\n"
                f"Чтобы вам было максимально спокойно, предложу два комфортных варианта:\n\n"
                f"• начать съёмку с короткой 20-минутной прогулки за чашкой кофе, чтобы привыкнуть ко мне и атмосфере без направленной в упор камеры;\n\n"
                f"• либо я заранее соберу для вас персональный мудборд простых, естественных движений в динамике, где вы будете чувствовать себя абсолютно свободно.\n\n"
                f"Вы прекрасны в своей настоящести, а моя задача — бережно поймать это в кадре 🤍"
            )
            advice = (
                "Клиентки боятся показаться неуклюжими, глупыми или разочароваться в полученных фото. "
                "Никогда не говорите банальное 'Просто расслабьтесь' — эта фраза вызывает обратный эффект и усиливает зажим. "
                "Заберите всю ответственность за позы на себя, гарантируйте ведение каждого шага и предложите адаптивный старт (кофе, прогулка, музыка)."
            )
            return {
                "client_message": client_msg,
                "methodological_advice": advice,
                "example_numbers_breakdown": "Формат 1: кофе-брейк и мягкая адаптация; Формат 2: заранее подготовленный мудборд простых поз в динамике.",
                "what_not_to_say": "Не пишите: 'Просто расслабьтесь перед камерой' (усиливает зажим) или 'Да у меня даже деревянные получаются красиво' (звучит оскорбительно).",
                "objection_category": "fear_of_posing"
            }

        # Budget / Price objection (default Yaishka methodology)
        client_msg = (
            f"{c_name}, понимаю вас, правда 🤍 Иногда съёмку очень хочется, но именно сейчас бюджет не позволяет — это абсолютно нормально.\n\n"
            f"Чтобы не откладывать {serv} совсем, могу предложить два более комфортных варианта:\n\n"
            f"• мини-съёмку в более коротком формате — 30 минут, 15 кадров в авторской ретуши за более комфортную сумму;\n\n"
            f"• либо оставить основной формат, но разделить оплату на части: например, внести небольшую предоплату для брони даты сейчас, а остаток — в день съёмки или двумя равными платежами (также доступна оплата частями через сервис 'Долями').\n\n"
            f"Посмотрите, какой вариант вам был бы удобнее. А если пока неактуально — оставайтесь со мной, я периодически провожу фотодни и короткие форматы, возможно, один из них вам идеально подойдёт 🤍"
        )
        advice = (
            "Я бы не предлагал клиентке сразу всё подряд. Лучше дать максимум два выбора: короткий формат и оплату частями. "
            "Так сообщение остаётся заботливым, а не превращается в меню из десяти способов 'ну пожалуйста, купите'."
        )
        return {
            "client_message": client_msg,
            "methodological_advice": advice,
            "example_numbers_breakdown": "Для пакета за 15 000 ₽: экспресс-формат на 30 мин за 7 500 ₽ либо сохранение полного пакета с делением на 2 платежа по 7 500 ₽.",
            "what_not_to_say": "Не пишите 'Сделаю вам скидку прямо сейчас' (обесценивает труд) или 'У других еще дороже' (звучит токсично).",
            "objection_category": "budget"
        }

    def handle_cancellation_and_reschedule(
        self,
        cancellation_text: str,
        client_name: Optional[str] = None,
        profile: Optional[UserProfile] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Handles client shoot cancellations, weather force-majeure, and illness reschedules
        using Yaishka's signature client-service mediation methodology:
        1. Empathic validation without guilt-tripping or passive aggression.
        2. Deposit retention policy: deposit holds the reserved exclusive time slot.
        3. 30-60 day reschedule window: 100% transfer of deposit to a new date or indoor studio backup.
        4. Methodological advice and boundary protection for the photographer.
        """
        c_name = client_name or "Имя"
        q_lower = cancellation_text.lower().replace("ё", "е")

        is_weather = any(w in q_lower for w in ["погод", "дождь", "ливень", "непогод", "гроза", "ветер", "шторм", "холод", "слякоть", "сыро"])
        is_illness = any(w in q_lower for w in ["заболе", "простуд", "температур", "вирус", "болеет", "дети заболели", "ребенок заболел", "плохо себя чувствую", "лежу с температурой"])

        cancellation_type = "weather" if is_weather else ("illness" if is_illness else "late_cancellation")

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                prompt = (
                    f"Ты — опытный юрист и сервисный медиатор для фотографов в сервисе «Яишка».\n"
                    f"Клиент ({c_name}) написал сообщение об отмене или переносе съёмки (тип: {cancellation_type}):\n"
                    f"«««\n{cancellation_text}\n»»»\n\n"
                    "Сформируй эталонное антикризисное решение по методологии Яишки:\n"
                    "1. Тёплая эмпатичная валидация клиентки с эмодзи 🤍 (без обвинений и обиды).\n"
                    "2. Чёткая и вежливая фиксация политики задатка: задаток сохраняется за клиентом и в полном объеме переносится на новую дату в течение 30–60 дней (либо студийная альтернатива при дожде).\n"
                    "3. Методический совет фотографу: как защитить границы, избежать конфликтов и почему правило переноса на 30–60 дней выгодно обеим сторонам.\n"
                    "4. Чего категорически нельзя писать (анти-примеры).\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    f'  "cancellation_type": "{cancellation_type}",\n'
                    '  "client_message": "готовый текст сообщения для отправки клиентке с эмодзи 🤍",\n'
                    '  "deposit_policy_explanation": "объяснение политики сохранения задатка и окна переноса на 30-60 дней",\n'
                    '  "methodological_advice": "совет фотографу по ведению переговоров и защите границ",\n'
                    '  "what_not_to_say": "чего категорически нельзя писать клиенту"\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.4)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "client_message" in parsed:
                        return parsed
            except Exception:
                pass

        if is_weather:
            msg = (
                f"{c_name}, понимаю вас, правда 🤍 Съемка под дождем или в сырость — это совсем не то настроение, "
                f"которое мы задумывали, и вы абсолютно правы, что не хотите мокнуть и мерзнуть.\n\n"
                f"Погода — это форс-мажор, поэтому ваш задаток ни в коем случае не сгорает. У нас есть два отличных решения:\n\n"
                f"• перенести съемку на сухой солнечный день в течение ближайших 30–60 дней с полным сохранением задатка;\n\n"
                f"• либо, если образ и макияж уже готовы, перенести съемку в уютную светлую студию или крытую оранжерею без изменения даты.\n\n"
                f"Посмотрите, какой вариант вам ближе, и мы сразу закрепим удобное решение 🤍"
            )
            policy = "При погодном форс-мажоре задаток в 100% объеме сохраняется за клиентом и переносится на новую дату съемки в течение 30–60 дней (либо бронь переносится в крытую студию)."
            advice = "Погода не зависит ни от вас, ни от клиента. Не заставляйте героиню сниматься под ливнем ради галочки — результат будет испорчен. Предложите два четких выбора: комфортный перенос на 30–60 дней или теплая интерьерная студия."
            what_not = "Не пишите: 'Дождь съемке не помеха', 'Задаток сгорит если не придете', или 'Сами выбрали открытую локацию'."
        elif is_illness:
            msg = (
                f"{c_name}, самое главное сейчас — ваше здоровье и восстановление! 🤍 "
                f"В болезненном состоянии съемка превратится в тяжелое испытание, а нам нужны ваши искренние улыбки, силы и легкость.\n\n"
                f"Пожалуйста, не переживайте о съемке: ваш задаток в полном объеме сохраняется за вами. "
                f"Мы спокойно выберем новую дату в интервале 30–60 дней, как только вы полностью поправитесь и почувствуете себя отлично.\n\n"
                f"Выздоравливайте скорее и отдыхайте 🤍"
            )
            policy = "При болезни клиента задаток в полном объеме сохраняется за клиентом, замораживается и гарантированно переносится на новую дату в течение 30–60 дней."
            advice = "Больной клиент на съемке — худший сценарий: потухший взгляд, риск осложнений и испорченные воспоминания. Проявите искреннюю заботу. Окно переноса в 30–60 дней дает клиенту время спокойно долечиться без стресса 'успеть за 3 дня'."
            what_not = "Не пишите: 'А может выпьете таблетку и приедете?', 'Справка от врача есть?', или 'Задаток возврату не подлежит'."
        else:
            msg = (
                f"{c_name}, спасибо большое, что предупредили заранее! 🤍 "
                f"Мне очень жаль, что у вас изменились обстоятельства, ведь я уже забронировала это съемочное время эксклюзивно за вами.\n\n"
                f"По правилам бронирования задаток удерживается для компенсации забронированного слота, но чтобы вы не теряли средства, "
                f"я с удовольствием сохраню его за вами и перенесу съемку на любую удобную свободную дату в течение ближайших 30–60 дней.\n\n"
                f"Напишите мне, когда вам будет комфортно встретиться и какой месяц/неделю рассматриваем 🤍"
            )
            policy = "Задаток выполняет функцию гарантии бронирования времени съемки и не возвращается наличными при отмене по инициативе клиента, но полностью засчитывается при переносе съемки в течение 30–60 дней."
            advice = "Твердо держите правило задатка: если вы начнете возвращать деньги за отмененные в последний момент слоты, бизнес фотографа станет убыточным. Перенос на 30–60 дней — это идеальный баланс твердых границ и высокого клиентского сервиса."
            what_not = "Не пишите: 'Вы сорвали мне весь рабочий график', 'Деньги сгорели, до свидания', или 'Надо было думать раньше'."

        return {
            "cancellation_type": cancellation_type,
            "client_message": msg,
            "deposit_policy_explanation": policy,
            "methodological_advice": advice,
            "what_not_to_say": what_not
        }

    def mediate_client_dispute(
        self,
        dispute_description: str,
        photographer_role: str = "автор",
        profile: Optional[UserProfile] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Mediation and professional analysis of client disputes / conflicts from a photo-business lens.
        Matches Yaishka screen 12 (Dispute breakdown: where I slipped, where client is right, where client crosses line).
        """
        p_name = (profile and profile.identity) or "фотограф"
        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                prompt = (
                    f"Ты — опытный юрист и бизнес-медиатор для фотографов в сервисе «Яишка».\n"
                    f"Фотограф ({p_name}) описал конфликтную или спорную ситуацию с клиентом:\n"
                    f"«««\n{dispute_description}\n»»»\n\n"
                    "Проведи глубокий объективный разбор ситуации именно с точки зрения сервиса фотографа и нашей профессиональной работы:\n"
                    "1. 'Где моя просадка': трезво укажи, где фотограф сам допустил ошибку (не зафиксировал ожидания в переписке/договоре, размыл дедлайн, не объяснил условия ретуши).\n"
                    "2. 'Где права клиентка': в чем эмоции или претензии клиента имеют разумное основание.\n"
                    "3. 'Где клиентка уже перегибает / нарушает границы': необоснованные требования (отдать все RAW, хамить, требовать возврат за уже оказанную качественную услугу).\n"
                    "4. Стратегия общения и готовый скрипт ответа: вежливый, сдержанный, защищающий границы и профессиональное достоинство фотографа, закрывающий конфликт без суда и скандала.\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    '  "photographer_slippage": "где просадка фотографа",\n'
                    '  "client_justified_points": "в чем клиентка права",\n'
                    '  "client_overstepping_points": "где клиентка нарушает границы и перегибает",\n'
                    '  "strategic_recommendations": ["рекомендация 1", "рекомендация 2"],\n'
                    '  "ready_response_script": "готовый текст ответа клиенту в вежливом и твердом тоне",\n'
                    '  "formatted_mediation": "полный текст разбора для фотографа с абзацами и пунктами"\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.3)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "ready_response_script" in parsed:
                        return parsed
            except Exception:
                pass

        # Fallback Yaishka-grade dispute mediation
        slippage = "Не были четко прописаны условия: количество кадров в ретуши, порядок отбора и то, что исходники в формате RAW являются рабочим материалом и не отдаются."
        justified = "Клиентка переживает за свои вложенные деньги и результат, хочет видеть себя красивой и испытывает естественную тревожность."
        overstepping = "Требование отдать сырые файлы RAW без обработки, попытка обесценить проведенную съемочную работу или переход на эмоциональные манипуляции."
        script = (
            "«Здравствуйте! Я понимаю ваши переживания: съёмка — это важное событие, и для меня действительно ценно, чтобы вы остались довольны результатом. "
            "Давайте сверимся с нашими договоренностями: я отдаю серию в авторской цветокоррекции и оговоренное количество кадров в детальной ретуши. "
            "Исходные файлы RAW являются техническим материалом и по стандарту профессии не передаются. "
            "Чтобы решить вопрос конструктивно, давайте вы выберете 5 кадров из готовой серии, в которых вам хотелось бы скорректировать детали, и я бесплатно внесу эти правки в рамках согласованного стиля. "
            "Уверена, мы найдем комфортное решение!»"
        )
        formatted = (
            f"⚖️ **Разбор спорной ситуации с точки зрения фотобизнеса:**\n\n"
            f"1. **Где твоя просадка:**\n{slippage}\n\n"
            f"2. **В чем права клиентка:**\n{justified}\n\n"
            f"3. **Где клиентка перегибает:**\n{overstepping}\n\n"
            f"🎯 **Стратегия общения:**\n"
            f"• Не оправдывайся и не проявляй агрессию.\n"
            f"• Валидируй её эмоцию, но твердо держи профессиональные границы.\n"
            f"• Предложи один четкий конструктивный шаг решения (например, доработка 3-5 конкретных кадров).\n\n"
            f"💬 **Готовый скрипт ответа:**\n{script}"
        )
        return {
            "photographer_slippage": slippage,
            "client_justified_points": justified,
            "client_overstepping_points": overstepping,
            "strategic_recommendations": [
                "Твердо зафиксировать границы: RAW не отдаются",
                "Предложить ограниченный шаг навстречу: правка 3-5 конкретных замечаний"
            ],
            "ready_response_script": script,
            "formatted_mediation": formatted
        }

    def generate_three_tier_price_guide(
        self,
        niche: Optional[str] = None,
        base_price: int = 20000,
        currency: str = "₽",
        profile: Optional[UserProfile] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Generates a premium 3-tier pricing structure ('Лайт', 'Оптимальный - Самый популярный', 'Премиум')
        with value stacking and trust bar matching Yaishka screen 07.
        """
        active_niche = niche or (profile and profile.niche) or "Авторская фотосъёмка"
        p_light = int(base_price * 0.6)
        p_opt = base_price
        p_prem = int(base_price * 1.75)

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                prompt = (
                    f"Ты — коммерческий директор фотографов сервиса «Яишка».\n"
                    f"Создай эталонный премиальный прайс-лист для ниши '{active_niche}'.\n"
                    f"Базовый якорь цены: {p_opt} {currency}.\n\n"
                    "Сформируй линейку ровно из 3 тарифов по 'Правилу трех':\n"
                    "1. Тариф 01: «ЛАЙТ» (Минимум. Ничего лишнего) — цена ~{p_light} {currency}, до 1 часа, 50+ фото, 1 локация, 1 образ, готовность до 7 дней.\n"
                    "2. Тариф 02: «ОПТИМАЛЬНЫЙ» [САМЫЙ ПОПУЛЯРНЫЙ] (Баланс времени и результата) — цена {p_opt} {currency}, до 2 часов, 100+ фото, 10 глубокой ретуши, 1-2 локации, 2 образа, готовность до 5 дней, помощь в позировании и мудборд.\n"
                    "3. Тариф 03: «ПРЕМИУМ» (Полная история) — цена ~{p_prem} {currency}, до 4 часов, 200+ фото, 20 глубокой ретуши, до 3 локаций/образов, готовность до 3 дней, бронь без предоплаты.\n"
                    "4. Нижняя панель с преимуществами: 4 гарантии (индивидуальный подход, ретушь включена, конфиденциальность, поддержка).\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    '  "niche": "' + active_niche + '",\n'
                    '  "tiers": [\n'
                    '    {"name": "ЛАЙТ", "subtitle": "МИНИМУМ. НИЧЕГО ЛИШНЕГО.", "price": "' + f"{p_light:,} {currency}".replace(",", " ") + '", "features": ["⏱ ДО 1 ЧАСА СЪЕМКИ", "🖼 50+ ФОТО В БАЗОВОЙ РЕТУШИ", "✨ ГОТОВНОСТЬ ДО 7 ДНЕЙ", "📍 1 ЛОКАЦИЯ", "👔 1 ОБРАЗ"]},\n'
                    '    {"name": "ОПТИМАЛЬНЫЙ", "badge": "САМЫЙ ПОПУЛЯРНЫЙ", "subtitle": "БАЛАНС ВРЕМЕНИ И РЕЗУЛЬТАТА.", "price": "' + f"{p_opt:,} {currency}".replace(",", " ") + '", "features": ["⏱ ДО 2 ЧАСОВ СЪЕМКИ", "🖼 100+ ФОТО В РЕТУШИ", "✨ 10 ФОТО В ГЛУБОКОЙ РЕТУШИ", "✨ ГОТОВНОСТЬ ДО 5 ДНЕЙ", "📍 1–2 ЛОКАЦИИ", "👔 2 ОБРАЗА", "🎁 ПОМОЩЬ В ПОЗИРОВАНИИ И ПОДБОРЕ ОБРАЗА"]},\n'
                    '    {"name": "ПРЕМИУМ", "subtitle": "ПОЛНЫЙ ДЕНЬ. ПОЛНАЯ ИСТОРИЯ.", "price": "' + f"{p_prem:,} {currency}".replace(",", " ") + '", "features": ["⏱ ДО 4 ЧАСОВ СЪЕМКИ", "🖼 200+ ФОТО В РЕТУШИ", "✨ 20 ФОТО В ГЛУБОКОЙ РЕТУШИ", "✨ ГОТОВНОСТЬ ДО 3 ДНЕЙ", "📍 ДО 3 ЛОКАЦИЙ", "👔 ДО 3 ОБРАЗОВ", "🎁 ПОЛНОЕ ПРОДЮСИРОВАНИЕ КОНЦЕПЦИИ", "📅 БРОНИРОВАНИЕ БЕЗ ПРЕДОПЛАТЫ"]}\n'
                    '  ],\n'
                    '  "guarantees": ["🤍 ИНДИВИДУАЛЬНЫЙ ПОДХОД К КАЖДОМУ ГЕРОЮ", "✨ ВСЯ БАЗОВАЯ РЕТУШЬ ВКЛЮЧЕНА", "🔒 КОНФИДЕНЦИАЛЬНОСТЬ И БЕЗОПАСНОСТЬ", "📅 ЛЕГКОЕ БРОНИРОВАНИЕ И ПОДДЕРЖКА"],\n'
                    '  "card_markdown": "готовый красивый прайс-лист в markdown с разделителями и эмодзи"\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.4)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "tiers" in parsed and len(parsed["tiers"]) == 3:
                        return parsed
            except Exception:
                pass

        tiers = [
            {
                "name": "ТАРИФ 01: «ЛАЙТ»",
                "subtitle": "МИНИМУМ. НИЧЕГО ЛИШНЕГО.",
                "price": f"{p_light:,} {currency}".replace(",", " "),
                "features": [
                    "⏱ ДО 1 ЧАСА СЪЕМКИ",
                    "🖼 50+ ФОТО В ЦВЕТОКОРРЕКЦИИ",
                    "✨ ГОТОВНОСТЬ ДО 7 ДНЕЙ",
                    "📍 1 ЛОКАЦИЯ",
                    "👔 1 ОБРАЗ"
                ]
            },
            {
                "name": "ТАРИФ 02: «ОПТИМАЛЬНЫЙ» ⭐ [САМЫЙ ПОПУЛЯРНЫЙ]",
                "subtitle": "БАЛАНС ВРЕМЕНИ И РЕЗУЛЬТАТА.",
                "price": f"{p_opt:,} {currency}".replace(",", " "),
                "features": [
                    "⏱ ДО 2 ЧАСОВ СЪЕМКИ",
                    "🖼 100+ ФОТО В ЦВЕТОКОРРЕКЦИИ",
                    "✨ 10 ФОТО В ГЛУБОКОЙ АВТОРСКОЙ РЕТУШИ",
                    "✨ ГОТОВНОСТЬ ДО 5 ДНЕЙ",
                    "📍 1–2 ЛОКАЦИИ",
                    "👔 2 ОБРАЗА",
                    "🎁 МУДБОРД И ПОМОЩЬ С ПОЗИРОВАНИЕМ"
                ]
            },
            {
                "name": "ТАРИФ 03: «ПРЕМИУМ»",
                "subtitle": "ПОЛНЫЙ ДЕНЬ. ПОЛНАЯ ИСТОРИЯ.",
                "price": f"{p_prem:,} {currency}".replace(",", " "),
                "features": [
                    "⏱ ДО 4 ЧАСОВ СЪЕМКИ",
                    "🖼 200+ ФОТО В ОБРАБОТКЕ",
                    "✨ 20 ФОТО В ГЛУБОКОЙ РЕТУШИ",
                    "✨ ГОТОВНОСТЬ ДО 3 ДНЕЙ (УСКОРЕННАЯ ОТДАЧА)",
                    "📍 ДО 3 ЛОКАЦИЙ",
                    "👔 ДО 3 ОБРАЗОВ",
                    "🎁 ПОЛНОЕ ПРОДЮСИРОВАНИЕ, ПОДБОР СТИЛЯ И ЛОКАЦИЙ",
                    "📅 БРОНИРОВАНИЕ БЕЗ ПРЕДОПЛАТЫ"
                ]
            }
        ]
        guarantees = [
            "🤍 ИНДИВИДУАЛЬНЫЙ ПОДХОД К КАЖДОМУ ГЕРОЮ",
            "✨ ВСЯ БАЗОВАЯ РЕТУШЬ ВКЛЮЧЕНА В СТОИМОСТЬ",
            "🔒 ПОЛНАЯ КОНФИДЕНЦИАЛЬНОСТЬ (БЕЗ ДОПЛАТ ЗА НЕПУБЛИКАЦИЮ)",
            "📅 ПОДДЕРЖКА И ВЕДЕНИЕ НА ВСЕХ ЭТАПАХ"
        ]
        card = (
            f"📋 **П Р А Й С — {active_niche.upper()}**\n"
            f"*«Фотосъёмка для тех, кто ценит качество, искренность и сервис.»*\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
        )
        for t in tiers:
            badge = " 🔥" if "ПОПУЛЯРНЫЙ" in t["name"] else ""
            card += f"### {t['name']}{badge}\n*{t['subtitle']}*\n\n"
            for f in t["features"]:
                card += f"• {f}\n"
            card += f"\n💰 **Стоимость:** `{t['price']}`\n\n━━━━━━━━━━━━━━━━━━━\n\n"

        card += "🛡 **В каждый тариф включено:**\n" + "\n".join([f"• {g}" for g in guarantees])
        card += "\n\n*Давайте создавать красоту вместе. 🤍*"

        return {
            "niche": active_niche,
            "tiers": tiers,
            "guarantees": guarantees,
            "card_markdown": card
        }

