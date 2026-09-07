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
        use_llm: bool = False
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
                if code == 200:
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
        use_llm: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Generates a chronological, production-ready shot list for the shoot via LLM.
        """
        if use_llm and concept:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    f"Ты — режиссер съемки и фотограф.\n"
                    f"Составь хронологический шот-лист съемки на {duration_minutes} минут по концепции: '{concept}'.\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО JSON массив из 4 фаз съёмки:\n"
                    f"[\n"
                    f'  {{"timing": "00:00 - 00:15", "phase": "Адаптация", "plan": "крупный план", "action": "описание действия", "key_shots": ["кадр 1", "кадр 2"]}},\n'
                    f'  {{"timing": "00:15 - 00:35", "phase": "Основная динамика", "plan": "поясной и ростовой", "action": "описание действия", "key_shots": ["кадр 3", "кадр 4"]}},\n'
                    f'  {{"timing": "00:35 - 00:50", "phase": "Эмоции и кульминация", "plan": "детали и эмоции", "action": "описание действия", "key_shots": ["кадр 5", "кадр 6"]}},\n'
                    f'  {{"timing": "00:50 - 01:00", "phase": "Завершение", "plan": "атмосферные финальные кадры", "action": "описание действия", "key_shots": ["кадр 7", "кадр 8"]}}\n'
                    f"]"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200:
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

    def analyze_reference(self, reference_description: str) -> Dict[str, Any]:
        """
        Deconstructs a visual reference into actionable photographic parameters.
        """
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

    def generate_client_prep_memo(self, client_name: str = "клиент") -> str:
        """
        Checklist memo sent to client 2 days prior to the shoot.
        """
        return (
            f"Чек-лист подготовки к съёмке для {client_name}:\n\n"
            "1. СОН И ВОДА: Постарайтесь хорошо выспаться накануне и пить достаточно воды — это лучший естественный тон для кожи.\n"
            "2. ОДЕЖДА И ОБУВЬ: Погладьте вещи заранее и везите на вешалках. Обувь должна быть с чистой подошвой для студии.\n"
            "3. БЕЛЬЕ: Под светлую или облегающую одежду идеально подойдет бесшовное белье телесного (бежевого) цвета.\n"
            "4. АКСЕССУАРЫ: Возьмите 2-3 любимых акцента (серьги, часы, очки, жакет) — они помогут менять образы за минуту.\n"
            "5. НАСТРОЙ: Главное правило — расслабиться и получать удовольствие. Я буду рядом, подскажу каждую позу и движение!"
        )
