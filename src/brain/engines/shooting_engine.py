"""
Specialized Shooting and Moodboard Engine for Personal AI Brain.
Handles visual logic, lighting schemes, shot lists, reference analysis,
and client preparation guidance.
"""
from typing import Dict, Any, List, Optional
from src.brain.models.profile import UserProfile

class ShootingEngine:
    def __init__(self):
        pass

    def build_visual_logic(
        self,
        concept_title: str,
        genre: str = "Индивидуальный портрет",
        mood: str = "Кинематографичный, сдержанный, глубокий",
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Synthesizes visual logic for a photo shoot: light, color palette, location, styling, props.
        Dynamically generates bespoke creative direction via LLM with rule-based fallback.
        """
        c_lower = f"{concept_title} {genre} {mood}".lower().replace("ё", "е")

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    f"Ты — арт-директор и мастер студийного и естественного света.\n"
                    f"Разработай профессиональную визуальную концепцию для съёмки:\n"
                    f"- Концепт: '{concept_title}'\n"
                    f"- Жанр: '{genre}'\n"
                    f"- Настроение: '{mood}'\n\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект (без markdown блоков ```json):\n"
                    f"{{\n"
                    f'  "concept": "{concept_title}",\n'
                    f'  "genre": "{genre}",\n'
                    f'  "mood": "{mood}",\n'
                    f'  "light_scheme": {{\n'
                    f'    "primary": "точная схема и насадка рисующего света",\n'
                    f'    "fill_or_accent": "заполняющий или контровой свет",\n'
                    f'    "character": "характер светотени и глубина объема"\n'
                    f'  }},\n'
                    f'  "color_palette": [\n'
                    f'    {{"name": "название цвета 1", "hex": "#HEX1"}},\n'
                    f'    {{"name": "название цвета 2", "hex": "#HEX2"}},\n'
                    f'    {{"name": "название цвета 3", "hex": "#HEX3"}},\n'
                    f'    {{"name": "название цвета 4", "hex": "#HEX4"}}\n'
                    f'  ],\n'
                    f'  "location_guidance": "рекомендации по подбору локации, фона и фактур",\n'
                    f'  "styling_and_wardrobe": ["образ 1", "образ 2", "образ 3", "акценты и ткани"],\n'
                    f'  "props": ["предмет 1", "предмет 2", "предмет 3"]\n'
                    f"}}"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "light_scheme" in parsed and "color_palette" in parsed:
                        return parsed
            except Exception:
                pass

        # 1. Dark / Noir / Drama / Low-Key
        if any(w in c_lower for w in ["нуар", "noir", "темн", "драмат", "low key", "вечер"]):
            light_scheme = {
                "primary": "Узконаправленный луч (snoot или рефлектор с сотами) под углом 60° для глубокого светотеневого рисунка",
                "fill_or_accent": "Контражурный стрипбокс по силуэту волос и плеч, глубокий спад света в тени",
                "character": "Глубокий Low-Key с резким спадом освещенности, кинематографичный плотный черный тон"
            }
            color_palette = [
                {"name": "Графитовый / Угольный", "hex": "#1A1A1D"},
                {"name": "Глубокий бордо / Марсала", "hex": "#4E1A24"},
                {"name": "Оливково-бронзовый", "hex": "#3B3A36"},
                {"name": "Приглушенный дымчатый", "hex": "#8E8D8A"}
            ]
            location = "Студия с фактурным бетонным или темным холщовым фоном, винтажный приглушенный интерьер."
            styling = [
                "Фактурный шерстяной пиджак прямого мужского силуэта",
                "Черный кашемировый лонгслив или шелковая рубашка",
                "Широкие брюки со стрелками или темный плотный деним",
                "Минимум украшений — акцент на геометрии силуэта и взгляде"
            ]
            props = ["Стакан из граненого стекла с преломлением света", "Винтажные часы", "Книга в тканевом переплете"]

        # 2. Warm / Golden / Sunset / Love Story / Romance / Nature
        elif any(w in c_lower for w in ["золот", "тепл", "закат", "романт", "love story", "семейн", "оранжер", "солнц"]):
            light_scheme = {
                "primary": "Теплый закатный контровой свет (солнечный луч от окна или моноблок с теплым CTO-фильтром)",
                "fill_or_accent": "Белый/золотистый отражатель снизу для мягкого заполнения полутонов кожи",
                "character": "Воздушный High-Key с мягкими солнечными бликами (lens flare) и ореолом вокруг силуэта"
            }
            color_palette = [
                {"name": "Медово-золотистый", "hex": "#E9C46A"},
                {"name": "Теплый терракот", "hex": "#F4A261"},
                {"name": "Сливочный / Молочный", "hex": "#F5EBE0"},
                {"name": "Приглушенный эвкалипт", "hex": "#2A9D8F"}
            ]
            location = "Оранжерея, залитая светом светлая студия с деревянным полом или природная локация на закате."
            styling = [
                "Льняное платье свободного кроя молочного оттенка",
                "Объемный кардиган крупной вязки цвета топленого молока",
                "Светлые свободные брюки из дышащего хлопка",
                "Натуральные фактуры: лен, муслин, тонкая шерсть"
            ]
            props = ["Букет полевых трав или сухоцветов", "Керамическая чашка ручной работы", "Плед натуральной шерсти"]

        # 3. Fashion / Editorial / Minimalist High-End
        elif any(w in c_lower for w in ["fashion", "фэшн", "кампейн", "лукбук", "глянец", "модел"]):
            light_scheme = {
                "primary": "Большой источник мягкого света под углом 45° (софтбокс или большое окно от пола)",
                "fill_or_accent": "Отражатель серебро/белый снизу для заполнения теней под глазами + контражурный контровой свет для отделения силуэта",
                "character": "Мягкая градация светотени с глубоким объемом и естественным контрастом"
            }
            color_palette = [
                {"name": "Графитовый / Угольный", "hex": "#2B2D42"},
                {"name": "Теплый беж / Песочный", "hex": "#D8C4B6"},
                {"name": "Молочный / Экрю", "hex": "#F5EBE0"},
                {"name": "Глубокий терракот", "hex": "#8D5B4C"}
            ]
            location = "Минималистичная студия с циклорамой или фактурными бетонными стенами, деревянный пол, естественный дневной свет."
            styling = [
                "Оверсайз пиджак прямого кроя мужского силуэта",
                "Шелковый топ или простая белая базовая футболка плотного хлопка",
                "Широкие брюки палаццо или прямой деним без потертостей",
                "Минимум броских принтов — фокус на фактуре ткани (шерсть, лен, шелк, кожа)"
            ]
            props = ["Винтажный деревянный стул", "Стакан с водой и преломлением света", "Черно-белые журналы или книга"]

        # 4. Default Cinematic Balance
        else:
            light_scheme = {
                "primary": "Большой источник мягкого света под углом 45° (софтбокс или большое окно от пола)",
                "fill_or_accent": "Отражатель серебро/белый снизу для заполнения теней под глазами + контражурный контровой свет для отделения силуэта",
                "character": "Мягкая градация светотени с глубоким объемом и естественным контрастом"
            }
            color_palette = [
                {"name": "Графитовый / Угольный", "hex": "#2B2D42"},
                {"name": "Теплый беж / Песочный", "hex": "#D8C4B6"},
                {"name": "Молочный / Экрю", "hex": "#F5EBE0"},
                {"name": "Глубокий терракот", "hex": "#8D5B4C"}
            ]
            location = "Минималистичная студия с циклорамой или фактурными бетонными стенами, деревянный пол, естественный дневной свет."
            styling = [
                "Оверсайз пиджак прямого кроя мужского силуэта",
                "Шелковый топ или простая белая базовая футболка плотного хлопка",
                "Широкие брюки палаццо или прямой деним без потертостей",
                "Минимум броских принтов — фокус на фактуре ткани (шерсть, лен, шелк, кожа)"
            ]
            props = ["Винтажный деревянный стул", "Стакан с водой и преломлением света", "Черно-белые журналы или книга"]

        return {
            "concept": concept_title,
            "genre": genre,
            "mood": mood,
            "light_scheme": light_scheme,
            "color_palette": color_palette,
            "location_guidance": location,
            "styling_and_wardrobe": styling,
            "props": props
        }

    def critique_shot(self, image_path: str, prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes live multimodal AI critique on a photograph or reference image
        using Gemini Vision.
        """
        from pathlib import Path
        from src.brain.knowledge.extractors.vision_provider import get_vision_provider
        vp = get_vision_provider()
        res = vp.analyze_image(Path(image_path), custom_prompt=prompt)
        return {
            "status": res.status.value,
            "description": res.description,
            "detected_objects": res.detected_objects,
            "visual_tags": res.visual_tags,
            "model_name": res.model_name,
            "error_message": res.error_message
        }

    def generate_shot_list(
        self,
        duration_minutes: int = 60,
        concept: str = "",
        use_llm: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Generates a chronological, production-ready shot list for the shoot via LLM.
        """
        effective_concept = concept or "Индивидуальная авторская портретная съёмка"
        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    f"Ты — режиссер съемки и фотограф.\n"
                    f"Составь хронологический шот-лист съемки на {duration_minutes} минут по концепции: '{effective_concept}'.\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО JSON массив из 4 фаз съёмки:\n"
                    f"[\n"
                    f'  {{"timing": "00:00 - 00:15", "phase": "Адаптация", "plan": "крупный план", "action": "описание действия", "key_shots": ["кадр 1", "кадр 2"]}},\n'
                    f'  {{"timing": "00:15 - 00:35", "phase": "Основная динамика", "plan": "поясной и ростовой", "action": "описание действия", "key_shots": ["кадр 3", "кадр 4"]}},\n'
                    f'  {{"timing": "00:35 - 00:50", "phase": "Эмоции и кульминация", "plan": "детали и эмоции", "action": "описание действия", "key_shots": ["кадр 5", "кадр 6"]}},\n'
                    f'  {{"timing": "00:50 - 01:00", "phase": "Завершение", "plan": "атмосферные финальные кадры", "action": "описание действия", "key_shots": ["кадр 7", "кадр 8"]}}\n'
                    f"]"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, list) and len(parsed) >= 4:
                        return parsed
            except Exception:
                pass

        return [
            {
                "timing": "00:00 - 00:15",
                "phase": "Адаптация и разогрев",
                "plan": "Погрудный и поясной портрет",
                "action": "Спокойные позы сидя, привыкание к камере, поиск рабочей стороны и естественной улыбки.",
                "key_shots": ["Взгляд в камеру с мягким светом", "Профиль с легким поворотом головы", "Руки у лица / поправление волос"]
            },
            {
                "timing": "00:15 - 00:35",
                "phase": "Динамика и движение",
                "plan": "Ростовые кадры в движении",
                "action": "Шаг на камеру, поворот, взаимодействие с одеждой (полы пиджака, карманы).",
                "key_shots": ["Силуэт в полный рост", "Шаг на зрителя", "Легкий разворот в движении"]
            },
            {
                "timing": "00:35 - 00:50",
                "phase": "Эмоциональная кульминация и макродетали",
                "plan": "Крупные планы и макродетали",
                "action": "Искренние эмоции, улыбка, взгляд вдаль, игра со светом и бликами.",
                "key_shots": ["Глаза крупно с бликом", "Эмоциональный смех", "Деталь: кольца, часы, ткань"]
            },
            {
                "timing": "00:50 - 01:00",
                "phase": "Финальные атмосферные акценты",
                "plan": "Смена позы / сидя на полу / игра с тенью",
                "action": "Расслабленные небрежные позы, кинематографичный спад света.",
                "key_shots": ["Кадр сверху вниз сидя", "Черно-белый контрастный силуэт"]
            }
        ]

    def analyze_reference(self, reference_description: str, use_llm: bool = True) -> Dict[str, Any]:
        """
        Deconstructs a visual reference into actionable photographic parameters.
        Supports both textual reference descriptions and direct reference image files via Gemini Vision.
        """
        ref_text = reference_description
        from pathlib import Path
        try:
            cleaned_path_str = reference_description.strip().strip('"').strip("'")
            p_ref = Path(cleaned_path_str)
            if p_ref.is_file() and p_ref.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                v_res = self.critique_shot(str(p_ref))
                if v_res.get("status") == "AVAILABLE" and v_res.get("description"):
                    ref_text = f"Визуальный референс (анализ Gemini Vision):\n{v_res['description']}"
                else:
                    err_msg = v_res.get("error_message") or f"статус: {v_res.get('status', 'UNAVAILABLE')}"
                    ref_text = f"Файл референса: {p_ref.name} (анализ Gemini Vision не вернул описание: {err_msg})"
        except Exception:
            pass

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    "Ты — арт-директор и мастер студийного света для фотографов.\n"
                    f"Разбери визуальный референс или кадр:\n«««\n{ref_text}\n»»»\n\n"
                    "Декомпозируй его на профессиональные параметры:\n"
                    "1. Точная схема света (насадки, угол, рисующий/заполняющий/контровой).\n"
                    "2. Оптика и композиция (фокусное расстояние, диафрагма, ракурс, крупность плана).\n"
                    "3. Цветокоррекция и стилизация (оттенки, контраст, зерно, скинтон).\n"
                    "4. Совет по повторению в реальных условиях (студия или выезд).\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    f'  "reference_summary": {json.dumps(reference_description, ensure_ascii=False)},\n'
                    '  "light_analysis": "описание световой схемы",\n'
                    '  "composition_and_optics": "описание оптики и кадрирования",\n'
                    '  "color_grading": "описание работы с цветом",\n'
                    '  "adaptation_tips": "как повторить этот кадр на съемке"\n'
                    "}"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.3)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "light_analysis" in parsed:
                        return parsed
            except Exception:
                pass

        r_lower = reference_description.lower().replace("ё", "е")
        
        # Analyze light
        if any(w in r_lower for w in ["жестк", "контраст", "прям", "вспышк"]):
            light_type = "Жесткий направленный свет (прямая накамерная вспышка или открытый рефлектор без рассеивателя)"
        elif any(w in r_lower for w in ["окн", "дневн", "мягк", "рассеян"]):
            light_type = "Мягкий рассеянный свет от большого окна или софтбокса с диффузором"
        else:
            light_type = "Кинематографичный боковой свет (Rembrandt / Split lighting) с глубокими тенями"

        # Analyze composition
        if any(w in r_lower for w in ["крупн", "лицо", "глаз"]):
            comp = "Крупный план с акцентом на мимику и фактуру кожи, малая глубина резкости (f/1.8 - f/2.8)"
        elif any(w in r_lower for w in ["рост", "пространств", "воздух"]):
            comp = "Общий план с большим количеством 'воздуха' (negative space), геометрия локации"
        else:
            comp = "Поясной план по правилу третей, классическая портретная перспектива (50mm - 85mm)"

        return {
            "reference_summary": reference_description,
            "light_analysis": light_type,
            "composition_and_optics": comp,
            "color_grading": "Аналоговая пленочная тонировка с легким зерном, теплые света и нейтральные глубокие тени",
            "adaptation_tips": "Для повторения в обычной студии используйте один моноблок с октобоксом на стойке чуть выше уровня глаз модели под углом 45 градусов."
        }

    def generate_client_prep_memo(
        self,
        client_name: str = "клиент",
        genre: str = "съемка",
        location: str = "студия",
        use_llm: bool = True
    ) -> str:
        """
        Personalized checklist memo sent to client 2 days prior to the shoot.
        """
        if use_llm:
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    f"Ты — опытный заботливый фотограф. Напиши памятку подготовки к съёмке для героя ({client_name}).\n"
                    f"Формат: {genre}. Локация: {location}.\n\n"
                    "Памятка должна снять стресс клиента и содержать 5 четких пунктов:\n"
                    "1. Сон, вода, подготовка кожи\n"
                    "2. Одежда и обувь (с чистой подошвой для студии или обувь под локацию, глажка)\n"
                    "3. Белье (бесшовное телесное под светлое)\n"
                    "4. Аксессуары и мелочи, создающие акценты\n"
                    "5. Эмоциональный настрой и обещание мягкой поддержки на съемке.\n\n"
                    "Тон: заботливый, поддерживающий, профессиональный. Без канцелярита."
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.5)
                if code == 200 and len(text.strip()) > 80 and not text.strip().startswith("Тестовый ответ"):
                    return text.strip()
            except Exception:
                pass

        return (
            f"Чек-лист подготовки к съёмке для {client_name}:\n\n"
            "1. СОН И ВОДА: Постарайтесь хорошо выспаться накануне и пить достаточно воды — это лучший естественный тон для кожи.\n"
            "2. ОДЕЖДА И ОБУВЬ: Погладьте вещи заранее и везите на вешалках. Обувь должна быть с чистой подошвой для студии.\n"
            "3. БЕЛЬЕ: Под светлую или облегающую одежду идеально подойдет бесшовное белье телесного (бежевого) цвета.\n"
            "4. АКСЕССУАРЫ: Возьмите 2-3 любимых акцента (серьги, часы, очки, жакет) — они помогут менять образы за минуту.\n"
            "5. НАСТРОЙ: Главное правило — расслабиться и получать удовольствие. Я буду рядом, подскажу каждую позу и движение!"
        )

    def analyze_photo_with_critique(self, image_path: str, user_question: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes a 5-dimension master photo critique using Gemini Vision:
        Light, Composition, Posing/Emotion, Color/Grading, and 3 steps to level up.
        """
        critique_prompt = (
            "Ты — строгий, но вдохновляющий фотокритик и арт-директор фотошколы.\n"
            "Разбери эту фотографию по 5 профессиональным аспектам:\n"
            "1. СВЕТ И ТЕНЬ: направление, качество (жесткий/мягкий), светотеневой рисунок лица/объекта, провалы в тенях или пересветы.\n"
            "2. КОМПОЗИЦИЯ И РАКУРС: кадрирование, правило третей/диагонали, воздух вокруг героя, точка съемки.\n"
            "3. ПОЗИРОВАНИЕ И ЭМОЦИЯ: естественность модели, руки, плечи, искренность взгляда или зажатость.\n"
            "4. ЦВЕТ И СКИНТОН: баланс белого, натуральность тона кожи, гармония палитры одежды и фона.\n"
            "5. КАК СДЕЛАТЬ КАДР В 2 РАЗА СИЛЬНЕЕ: 3 конкретных практических шага для следующей съемки.\n"
        )
        if user_question:
            critique_prompt += f"\nВопрос автора кадра: «{user_question}»\nОтветь на него с точки зрения профессионального фотобизнеса."

        return self.critique_shot(image_path, prompt=critique_prompt)

    def audit_profile_and_grid(
        self,
        target: str,
        profile: Optional[UserProfile] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Multimodal audit of a photographer's social profile, bio, highlights, and grid rhythm.
        Matches Yaishka screen 03 (Account & Grid Audit).
        Accepts either an image path (screenshot of profile/grid) or text description.
        """
        from pathlib import Path
        visual_context = ""
        try:
            cleaned = target.strip().strip('"').strip("'")
            p_img = Path(cleaned)
            if p_img.is_file() and p_img.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                audit_vision_prompt = (
                    "Ты — арт-директор и ведущий аудитор профилей фотографов в соцсетях.\n"
                    "Внимательно изучи скриншот профиля/ленты фотографа:\n"
                    "1. Прочитай весь текст шапки: ник, имя, ниша, город, ключевые факты (УТП, опыт, ссылки).\n"
                    "2. Посмотри на закрепленные посты (Pinned).\n"
                    "3. Изучи названия обложек в «Актуальном» (Highlights).\n"
                    "4. Оцени сетку публикаций (ленту): крупность планов (дальний, средний, макро-детали), чередование света и гармонию.\n"
                    "5. Проявленность личного бренда (лицо автора, бэкстейдж или только безликие фото).\n"
                    "Опиши подробно всё увиденное для профессионального разбора."
                )
                v_res = self.critique_shot(str(p_img), prompt=audit_vision_prompt)
                if v_res.get("status") == "AVAILABLE" and v_res.get("description"):
                    visual_context = f"Анализ скриншота через Gemini Vision:\n{v_res['description']}"
        except Exception:
            pass

        content_to_audit = visual_context or target

        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                author_name = (profile and profile.identity) or "коллега"
                city_niche = f"Город: {profile.city or 'не указан'}, Ниша: {profile.niche or 'фотография'}." if profile else ""
                prompt = (
                    f"Ты — профессиональный арт-директор и наставник фотографов, как в сервисе «Яишка».\n"
                    f"Проведи комплексный аудит профиля и ленты фотографа ({author_name}. {city_niche}):\n"
                    f"«««\n{content_to_audit}\n»»»\n\n"
                    "Сделай структурированный разбор точно по методологии Яишки:\n"
                    "1. Введение: дружелюбное обращение по имени, общий вердикт.\n"
                    "2. Ниша и данные: ниша, география, ключевые факты шапки (УТП, сроки отдачи, ссылки).\n"
                    "3. Сильные стороны: что уже работает отлично (витрина из закрепленных постов, личный бренд, эстетика).\n"
                    "4. Точки роста:\n"
                    "   - Визуальный ритм ленты: как соседствуют кадры, нет ли каши по свету и крупности.\n"
                    "   - Навигация: названия обложек в «Актуальном» (предложи заменить загадочные/абстрактные названия на четкие конвертящие теги: «Прайс», «Отзывы», «Образы / Советы», «Локации»).\n"
                    "   - Управление «Ритмом» в ленте: шахматный порядок чередования планов (Дальний план / Средний план / Макро-деталь).\n"
                    "5. Три главных шага для внедрения уже сегодня.\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    '  "niche_and_geo": "описание ниши и города",\n'
                    '  "bio_assessment": "оценка шапки профиля и УТП",\n'
                    '  "strengths": ["сильная сторона 1", "сильная сторона 2"],\n'
                    '  "growth_points": ["точка роста 1", "точка роста 2"],\n'
                    '  "highlights_recommendation": "как переименовать актуальное",\n'
                    '  "grid_rhythm_advice": "рекомендация по шахматному чередованию планов (дальний, средний, макро)",\n'
                    '  "action_steps": ["шаг 1", "шаг 2", "шаг 3"],\n'
                    '  "full_formatted_audit": "готовый красивый текст разбора с эмодзи и абзацами в стиле Яишки"\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.5)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "grid_rhythm_advice" in parsed:
                        return parsed
            except Exception:
                pass

        # Fallback Yaishka-grade audit
        author_name = (profile and profile.identity) or "коллега"
        niche = (profile and profile.niche) or "портретная и семейная фотография"
        city = (profile and profile.city) or "вашем городе"
        formatted_audit = (
            f"{author_name}, вижу профиль целиком, и картина гораздо яснее. Давай разберем, что у тебя сейчас работает на ура, а где есть точки роста.\n\n"
            f"• Ниша: {niche}\n"
            f"• География: {city}\n"
            f"• Шапка профиля: важно, чтобы за первые 3 секунды клиент видел УТП (например, готовность фото за 24-48 часов или помощь с образами) и прямую ссылку для связи.\n\n"
            f"✨ Сильные стороны:\n"
            f"• Отличная «витрина» из закрепленных постов (Pinned). Это позволяет оценить твой уровень работ без долгого скроллинга.\n"
            f"• Проявленность автора: живые бэкстейджи и искренние кадры создают доверие намного сильнее безликих лент.\n\n"
            f"🎯 Точки роста:\n"
            f"• Визуальный ритм ленты: когда рядом стоят средние планы с разной температурой света, лента спорит сама с собой.\n"
            f"• Навигация в «Актуальном»: замени абстрактные заголовки на понятные теги — «Прайс», «Отзывы», «Образы», «Обо мне».\n"
            f"• Управление «Ритмом» (шахматный порядок): чередуй планы по крупности:\n"
            f"   1. Дальний план (атмосфера, локация, воздух)\n"
            f"   2. Средний план (герой, действие, эмоция)\n"
            f"   3. Макро-деталь (руки, кольца, цветы, фактура ткани)\n\n"
            f"Такой шахматный порядок сделает ленту визуально спокойной и дорогой!"
        )
        return {
            "niche_and_geo": f"{niche}, {city}",
            "bio_assessment": "Шапка профиля требует четкого УТП и прямой ссылки в мессенджер.",
            "strengths": ["Закрепленные посты дают понимание эстетики", "Наличие живых кадров формирует доверие"],
            "growth_points": ["Хаотичное чередование планов в ленте", "Неочевидные названия в актуальном"],
            "highlights_recommendation": "Переименовать в теги: «Прайс», «Отзывы», «Образы / Советы», «Локации».",
            "grid_rhythm_advice": "Внедрить шахматный порядок крупности: Дальний (воздух) -> Средний (герой) -> Макро-деталь (руки/декор).",
            "action_steps": [
                "Переименовать хайлайтс в понятные для клиента категории",
                "Разбавить ленту макро-деталями и кадрами с воздухом",
                "Закрепить в топ 3 лучших разноплановых серии"
            ],
            "full_formatted_audit": formatted_audit
        }

    def generate_moodboard_card(
        self,
        concept_title: str,
        genre: str = "Семейная фотосессия",
        location: str = "природная локация или студия",
        season: str = "текущий сезон",
        people_type: str = "семья",
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Generates a complete Yaishka visual moodboard & wardrobe lookbook card.
        Matches Yaishka screen 02 & 10 (Color palette, 7 outfit combinations, location, 5 framing ideas, "Важно ♡").
        """
        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                prompt = (
                    f"Ты — элитный арт-директор и стилист съёмок сервиса «Яишка».\n"
                    f"Создай эталонный мудборд и подборку образов для съёмки:\n"
                    f"- Концепция: '{concept_title}'\n"
                    f"- Жанр: '{genre}'\n"
                    f"- Локация: '{location}'\n"
                    f"- Сезон: '{season}', Участники: '{people_type}'\n\n"
                    "Сформируй карточку мудборда строго по стандартам Яишки:\n"
                    "1. Заголовок и поэтичный подзаголовок (например: «МУДБОРД: СЕМЕЙНАЯ СЪЕМКА В ЛЕСУ. Про теплые объятия, смех, прогулки...»).\n"
                    "2. Палитра: ровно 5 гармоничных цветов с красивыми названиями и HEX-кодами.\n"
                    "3. Примеры сочетаний образов: ровно 7 готовых сетов одежды (комбинации из 2-3 цветов, фактурные ткани: лен, муслин, крупная вязка, шелк, без ярких принтов).\n"
                    "4. Локация и свет: характеристики локации, лучшее окно света (утро или закат).\n"
                    "5. Идеи для кадров: 5 разноплановых идей (дальний, средний, крупный, макро-детали, динамика).\n"
                    "6. Блок «Важно ♡»: 4 заботливых совета (не стремиться к идеальным позам, дать быть собой, живые эмоции).\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    f'  "concept": "{concept_title}",\n'
                    '  "sub_headline": "поэтичный подзаголовок про чувства",\n'
                    '  "color_palette": [\n'
                    '    {"name": "Тёплый белый / Экрю", "hex": "#F5EBE0"},\n'
                    '    {"name": "Песочный / Карамельный", "hex": "#D8C4B6"},\n'
                    '    {"name": "Терракотовый", "hex": "#8D5B4C"},\n'
                    '    {"name": "Приглушенный оливковый", "hex": "#2A9D8F"},\n'
                    '    {"name": "Графитовый / Угольный", "hex": "#2B2D42"}\n'
                    '  ],\n'
                    '  "outfit_combinations": [\n'
                    '    "Сет 1: Тёплый белый + бежевый + карамельный (молочные свитеры, льняные брюки)",\n'
                    '    "Сет 2: Терракотовый + бежевый + тёплый белый (акцентный свитер или жакет)",\n'
                    '    "Сет 3: Горчичный + тёплый белый + песочный (фактурное платье и светлый кардиган)",\n'
                    '    "Сет 4: Оливковый + молочный + деним (спокойные природные тона)",\n'
                    '    "Сет 5: Карамельный + терракотовый + молочный (многослойный уютный образ)",\n'
                    '    "Сет 6: Глубокий шоколад + экрю + беж (элегантный контраст)",\n'
                    '    "Сет 7: Монохромный светлый беж с акцентом на фактуры (хлопок, шерсть, шелк)"\n'
                    '  ],\n'
                    '  "location_and_light": "описание локации и мягкий свет (утро или золотой час заката)",\n'
                    '  "framing_ideas": [\n'
                    '    "Дальний план: Прогулки рука об руку на фоне пространства",\n'
                    '    "Средний план: Игры и искренний смех в движении",\n'
                    '    "Крупный план: Объятия, улыбки, взгляд в кадр и мимо камеры",\n'
                    '    "Макро-детали: Прикосновения рук, прядь волос, фактура одежды",\n'
                    '    "Сюжетный кадр: Отдых вместе (чай из термоса, книга, плед)"\n'
                    '  ],\n'
                    '  "important_notes": [\n'
                    '    "Не стремитесь к идеальным заученным позам",\n'
                    '    "Дайте себе и близким быть собой",\n'
                    '    "Ловите живые моменты в эмоциях",\n'
                    '    "Главное — вы и ваши искренние чувства ♡"\n'
                    '  ],\n'
                    '  "card_markdown": "готовая презентационная карточка для клиента с эмодзи и разметкой"\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "outfit_combinations" in parsed and "color_palette" in parsed:
                        return parsed
            except Exception:
                pass

        # Fallback Yaishka-grade moodboard
        palette = [
            {"name": "Тёплый белый / Экрю", "hex": "#F5EBE0"},
            {"name": "Песочный / Карамель", "hex": "#D8C4B6"},
            {"name": "Тёплый терракот", "hex": "#8D5B4C"},
            {"name": "Приглушенный оливковый", "hex": "#2A9D8F"},
            {"name": "Глубокий графит", "hex": "#2B2D42"}
        ]
        outfits = [
            "Сет 1: Тёплый белый + бежевый + карамельный (молочные свитеры, льняные брюки)",
            "Сет 2: Терракотовый + бежевый + тёплый белый (акцентный свитер или жакет)",
            "Сет 3: Горчичный + тёплый белый + песочный (фактурное платье и светлый кардиган)",
            "Сет 4: Оливковый + молочный + деним (спокойные природные тона)",
            "Сет 5: Карамельный + терракотовый + молочный (многослойный уютный образ)",
            "Сет 6: Глубокий шоколад + экрю + беж (элегантный контраст)",
            "Сет 7: Монохромный светлый беж с акцентом на фактуры (хлопок, шерсть, шелк)"
        ]
        framing = [
            "Дальний план: Прогулки рука об руку на фоне пространства и геометрии локации",
            "Средний план: Взаимодействие, смех и непринужденное движение",
            "Крупный план: Объятия, живые глаза, полуулыбка",
            "Макро-детали: Прикосновения рук, прядь волос, кольца, чашка кофе/термос",
            "Сюжетный кадр: Маленькое общее действие (пикник, плед, чтение книги)"
        ]
        notes = [
            "Не стремитесь к идеальным заученным позам",
            "Дайте себе и близким право быть собой",
            "Ловите моменты в движении и эмоциях",
            "Главное — вы и ваши искренние чувства ♡"
        ]
        card_md = (
            f"📸 **МУДБОРД: {concept_title.upper()}**\n"
            f"*«Про теплые объятия, смех, уютную атмосферу и ваши настоящие моменты вместе.»*\n\n"
            f"🎨 **Палитра съёмки:**\n" + "\n".join([f"• `{p['hex']}` — {p['name']}" for p in palette]) + "\n\n"
            f"👗 **Подборка образов (7 вариантов):**\n" + "\n".join([f"• {o}" for o in outfits]) + "\n\n"
            f"📍 **Локация и свет:**\n{location}. Лучшее время — мягкий свет на рассвете или золотой предзакатный час.\n\n"
            f"🎞 **Идеи для кадров:**\n" + "\n".join([f"• {f}" for f in framing]) + "\n\n"
            f"🤍 **Важно:**\n" + "\n".join([f"• {n}" for n in notes])
        )
        return {
            "concept": concept_title,
            "sub_headline": "Про теплые объятия, смех, прогулки и ваши настоящие моменты вместе ♡",
            "color_palette": palette,
            "outfit_combinations": outfits,
            "location_and_light": f"{location}. Мягкий рассеянный свет (утро или закат).",
            "framing_ideas": framing,
            "important_notes": notes,
            "card_markdown": card_md
        }

    def recommend_music_soundtrack(
        self,
        mood_or_concept: str,
        visual_series_description: Optional[str] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Recommends 4-5 atmospheric audio tracks for visual series, Reels, or Stories.
        Matches Yaishka screen 16 (Track Selection with Artistic Rationale).
        """
        series_info = f"\nОписание визуальной серии: {visual_series_description}" if visual_series_description else ""
        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                prompt = (
                    f"Ты — музыкальный редактор и арт-директор визуальных медиа сервиса «Яишка».\n"
                    f"Подбери идеальное музыкальное сопровождение под концепцию съёмки:\n"
                    f"Концепт/настроение: '{mood_or_concept}'.{series_info}\n\n"
                    "Подбери ровно 4-5 атмосферных треков для Reels, Stories или музыкального слайдшоу.\n"
                    "Для каждого трека укажи:\n"
                    "1. Исполнитель и название (или характерный инструментальный стиль)\n"
                    "2. Жанр и темп (BPM, медленный / качающий / кинематографичный)\n"
                    "3. Настроение трека\n"
                    "4. Подробное художественное пояснение: почему этот трек подчеркивает визуальный ритм серии, свет и эмоциональную глубину кадров.\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    f'  "concept": "{mood_or_concept}",\n'
                    '  "tracks": [\n'
                    '    {\n'
                    '      "title": "Исполнитель — Трек",\n'
                    '      "genre": "Indie Folk / Cinematic Neo-Classical",\n'
                    '      "tempo": "85 BPM, размеренный мягкий бит",\n'
                    '      "mood": "Теплый, ностальгический, светлый",\n'
                    '      "artistic_rationale": "Мягкое акустическое вступление идеально совпадает с медленным панорамированием локации, а легкий ритм поддерживает смену кадров каждые 1.5 секунды."\n'
                    '    }\n'
                    '  ],\n'
                    '  "formatted_recommendations": "красивый готовый текст с эмодзи и рекомендациями для фотографа"\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "tracks" in parsed and len(parsed["tracks"]) >= 3:
                        return parsed
            except Exception:
                pass

        tracks = [
            {
                "title": "Novo Amor — Anchor",
                "genre": "Indie Folk / Atmospheric Acoustic",
                "tempo": "78 BPM, медленный дышащий темп",
                "mood": "Глубокий, трепетный, кинематографичный",
                "artistic_rationale": "Идеально подходит под кадры на закате и крупные планы объятий. Воздушный вокал не перетягивает внимание от визуальной серии."
            },
            {
                "title": "Hollow Coves — Coastline",
                "genre": "Acoustic Indie Pop",
                "tempo": "95 BPM, бодрый прогулочный ритм",
                "mood": "Солнечный, свободный, жизнеутверждающий",
                "artistic_rationale": "Отлично подчеркивает динамичные кадры в движении, искренний смех и прогулку семьи или пары."
            },
            {
                "title": "Ludovico Einaudi — Nuvole Bianche",
                "genre": "Modern Classical / Minimalist Piano",
                "tempo": "Рубато, плавный эмоциональный подъем",
                "mood": "Интимный, возвышенный, чувственный",
                "artistic_rationale": "Классический выбор для черно-белых серий и портретов крупным планом, где важен взгляд."
            },
            {
                "title": "Leon Bridges — Texas Sun (feat. Khruangbin)",
                "genre": "Vintage Soul / Psych Groove",
                "tempo": "88 BPM, мягкий обволакивающий грув",
                "mood": "Стильный, кинематографичный, теплый",
                "artistic_rationale": "Безупречно сочетается с аналоговыми пленочными тонами, фактурной одеждой и городскими прогулками."
            }
        ]
        formatted = (
            f"🎵 **Подборка атмосферных треков для серии: «{mood_or_concept}»**\n\n" +
            "\n\n".join([
                f"🎧 **{t['title']}** ({t['genre']})\n"
                f"• Темп: {t['tempo']}\n"
                f"• Настроение: {t['mood']}\n"
                f"• Почему подходит: {t['artistic_rationale']}"
                for t in tracks
            ])
        )
        return {
            "concept": mood_or_concept,
            "tracks": tracks,
            "formatted_recommendations": formatted
        }

    def prototype_photozone_concept(
        self,
        theme: str,
        season: Optional[str] = None,
        studio_type: Optional[str] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Prototypes a photozone concept before physical construction to launch pre-sales.
        Matches Yaishka screen 14 (Photozone Prototyping & Midjourney prompt generation).
        """
        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                prompt = (
                    f"Ты — арт-директор фотостудий и декоратор сервиса «Яишка».\n"
                    f"Создай концепт сезонной фотозоны для предварительных продаж съёмок:\n"
                    f"Тема: '{theme}', Сезон: '{season or 'сезонный'}', Студия: '{studio_type or 'интерьерная'}'.\n\n"
                    "Разработай:\n"
                    "1. Техническое задание декоратору: размеры, свет из окон, базовые цвета.\n"
                    "2. Список реквизита и ключевых акцентов.\n"
                    "3. Коммерческий текст для блога / соцсетей фотографа, чтобы продавать съёмки заранее.\n"
                    "4. Детальный англоязычный промпт для генерации визуального мокапа (Midjourney / Flux / Imagen).\n\n"
                    "Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    "{\n"
                    f'  "photozone_title": "{theme}",\n'
                    '  "dimensions_and_light": "размеры 3х4м, естественный свет из окна под 45 градусов",\n'
                    '  "color_scheme": ["#HEX1 (название)", "#HEX2 (название)"],\n'
                    '  "key_props": ["предмет 1", "предмет 2", "предмет 3"],\n'
                    '  "presale_pitch_text": "готовый продающий пост для фотографа с ранним бронированием",\n'
                    '  "image_generation_prompt": "cinematic photorealistic photozone set design..."\n'
                    "}"
                )
                code, text, _, _ = LLMProvider().chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "image_generation_prompt" in parsed:
                        return parsed
            except Exception:
                pass

        return {
            "photozone_title": theme,
            "dimensions_and_light": "Пространство 3.5х4 метра, боковой мягкий свет от большого окна от пола, нейтральный светлый пол.",
            "color_scheme": ["#D8C4B6 (Песочный)", "#8D5B4C (Тёплый терракот)", "#F5EBE0 (Молочный)", "#2A9D8F (Приглушенный оливковый)"],
            "key_props": ["Винтажная деревянная мебель", "Текстурные пледы и ткани", "Уютный атмосферный реквизит", "Сезонная флористика и сухоцветы"],
            "presale_pitch_text": f"Открываю предварительную запись на съёмки в новой авторской фотозоне «{theme}»! Ограниченное количество мест по спец-цене раннего бронирования.",
            "image_generation_prompt": f"aesthetic cozy photostudio interior corner, theme '{theme}', natural soft window light, warm neutral palette, wooden textures, photorealistic, 8k resolution, architectural photography"
        }
