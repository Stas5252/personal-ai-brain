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
