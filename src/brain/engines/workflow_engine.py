"""
Stateful Workflow Engine for Personal AI Brain.
Orchestrates multi-step photographer workflows, task DAGs, and approval gates.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from src.brain.db import get_connection

class WorkflowStep(BaseModel):
    step_index: int
    name: str
    description: str
    action: str
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, SKIPPED, WAITING_APPROVAL
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False

class WorkflowInstance(BaseModel):
    workflow_id: str
    name: str
    workflow_type: str
    status: str = "ACTIVE"  # ACTIVE, WAITING_INPUT, WAITING_APPROVAL, COMPLETED, CANCELLED
    current_step: int = 0
    steps: List[WorkflowStep] = Field(default_factory=list)
    context_data: Dict[str, Any] = Field(default_factory=dict)
    results: Dict[str, Any] = Field(default_factory=dict)
    approval_state: str = "NONE"  # NONE, PENDING, APPROVED, REJECTED
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

WORKFLOW_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "photoday_launch": {
        "name": "Запуск фотодня под ключ",
        "steps": [
            {"name": "audit_context", "description": "Анализ профиля, жанра и аудитории", "action": "audit", "requires_approval": False},
            {"name": "concept_and_visual_logic", "description": "Разработка концепции, цветовой палитры и стиля", "action": "concept", "requires_approval": False},
            {"name": "package_architecture", "description": "Формирование пакетов, тайминга слотов и цен", "action": "pricing", "requires_approval": True},
            {"name": "announcement_post", "description": "Создание вовлекающего анонсирующего поста", "action": "content", "requires_approval": False},
            {"name": "stories_sequence", "description": "Прогревочная серия Stories из 5 кадров", "action": "stories", "requires_approval": False},
            {"name": "reels_script", "description": "Сценарий Reels с хуком и визуальным рядом", "action": "reels", "requires_approval": False},
            {"name": "client_dm_template", "description": "Шаблон ответа клиентам в Direct / Telegram", "action": "sales", "requires_approval": True},
            {"name": "launch_checklist", "description": "Финальный чек-лист подготовки и тайминга", "action": "checklist", "requires_approval": False}
        ]
    },
    "no_content_emergency": {
        "name": "Скорая помощь: Мне нечего выложить",
        "steps": [
            {"name": "mine_context", "description": "Поиск неиспользованных идей, съемок и актуального сезона", "action": "mine", "requires_approval": False},
            {"name": "generate_angles", "description": "3 готовых идеи публикаций с хуками", "action": "ideas", "requires_approval": False},
            {"name": "draft_priority_post", "description": "Полный черновик приоритетного поста в стиле фотографа", "action": "draft", "requires_approval": False}
        ]
    },
    "client_chat_analysis": {
        "name": "Анализ переписки и закрытие сделки",
        "steps": [
            {"name": "reconstruct_dialogue", "description": "Разбор сообщений клиента и эмоционального фона", "action": "parse", "requires_approval": False},
            {"name": "diagnose_objection", "description": "Определение истинной причины сомнений клиента", "action": "diagnose", "requires_approval": False},
            {"name": "consultative_strategy", "description": "Формирование мягкой консультационной стратегии", "action": "strategy", "requires_approval": False},
            {"name": "draft_response", "description": "Подготовка заботливого ответа без давления", "action": "draft_message", "requires_approval": True},
            {"name": "schedule_followup", "description": "Постановка задачи на follow-up", "action": "task", "requires_approval": False}
        ]
    },
    "shoot_preparation": {
        "name": "Полная подготовка к съёмке",
        "steps": [
            {"name": "concept_definition", "description": "Определение настроения, идеи и ассоциаций", "action": "concept", "requires_approval": False},
            {"name": "visual_logic", "description": "Свет, цветовая гамма, локация, образы и реквизит", "action": "visuals", "requires_approval": False},
            {"name": "shot_list_and_timing", "description": "Покадровый план съёмки и хронометраж", "action": "shotlist", "requires_approval": False},
            {"name": "client_memo", "description": "Памятка клиенту по гардеробу и подготовке", "action": "memo", "requires_approval": True}
        ]
    },
    "daily_planning": {
        "name": "Ежедневное планирование фотографа",
        "steps": [
            {"name": "scan_workspace", "description": "Сканирование съемок, дедлайнов и зависших клиентов", "action": "scan", "requires_approval": False},
            {"name": "priorities_synthesis", "description": "Формирование топ-3 фокусных действий на день", "action": "prioritize", "requires_approval": False}
        ]
    },
    "voice_to_content": {
        "name": "Голосовая заметка в контент-пак",
        "steps": [
            {"name": "stt_parsing", "description": "Извлечение историй, драматургии и бизнес-инсайтов", "action": "parse_voice", "requires_approval": False},
            {"name": "derivative_pack", "description": "Генерация 1 поста, 2 рилс, серии сторис и задачи", "action": "generate_pack", "requires_approval": False}
        ]
    }
}

class WorkflowEngine:
    def __init__(self):
        pass

    def start_workflow(self, workflow_type: str, initial_context: Optional[Dict[str, Any]] = None, name: Optional[str] = None) -> WorkflowInstance:
        template = WORKFLOW_TEMPLATES.get(workflow_type)
        if not template:
            template = {
                "name": f"Пользовательский workflow ({workflow_type})",
                "steps": [
                    {"name": "step_1", "description": "Выполнение задачи", "action": "execute", "requires_approval": False}
                ]
            }

        wf_id = str(uuid.uuid4())
        first_gated = bool(template["steps"] and template["steps"][0].get("requires_approval", False))
        steps = [
            WorkflowStep(
                step_index=idx,
                name=s["name"],
                description=s["description"],
                action=s["action"],
                requires_approval=s.get("requires_approval", False),
                status=("WAITING_APPROVAL" if first_gated else "IN_PROGRESS") if idx == 0 else "PENDING"
            )
            for idx, s in enumerate(template["steps"])
        ]

        instance = WorkflowInstance(
            workflow_id=wf_id,
            name=name or template["name"],
            workflow_type=workflow_type,
            status="WAITING_APPROVAL" if first_gated else "ACTIVE",
            current_step=0,
            steps=steps,
            context_data=initial_context or {},
            results={},
            approval_state="PENDING" if first_gated else "NONE"
        )
        self._save_instance(instance)
        return instance

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowInstance]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_instance(row)

    def get_active_workflow_by_type(self, workflow_type: str) -> Optional[WorkflowInstance]:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        SELECT * FROM workflows 
        WHERE workflow_type = ? AND status IN ('ACTIVE', 'WAITING_INPUT', 'WAITING_APPROVAL')
        ORDER BY updated_at DESC LIMIT 1
        """, (workflow_type,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_instance(row)

    def cancel_workflow(self, workflow_id: str) -> WorkflowInstance:
        wf = self.get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")
        wf.status = "CANCELLED"
        wf.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_instance(wf)
        return wf

    def advance_step(self, workflow_id: str, step_output: Dict[str, Any], next_inputs: Optional[Dict[str, Any]] = None) -> WorkflowInstance:
        wf = self.get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")

        if wf.status == "COMPLETED":
            raise ValueError(f"Workflow {workflow_id} is already completed")
        if wf.status == "CANCELLED":
            raise ValueError(f"Workflow {workflow_id} is cancelled")
        if wf.status == "WAITING_APPROVAL":
            raise ValueError(f"Workflow {workflow_id} step {wf.current_step} ('{wf.steps[wf.current_step].name}') requires approval before execution")
        if wf.status == "WAITING_INPUT":
            raise ValueError(f"Workflow {workflow_id} step {wf.current_step} ('{wf.steps[wf.current_step].name}') is waiting for input or rejected")

        curr_idx = wf.current_step
        if curr_idx < len(wf.steps):
            wf.steps[curr_idx].status = "COMPLETED"
            wf.steps[curr_idx].outputs = step_output
            wf.results[wf.steps[curr_idx].name] = step_output

        next_idx = curr_idx + 1
        if next_idx >= len(wf.steps):
            wf.status = "COMPLETED"
            wf.current_step = curr_idx
            wf.approval_state = "NONE"
        else:
            wf.current_step = next_idx
            wf.steps[next_idx].status = "IN_PROGRESS"
            if next_inputs:
                wf.steps[next_idx].inputs = next_inputs
            if wf.steps[next_idx].requires_approval:
                wf.status = "WAITING_APPROVAL"
                wf.approval_state = "PENDING"
            else:
                wf.status = "ACTIVE"
                wf.approval_state = "NONE"

        wf.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_instance(wf)
        return wf

    def approve_step(self, workflow_id: str, approved: bool = True) -> WorkflowInstance:
        wf = self.get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")

        curr_idx = wf.current_step
        if approved:
            wf.approval_state = "APPROVED"
            wf.steps[curr_idx].status = "APPROVED"
            wf.status = "ACTIVE"
        else:
            wf.approval_state = "REJECTED"
            wf.steps[curr_idx].status = "REJECTED"
            wf.status = "WAITING_INPUT"

        wf.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_instance(wf)
        return wf

    def execute_step(self, workflow_id: str, profile: Optional[Any] = None) -> Tuple[WorkflowInstance, Dict[str, Any]]:
        """
        Executes the current step using the corresponding domain engine,
        records the output, and advances the workflow state.
        """
        from src.brain.engines.content_engine import ContentEngine
        from src.brain.engines.sales_engine import SalesEngine
        from src.brain.engines.shooting_engine import ShootingEngine
        from src.brain.engines.voice_engine import VoiceEngine
        from src.brain.engines.proactive_engine import ProactiveEngine

        wf = self.get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")

        if wf.status == "COMPLETED":
            raise ValueError(f"Workflow {workflow_id} is already completed")
        if wf.status == "CANCELLED":
            raise ValueError(f"Workflow {workflow_id} is cancelled")

        curr_step = wf.steps[wf.current_step]
        if wf.status == "WAITING_APPROVAL":
            raise ValueError(f"Workflow {workflow_id} step {wf.current_step} ('{curr_step.name}') requires approval before execution")
        if wf.status == "WAITING_INPUT":
            raise ValueError(f"Workflow {workflow_id} step {wf.current_step} ('{curr_step.name}') is waiting for input or rejected")

        action = curr_step.action
        ctx = wf.context_data
        output = {}

        if action == "mine":
            ce = ContentEngine()
            angles = ce.emergency_content_recovery(profile=profile)
            output = {"mined_angles": angles}
        elif action == "ideas":
            ce = ContentEngine()
            output = {"ideas": ce.emergency_content_recovery(profile=profile)}
        elif action == "draft":
            ce = ContentEngine()
            fmt = ce.build_format_prompt("post")
            draft_text = ""
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                angles = ctx.get("mined_angles") or wf.results.get("generate_angles", {}).get("ideas", []) or []
                selected_angle = angles[0] if angles else {"hook": "Секрет живого кадра", "theme": "Закулисье работы со светом"}
                niche = profile.niche if profile and profile.niche else "авторская фотография"
                tone = profile.tone if profile and profile.tone else "живой, экспертный"
                prompt = (
                    f"Ты — копирайтер фотографа ({niche}, тон: {tone}).\n"
                    f"Напиши готовый к публикации пост на тему: {selected_angle.get('theme', 'Закулисье съёмки')}.\n"
                    f"Хук: {selected_angle.get('hook', 'Что остаётся за кадром')}.\n"
                    f"Формат:\n{fmt}\n"
                    f"Напиши готовый живой текст поста от первого лица с абзацами и призывом к действию."
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.7)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    draft_text = text.strip()
            except Exception:
                pass
            if not draft_text:
                draft_text = (
                    f"«Один кадр, который изменил всё»\n\n"
                    f"Когда мы только начинали работу над проектом '{wf.name}', казалось, что свет не ложится как надо. "
                    f"Но стоило убрать лишний отражатель и сместить акцент на геометрию силуэта — картинка ожила.\n\n"
                    f"В фотографии главное — не заученные позы, а состояние героя и воздух в кадре.\n\n"
                    f"А что для вас самое сложное на съемках — выбор образа или первые минуты перед камерой?"
                )
            output = {"draft_prompt": fmt, "draft_text": draft_text}
        elif action == "audit":
            theme = ctx.get("theme", wf.name or "Фотодень")
            city = (profile and profile.city) or ctx.get("city", "город не указан")
            niche = (profile and profile.niche) or ctx.get("niche", "авторская портретная фотография")
            aud = (profile and profile.audience) or ctx.get("audience", "целевая аудитория")
            audit_res = None
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    f"Ты — коммерческий продюсер и маркетолог для фотографов.\n"
                    f"Проведи экспресс-аудит контекста для запуска спецпроекта / фотодня «{theme}».\n"
                    f"Параметры фотографа:\n"
                    f"- Ниша: {niche}\n"
                    f"- Город: {city}\n"
                    f"- Аудитория: {aud}\n\n"
                    f"Определи:\n"
                    f"1. Готовность аудитории и позиционирование проекта\n"
                    f"2. Рекомендуемый фокус ценности (почему купят именно сейчас)\n"
                    f"3. Ключевые риски и рекомендации по формату\n\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    f"{{\n"
                    f'  "market_readiness": "высокая / средняя",\n'
                    f'  "target_segment": "описание целевого сегмента",\n'
                    f'  "core_value_proposition": "главная ценность предложения",\n'
                    f'  "audit_recommendations": ["рекомендация 1", "рекомендация 2"]\n'
                    f"}}"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.5)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "core_value_proposition" in parsed:
                        audit_res = parsed
            except Exception:
                pass
            if not audit_res:
                audit_res = {
                    "market_readiness": "высокая",
                    "target_segment": f"Клиенты в нише '{niche}' ({city}), ценящие готовый результат без сложной подготовки",
                    "core_value_proposition": f"Концептуальный фотодень «{theme}» с продуманным светом, локацией и готовыми образами",
                    "audit_recommendations": [
                        "Сфокусироваться на ограниченном количестве слотов (не более 4-5 героев в день)",
                        "Заранее подготовить мудборд и схему света, чтобы съемки шли в едином тайминге"
                    ]
                }
            output = {"audit": audit_res}
        elif action == "concept":
            theme = ctx.get("theme", wf.name or "Индивидуальный портрет")
            genre = ctx.get("genre", "Авторский портрет")
            mood = ctx.get("mood", "Кинематографичный, глубокий, естественный")
            concept_res = None
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    f"Ты — креативный арт-директор и концептуалист в фотографии.\n"
                    f"Разработай художественную концепцию съемки:\n"
                    f"- Тема: {theme}\n"
                    f"- Жанр: {genre}\n"
                    f"- Настроение: {mood}\n\n"
                    f"Опиши:\n"
                    f"1. Главная идея и драматургия съемки (о чем эта визуальная история)\n"
                    f"2. Ключевые эмоции и состояние героя в кадре\n"
                    f"3. Визуальные референсы и метафоры\n\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    f"{{\n"
                    f'  "concept_title": "{theme}",\n'
                    f'  "core_narrative": "драматургия и идея съемки",\n'
                    f'  "hero_state": "состояние и эмоции героя",\n'
                    f'  "visual_references": ["референс 1", "референс 2", "референс 3"]\n'
                    f"}}"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "core_narrative" in parsed:
                        concept_res = parsed
            except Exception:
                pass
            if not concept_res:
                concept_res = {
                    "concept_title": theme,
                    "core_narrative": f"Исследование естественной красоты и внутреннего состояния героя в рамках концепта «{theme}».",
                    "hero_state": "Расслабленность, глубина, уверенность и искренность без заученных поз.",
                    "visual_references": [
                        "Кинематографичный боковой свет и фактурный нейтральный фон",
                        "Портреты крупным планом с живым глубоким взглядом",
                        "Динамичные кадры в полуоборота с воздухом в кадре"
                    ]
                }
            output = {"concept": concept_res}
        elif action == "visuals":
            se = ShootingEngine()
            theme = ctx.get("theme") or wf.results.get("concept_definition", {}).get("concept", {}).get("concept_title") or wf.name or "Индивидуальный портрет"
            genre = ctx.get("genre", "Индивидуальный портрет")
            mood = ctx.get("mood", "Кинематографичный, сдержанный, глубокий")
            output = se.build_visual_logic(theme, genre=genre, mood=mood)
        elif action == "pricing":
            sa = SalesEngine()
            packages = ctx.get("packages", [{"name": "Стандарт", "price": 15000, "duration_hours": 1, "retouched_photos": 20}])
            output = sa.evaluate_pricing_ladder(packages)
            output["packages"] = packages
        elif action == "content":
            ce = ContentEngine()
            fmt = ce.build_format_prompt("post")
            theme = ctx.get("theme", wf.name or "Осенний фотодень")
            city = (profile and profile.city) or ctx.get("city", "")
            city_str = f" в {city}" if city else ""
            post_content = ""
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = f"Напиши живой анонсирующий пост для фотодня '{theme}'{city_str}. Формат:\n{fmt}\nЖивой слог без заезженных клише."
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.7)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    post_content = text.strip()
            except Exception:
                pass
            if not post_content:
                post_content = (
                    f"Открываю запись на специальный фотодень «{theme}»{city_str}! 🍂\n\n"
                    f"Мы подготовили авторскую цветовую гамму, идеальный студийный свет и бережную помощь с позированием на каждом шаге. "
                    f"Все удачные кадры в цветокоррекции + 10 фото в журнальной ретуши уже через 5 дней.\n\n"
                    f"Напишите мне в личные сообщения, чтобы выбрать удобный временной слот!"
                )
            output = {"post_template": fmt, "post_text": post_content}
        elif action == "stories":
            ce = ContentEngine()
            fmt = ce.build_format_prompt("stories")
            theme = ctx.get("theme", wf.name or "Фотодень")
            stories_content = ""
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = f"Напиши серию из 5 вовлекающих Stories для анонса '{theme}'. Формат:\n{fmt}"
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.7)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    stories_content = text.strip()
            except Exception:
                pass
            if not stories_content:
                stories_content = (
                    f"Серия Stories для анонса «{theme}»:\n"
                    f"1. [Интрига]: 'Давно хотела реализовать эту концепцию света и цвета...'\n"
                    f"2. [Контекст]: Показываем бэкстейдж подбора референсов и фактур тканей.\n"
                    f"3. [Кульминация]: 'Анонсирую специальный фотодень всего на один уикенд!'\n"
                    f"4. [Польза и сервис]: Полная помощь с одеждой, комфортная атмосфера без спешки.\n"
                    f"5. [CTA]: Интерактивное окошко 'Прислать условия и тайминг слотов в Direct'."
                )
            output = {"stories_template": fmt, "stories_content": stories_content}
        elif action == "reels":
            ce = ContentEngine()
            fmt = ce.build_format_prompt("reels")
            theme = ctx.get("theme", wf.name or "Фотодень")
            reels_content = ""
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = f"Напиши сценарий Reels для анонса фотодня '{theme}'. Формат:\n{fmt}"
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.7)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    reels_content = text.strip()
            except Exception:
                pass
            if not reels_content:
                reels_content = (
                    f"Сценарий Reels «{theme}»:\n"
                    f"1. ХУК (0-3 сек): 'Почему на одних фотосессиях скованно, а на других — легко?' (показываем контраст взглядов).\n"
                    f"2. ВИЗУАЛЬНЫЙ РЯД: Смена планов под ритмичный джазовый бит, фотограф направляет модель с улыбкой.\n"
                    f"3. ТЕКСТ НА ЭКРАНЕ: 'Секрет в атмосфере, где тебе разрешено быть собой'.\n"
                    f"4. ГОЛОСОВОЙ ТЕКСТ: 'Я беру на себя свет, образ и каждую позу — вам остаётся только пить кофе и ловить момент'.\n"
                    f"5. CTA: 'Свободные слоты на ближайший фотодень — по ссылке в профиле'."
                )
            output = {"reels_template": fmt, "reels_content": reels_content}
        elif action == "sales":
            theme = ctx.get("theme", wf.name or "Фотодень")
            city = (profile and profile.city) or ctx.get("city", "")
            city_str = f" в {city}" if city else ""
            packages = ctx.get("packages") or wf.results.get("package_architecture", {}).get("packages")
            dm_text = ""
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                niche = profile.niche if profile and profile.niche else "авторская фотография"
                tone = profile.tone if profile and profile.tone else "теплый, заботливый"
                pkg_info = f"Пакеты: {json.dumps(packages, ensure_ascii=False)}" if packages else "Формат: индивидуальные слоты с полной подготовкой"
                prompt = (
                    f"Ты — фотограф ({niche}, тон: {tone}).\n"
                    f"Напиши готовый идеальный шаблон первого ответа клиенту в Direct / Telegram, который интересуется спецпроектом «{theme}»{city_str}.\n"
                    f"{pkg_info}\n\n"
                    f"Правила:\n"
                    f"- Теплое приветствие без шаблонов и панибратства\n"
                    f"- Кратко раскрыть ценность концепта и что уже включено\n"
                    f"- Предложить выбрать удобное время или задать вопрос\n"
                    f"Верни ТОЛЬКО текст шаблона ответа в кавычках."
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and len(text.strip()) > 30 and not text.strip().startswith("Тестовый ответ"):
                    dm_text = text.strip()
            except Exception:
                pass
            if not dm_text:
                dm_text = (
                    f"«Здравствуйте! С радостью расскажу про наш фотодень «{theme}»{city_str}! ✨\n\n"
                    f"Этот день мы создали для того, чтобы вы получили не просто кадры, а удовольствие от процесса: "
                    f"я полностью беру на себя свет, помощь с позированием и подбор образов.\n\n"
                    f"В стоимость входит 50 минут съемки, аренда студии и все удачные фото в авторской обработке.\n\n"
                    f"Подскажите, на какое время дня вам комфортнее ориентироваться — утро или вторая половина?»"
                )
            output = {"dm_template": dm_text}
        elif action == "checklist":
            theme = ctx.get("theme", wf.name or "Фотодень")
            city = (profile and profile.city) or ctx.get("city", "")
            checklist_items = []
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                prompt = (
                    f"Ты — опытный продюсер фотопроектов.\n"
                    f"Составь подробный чек-лист организационной подготовки для фотографа к проведению фотодня «{theme}» ({city or 'студия'}).\n"
                    f"Включи 5-6 ключевых этапов: бронь студии, тайминг слотов, подготовка оборудования, коммуникация с клиентами, атмосфера.\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО валидный JSON массив строк:\n"
                    f'["пункт 1", "пункт 2", "пункт 3", "пункт 4", "пункт 5", "пункт 6"]'
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.5)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, list) and len(parsed) >= 4:
                        checklist_items = parsed
            except Exception:
                pass
            if not checklist_items:
                checklist_items = [
                    f"Забронировать студию и согласовать свет под концепт «{theme}»",
                    "Сформировать сетку слотов с перерывом 15 минут между героями",
                    "Зарядить аккумуляторы, очистить флешки и подготовить бекап-камеру",
                    "Отправить всем участникам памятку по гардеробу за 48 часов",
                    "Подготовить вдохновляющий плейлист и напитки для создания уюта",
                    "Сохранить мудборд на телефон/планшет для быстрой сверки на площадке"
                ]
            output = {"checklist": checklist_items}
        elif action == "parse":
            sa = SalesEngine()
            dialogue = ctx.get("dialogue", "Здравствуйте! Сколько стоит?")
            output = sa.analyze_client_dialogue(dialogue, client=ctx.get("client"))
        elif action == "diagnose":
            sa = SalesEngine()
            dialogue = ctx.get("dialogue", "Здравствуйте! Это слишком дорого.")
            output = sa.analyze_client_dialogue(dialogue, client=ctx.get("client"))
        elif action == "strategy":
            sa = SalesEngine()
            dialogue = ctx.get("dialogue", "Здравствуйте! Это слишком дорого.")
            diag = wf.results.get("diagnose_objection") or wf.results.get("reconstruct_dialogue") or sa.analyze_client_dialogue(dialogue, client=ctx.get("client"))
            output = {"strategy": diag.get("recommended_strategy", "Раскрыть ценность подготовки и сервиса")}
        elif action == "draft_message":
            sa = SalesEngine()
            diag = wf.results.get("diagnose_objection") or wf.results.get("reconstruct_dialogue") or {}
            detected_objs = diag.get("detected_objections", [])
            primary_obj = ctx.get("objection") or (detected_objs[0] if detected_objs else None) or ctx.get("dialogue", "дорого")
            resp_text = sa.generate_objection_response(primary_obj, profile=profile, client=ctx.get("client"))
            output = {"response": resp_text}
        elif action == "task":
            from src.brain.models.task import TaskPriority, TaskStatus, ApprovalState
            client_id = ctx.get("client_id") or (ctx.get("client") and getattr(ctx.get("client"), "id", None))
            client_name = ctx.get("client_name") or (ctx.get("client") and getattr(ctx.get("client"), "name", None)) or "Клиент"
            task_title = ctx.get("task_title") or f"Follow-up диалога с клиентом: {client_name}"
            task_id = str(uuid.uuid4())
            now_str = datetime.now(timezone.utc).isoformat()
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("""
                INSERT INTO tasks (task_id, title, type, status, priority, created_at, due_at, project_id, client_id, inputs_json, outputs_json, approval_state)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id, task_title, "client_followup", TaskStatus.TODO.value, TaskPriority.HIGH.value,
                    now_str, None, None, client_id,
                    json.dumps({"workflow_id": workflow_id, "dialogue": ctx.get("dialogue")}, ensure_ascii=False),
                    json.dumps({}, ensure_ascii=False),
                    ApprovalState.NONE.value
                ))
                conn.commit()
                conn.close()
            except Exception:
                pass
            output = {
                "task_id": task_id,
                "title": task_title,
                "priority": TaskPriority.HIGH.value,
                "status": TaskStatus.TODO.value
            }
        elif action == "shotlist":
            se = ShootingEngine()
            c_data = (
                wf.results.get("concept_definition", {}).get("concept") or
                wf.results.get("concept_and_visual_logic", {}).get("concept")
            )
            c_extracted = (c_data.get("concept_title") or c_data.get("core_narrative")) if isinstance(c_data, dict) else (c_data if isinstance(c_data, str) else None)
            concept_title = (
                ctx.get("concept") or ctx.get("theme") or
                c_extracted or
                "Индивидуальная авторская портретная съёмка"
            )
            duration = ctx.get("duration", 60)
            output = {"shot_list": se.generate_shot_list(duration_minutes=duration, concept=concept_title)}
        elif action == "memo":
            se = ShootingEngine()
            c_name = ctx.get("client_name", "Герой съемки")
            genre = ctx.get("genre") or ctx.get("theme") or "авторская съемка"
            location = ctx.get("location", "студия")
            output = {"memo": se.generate_client_prep_memo(client_name=c_name, genre=genre, location=location)}
        elif action == "scan":
            pe = ProactiveEngine()
            plan = pe.generate_daily_plan(profile=profile)
            output = {
                "scan_report": "Сканирование проектов, дедлайнов и клиентов завершено",
                "date": plan.get("date"),
                "detected_priorities_preview": plan.get("priorities", [])
            }
        elif action == "prioritize":
            pe = ProactiveEngine()
            output = pe.generate_daily_plan(profile=profile)
        elif action == "parse_voice":
            ve = VoiceEngine()
            transcript = ctx.get("transcript", "Вчера была отличная съемка!")
            voice_res = ve.process_voice_transcript(transcript, profile=profile)
            output = {
                "source_transcript": voice_res.get("source_transcript"),
                "extracted_events": voice_res.get("extracted_events"),
                "story_beats": voice_res.get("story_beats"),
                "business_insights": voice_res.get("business_insights")
            }
        elif action == "generate_pack":
            ve = VoiceEngine()
            transcript = ctx.get("transcript", "Вчера была отличная съемка!")
            voice_res = ve.process_voice_transcript(transcript, profile=profile)
            output = {
                "derivative_post": voice_res.get("derivative_post"),
                "derivative_reels": voice_res.get("derivative_reels"),
                "derivative_stories": voice_res.get("derivative_stories"),
                "suggested_task": voice_res.get("suggested_task")
            }
        else:
            output = {"status": "completed", "action": action}

        updated_wf = self.advance_step(workflow_id, output)
        return updated_wf, output

    def _save_instance(self, wf: WorkflowInstance):
        conn = get_connection()
        c = conn.cursor()
        steps_json = json.dumps([s.model_dump() for s in wf.steps], ensure_ascii=False)
        context_json = json.dumps(wf.context_data, ensure_ascii=False)
        results_json = json.dumps(wf.results, ensure_ascii=False)

        c.execute("""
        INSERT INTO workflows (workflow_id, name, workflow_type, status, current_step, steps_json, context_json, results_json, approval_state, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workflow_id) DO UPDATE SET
            status=excluded.status,
            current_step=excluded.current_step,
            steps_json=excluded.steps_json,
            context_json=excluded.context_json,
            results_json=excluded.results_json,
            approval_state=excluded.approval_state,
            updated_at=excluded.updated_at
        """, (
            wf.workflow_id, wf.name, wf.workflow_type, wf.status,
            wf.current_step, steps_json, context_json, results_json,
            wf.approval_state, wf.created_at, wf.updated_at
        ))
        conn.commit()
        conn.close()

    def _row_to_instance(self, row: Any) -> WorkflowInstance:
        steps_data = json.loads(row["steps_json"] or "[]")
        steps = [WorkflowStep(**s) for s in steps_data]
        return WorkflowInstance(
            workflow_id=row["workflow_id"],
            name=row["name"],
            workflow_type=row["workflow_type"],
            status=row["status"],
            current_step=row["current_step"],
            steps=steps,
            context_data=json.loads(row["context_json"] or "{}"),
            results=json.loads(row["results_json"] or "{}"),
            approval_state=row["approval_state"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
