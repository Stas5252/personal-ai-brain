"""
Interactive CLI for Personal AI Brain (Photographer Work System).
Allows immediate testing of all Brain capabilities directly in your terminal:
- Text chat with full memory, CRM, and style directives
- Live Gemini Vision photo critique
- Voice transcript deconstruction
- Sales objections handling
- Content emergency synthesis
- Proactive daily planning
"""
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.brain.services.brain_service import BrainService
from src.brain.engines.shooting_engine import ShootingEngine
from src.brain.engines.voice_engine import VoiceEngine
from src.brain.engines.sales_engine import SalesEngine
from src.brain.engines.content_engine import ContentEngine
from src.brain.engines.proactive_engine import ProactiveEngine

def print_banner():
    print("=" * 70)
    print("      PERSONAL AI BRAIN — PHOTOGRAPHER WORK STUDIO (CLI)")
    print("=" * 70)
    print("Горячие клавиши и быстрые режимы:")
    print("  [1] ⚡ Сценарий 'Мне нечего выложить' (3 ракурса из базы)")
    print("  [2] 💬 Отработка возражения ('дорого', 'подумаем', 'не умеем позировать')")
    print("  [3] 👁️ Фотокритика кадра через Gemini Vision (указать путь к файлу)")
    print("  [4] 🎙️ Разбор голосовой заметки фотографа в контент-пак")
    print("  [5] 📅 План на день из CRM (проекты, клиенты, задачи)")
    print("  [6] 🧠 Обзор долговременной памяти и профиля")
    print("  [exit / q] Выход")
    print("-" * 70)

def main():
    brain = BrainService()
    print_banner()

    while True:
        try:
            user_input = input("\n[Вы] > ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("\nДо встречи в студии!")
                break

            # Mode 1: Emergency content
            if user_input == "1":
                print("\n[*] Запуск сценария 'Мне нечего выложить'...")
                ce = ContentEngine()
                angles = ce.emergency_content_recovery(profile=brain.profile_engine.get_profile(), use_llm=True)
                for i, a in enumerate(angles, 1):
                    print(f"\n--- РАКУРС {i}: {a.get('angle')} [{a.get('format')}] ---")
                    print(f"Хук: {a.get('hook')}")
                    print(f"Тема: {a.get('theme')}")
                    print(f"CTA: {a.get('cta')}")
                continue

            # Mode 2: Sales objections
            if user_input == "2":
                obj = input("Введите возражение клиента (например: дорого, подумаем, муж против, не умеем позировать): ")
                se = SalesEngine()
                resp = se.generate_objection_response(obj, profile=brain.profile_engine.get_profile(), use_llm=True)
                print(f"\n[Ответ клиенту]:\n{resp}")
                continue

            # Mode 3: Vision critique
            if user_input == "3":
                img_path = input("Введите путь к фотографии (.jpg, .png): ").strip(""'")
                p = Path(img_path)
                if not p.exists():
                    print(f"[!] Файл не найден: {img_path}")
                    continue
                print("[*] Отправка в Gemini Vision (свет, композиция, поза, цвет)...")
                se = ShootingEngine()
                critique = se.critique_shot(str(p))
                print(f"\n--- РЕЗУЛЬТАТ АНАЛИЗА КАДРА ({critique.get('status')}) ---")
                print(critique.get("description"))
                continue

            # Mode 4: Voice transcript
            if user_input == "4":
                transcript = input("Введите надиктованный текст со съемки: ")
                ve = VoiceEngine()
                pack = ve.process_voice_transcript(transcript, profile=brain.profile_engine.get_profile(), use_llm=True)
                print("\n--- ГОТОВЫЙ КОНТЕНТ-ПАК ИЗ ГОЛОСОВОГО ---")
                print(f"Пост:\n{pack.get('derivative_post')}\n")
                print(f"Reels 1: {pack.get('derivative_reels_1')}\n")
                print(f"Reels 2: {pack.get('derivative_reels_2')}\n")
                print(f"Stories:\n{pack.get('derivative_stories')}\n")
                print(f"Задача: {pack.get('assistant_task')}")
                continue

            # Mode 5: Daily plan
            if user_input == "5":
                print("[*] Синтез плана дня из CRM...")
                pe = ProactiveEngine()
                plan = pe.generate_daily_plan(profile=brain.profile_engine.get_profile(), use_llm=True)
                print(f"\nФокус дня: {plan.get('daily_focus')}")
                for pr in plan.get("priorities", []):
                    print(f"• [Приоритет {pr.get('priority_level')}] {pr.get('title')}: {pr.get('action')}")
                continue

            # Mode 6: Memory overview
            if user_input == "6":
                memories = brain.memory_engine.get_memories()
                prof = brain.profile_engine.get_profile()
                print(f"\n--- ПРОФИЛЬ: {prof.identity if prof else 'Не задан'} ---")
                print(f"Ниша: {prof.niche if prof else '-'}")
                print(f"Всего воспоминаний в памяти: {len(memories)}")
                for m in memories[:8]:
                    print(f"• [{m.type.value}] {m.content[:75]}...")
                continue

            # Standard chat processing through full Brain pipeline
            print("[*] Обработка запроса через Brain Service...")
            res = brain.process_chat(user_input)
            print(f"\n[Brain] ({res.get('model_used')}, {res.get('execution_time_ms')}мс):\n")
            print(res.get("response"))

        except KeyboardInterrupt:
            print("\nВыход.")
            break
        except Exception as e:
            print(f"[!] Ошибка: {e}")

if __name__ == "__main__":
    main()
