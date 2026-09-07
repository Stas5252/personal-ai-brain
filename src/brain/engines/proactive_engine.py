"""
Proactive and Daily Planning Assistant for Personal AI Brain.
Provides intelligent schedule analysis ("Что мне сегодня делать?"),
task prioritization, and contextual proactive nudges with quiet-hours policy.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.brain.models.profile import UserProfile
from src.brain.models.client import Client, ClientStatus
from src.brain.models.project import Project, ProjectStatus
from src.brain.models.task import Task, TaskStatus, TaskPriority

class ProactiveEngine:
    def __init__(self, enabled: bool = True, quiet_hours_start: int = 22, quiet_hours_end: int = 9):
        self.enabled = enabled
        self.quiet_hours_start = quiet_hours_start
        self.quiet_hours_end = quiet_hours_end

    def is_quiet_hours(self, current_hour: Optional[int] = None) -> bool:
        if current_hour is None:
            current_hour = datetime.now().hour
        if self.quiet_hours_start > self.quiet_hours_end:
            return current_hour >= self.quiet_hours_start or current_hour < self.quiet_hours_end
        return self.quiet_hours_start <= current_hour < self.quiet_hours_end

    def generate_daily_plan(
        self,
        projects: Optional[List[Project]] = None,
        clients: Optional[List[Client]] = None,
        tasks: Optional[List[Task]] = None,
        profile: Optional[UserProfile] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Synthesizes Top-3 high-impact daily priorities for the photographer,
        querying real database entities (projects, clients, tasks) when available.
        """
        from src.brain.db import get_connection
        import json

        # 1. Fetch real active projects from DB if not provided
        if projects is None:
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM projects WHERE status NOT IN ('COMPLETED', 'CANCELLED') ORDER BY updated_at DESC LIMIT 5")
                rows = c.fetchall()
                conn.close()
                if rows:
                    projects = [
                        Project(
                            id=r["id"], name=r["name"], description=r["description"],
                            status=ProjectStatus(r["status"]), start_date=r["start_date"],
                            deadline=r["deadline"], client_id=r["client_id"],
                            created_at=r["created_at"], updated_at=r["updated_at"]
                        ) for r in rows
                    ]
                else:
                    projects = []
            except Exception:
                projects = []

        # 2. Fetch real clients from DB if not provided
        if clients is None:
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM clients WHERE status IN ('THINKING', 'PROPOSAL', 'LEAD', 'INTERESTED') ORDER BY updated_at DESC LIMIT 5")
                rows = c.fetchall()
                conn.close()
                if rows:
                    clients = [
                        Client(
                            id=r["id"], name=r["name"], contact=r["contact"],
                            status=ClientStatus(r["status"]), source=r["source"],
                            budget=r["budget"], service=r["service"], preferences=r["preferences"],
                            objections=r["objections"], created_at=r["created_at"], updated_at=r["updated_at"]
                        ) for r in rows
                    ]
                else:
                    clients = []
            except Exception:
                clients = []

        # 3. Fetch real tasks from DB if not provided
        if tasks is None:
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM tasks WHERE status NOT IN ('COMPLETED', 'CANCELLED') ORDER BY priority DESC LIMIT 5")
                rows = c.fetchall()
                conn.close()
                if rows:
                    tasks = [
                        Task(
                            task_id=r["task_id"], title=r["title"], type=r["type"],
                            status=TaskStatus(r["status"]), priority=TaskPriority(r["priority"]),
                            created_at=r["created_at"], due_at=r["due_at"]
                        ) for r in rows
                    ]
                else:
                    tasks = []
            except Exception:
                tasks = []

        # Try LLM synthesis of top priorities
        if use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                proj_desc = ", ".join([f"'{p.name}' [{p.status.value}]" for p in (projects or [])[:3]]) or "нет активных съемок"
                client_desc = ", ".join([f"{c.name} ({c.status.value}, {c.service})" for c in (clients or [])[:3]]) or "нет активных лидов"
                task_desc = ", ".join([t.title for t in (tasks or [])[:3]]) or "нет срочных дедлайнов"
                niche_str = profile.niche if profile and profile.niche else "авторская фотография"

                prompt = (
                    f"Ты — личный операционный менеджер фотографа ({niche_str}).\n"
                    f"Текущая ситуация в бизнесе:\n"
                    f"- Проекты: {proj_desc}\n"
                    f"- Клиенты: {client_desc}\n"
                    f"- Задачи: {task_desc}\n\n"
                    f"Составь фокусированный план на сегодня ровно из 3 приоритетов (Производство съемок, Продажи/Клиенты, Контент).\n"
                    f"Верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект:\n"
                    f"{{\n"
                    f'  "date": "{datetime.now().strftime("%d.%m.%Y")}",\n'
                    f'  "priorities": [\n'
                    f'    {{"priority_level": 1, "domain": "SHOOTING & PRODUCTION", "title": "...", "action": "...", "reason": "..."}},\n'
                    f'    {{"priority_level": 2, "domain": "SALES & CLIENT CARE", "title": "...", "action": "...", "reason": "..."}},\n'
                    f'    {{"priority_level": 3, "domain": "CONTENT & VISIBILITY", "title": "...", "action": "...", "reason": "..."}}\n'
                    f'  ],\n'
                    f'  "photographer_focus": "главный фокус дня в одно предложение"\n'
                    f"}}"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.5)
                if code == 200:
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and "priorities" in parsed and len(parsed["priorities"]) == 3:
                        return parsed
            except Exception:
                pass

        priorities = []

        # Priority 1: Shoot / Production / Urgent Project
        active_projects = projects or []
        urgent_projects = [p for p in active_projects if p.status in [ProjectStatus.SHOOTING, ProjectStatus.EDITING, ProjectStatus.PREPARATION, ProjectStatus.PLANNED, ProjectStatus.BOOKED]]
        
        if urgent_projects:
            p = urgent_projects[0]
            priorities.append({
                "priority_level": 1,
                "domain": f"SHOOTING / {p.status.value}",
                "title": f"Проект '{p.name}': статус {p.status.value}",
                "action": f"Завершить этап '{p.status.value}' по проекту '{p.name}', подготовить материалы для клиента.",
                "reason": "Прямое влияние на соблюдение дедлайна и лояльность клиента."
            })
        else:
            priorities.append({
                "priority_level": 1,
                "domain": "SHOOTING PREPARATION",
                "title": "Подготовка к ближайшей съёмке",
                "action": "Согласовать референсы и отправить клиенту памятку по гардеробу за 48 часов.",
                "reason": "Гарантирует спокойствие клиента и высокий результат съёмки."
            })

        # Priority 2: Sales & Client Care
        active_clients = clients or []
        thinking_clients = [c for c in active_clients if c.status in [ClientStatus.THINKING, ClientStatus.PROPOSAL, ClientStatus.LEAD, ClientStatus.INTERESTED]]
        
        if thinking_clients:
            c = thinking_clients[0]
            service_note = f" по услуге '{c.service}'" if c.service else ""
            priorities.append({
                "priority_level": 2,
                "domain": "SALES & CLIENT CARE",
                "title": f"Клиент {c.name}: статус {c.status.value}",
                "action": f"Мягко напомнить о себе заботливым сообщением{service_note} или подборкой идей под запрос.",
                "reason": "Предотвращает потерю лида и закрывает сделку без навязчивости."
            })
        else:
            priorities.append({
                "priority_level": 2,
                "domain": "SALES",
                "title": "Работа с базой постоянных клиентов",
                "action": "Написать 2-3 прошлым клиентам с поздравлением или анонсом нового сезона.",
                "reason": "Повторные клиенты имеют самую высокую конверсию."
            })

        # Priority 3: Content & Visibility
        niche_str = profile.niche if profile and profile.niche else "авторской фотографии"
        priorities.append({
            "priority_level": 3,
            "domain": "CONTENT & VISIBILITY",
            "title": "Публикация контента в блоге / канале",
            "action": f"Выложить Reels с бекстейджем или историю со вчерашней съёмки в стиле {niche_str}.",
            "reason": "Регулярность формирует доверие новой аудитории и держит блог активным."
        })

        return {
            "date": datetime.now().strftime("%d.%m.%Y"),
            "priorities": priorities,
            "photographer_focus": "1 процессная задача + 1 продажа + 1 касание аудитории через контент."
        }

    def evaluate_proactive_nudge(
        self,
        recent_event: str,
        profile: Optional[UserProfile] = None,
        use_llm: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Generates context-aware proactivity (e.g. after a shoot, client ghosting, or idle content pause).
        """
        if not self.enabled or self.is_quiet_hours():
            return None

        event_lower = recent_event.lower().replace("ё", "е")
        nudge_type = None
        suggested_action = None
        base_msg = ""

        if "съемк" in event_lower or "прошла съемка" in event_lower:
            nudge_type = "POST_SHOOT_FOLLOWUP"
            suggested_action = "start_workflow:no_content_emergency"
            base_msg = "У тебя недавно прошла съёмка! Хочешь, помогу собрать живой пост с инсайтом или сценарий Reels из бекстейджа, пока впечатления свежие?"
        elif "пропал клиент" in event_lower or "не отвечает" in event_lower or "молча" in event_lower:
            nudge_type = "CLIENT_GHOSTING_CARE"
            suggested_action = "start_workflow:client_chat_analysis"
            base_msg = "Клиент молчит больше 24 часов. Подготовить короткое бережное сообщение, чтобы возобновить диалог без навязчивости?"
        elif "давно не заходил" in event_lower or "пауз" in event_lower or "тишин" in event_lower:
            nudge_type = "CONTENT_IDLE_REMINDER"
            suggested_action = "start_workflow:no_content_emergency"
            base_msg = "Привет! Заметил, что мы давно не выкладывали контент. Давай за 5 минут набросаем идею для легкого поста или сторис?"

        if not nudge_type and use_llm:
            try:
                import json
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                tone = profile.tone if profile and profile.tone else "Теплый напарник, заботливый, без спама"
                niche = profile.niche if profile and profile.niche else "фотография"
                prompt = (
                    f"Ты — личный ИИ-напарник фотографа ({niche}). Твой тон: {tone}.\n"
                    f"Произошло событие: '{recent_event}'.\n"
                    "Определи, требуется ли проактивная поддержка, совет или напоминание фотографу.\n"
                    "Если да, верни ИСКЛЮЧИТЕЛЬНО валидный JSON объект (без markdown блоков):\n"
                    '{\n'
                    '  "nudge_type": "ТИП_СОБЫТИЯ",\n'
                    '  "message": "короткое (1-2 предложения) искреннее сообщение в мессенджер с предложением конкретного действия",\n'
                    '  "suggested_action": "рекомендуемое действие или название процесса"\n'
                    '}\n'
                    "Если проактивное вмешательство не требуется, верни {}\n"
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.5)
                if code == 200 and not text.strip().startswith("Тестовый ответ"):
                    clean = text.strip()
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict) and parsed.get("message"):
                        return {
                            "type": parsed.get("nudge_type", "DYNAMIC_EVENT_NUDGE"),
                            "message": parsed["message"],
                            "suggested_action": parsed.get("suggested_action")
                        }
            except Exception:
                pass

        if not nudge_type:
            return None

        if use_llm:
            try:
                from src.brain.services.llm_provider import LLMProvider
                llm = LLMProvider()
                tone = profile.tone if profile and profile.tone else "Теплый напарник, заботливый, без спама"
                niche = profile.niche if profile and profile.niche else "фотография"
                prompt = (
                    f"Ты — личный ИИ-напарник фотографа ({niche}). Твой тон: {tone}.\n"
                    f"Событие: {recent_event}.\n"
                    f"Напиши одно короткое (1-2 предложения), теплое, дружеское напоминание в Telegram.\n"
                    f"Без формализма, навязчивости и роботизированных фраз. Сразу предложи полезное действие.\n"
                    f"Верни ТОЛЬКО текст сообщения."
                )
                code, text, _, _ = llm.chat_completion([{"role": "user", "content": prompt}], temperature=0.6)
                if code == 200 and len(text.strip()) > 20 and not text.strip().startswith("Тестовый ответ"):
                    return {
                        "type": nudge_type,
                        "message": text.strip().strip('"\''),
                        "suggested_action": suggested_action
                    }
            except Exception:
                pass

        return {
            "type": nudge_type,
            "message": base_msg,
            "suggested_action": suggested_action
        }
