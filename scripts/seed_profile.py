#!/usr/bin/env python3
"""
Quick profile setup helper — skips the Telegram onboarding flow.

Set your photographer profile directly from the command line:

    python scripts/seed_profile.py \\
        --name "Мария" \\
        --city "Москва" \\
        --niche "Семейная и детская фотография" \\
        --services "Семейная съёмка" "Детская съёмка" "Прегнанность" \\
        --price-light "8000" \\
        --price-optimal "12000" \\
        --price-premium "20000" \\
        --tone "Теплый, искренний, без клише" \\
        --goals "Два раза больше записей" "Чек от 30к ₽"
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(
        description='Seed photographer profile into brain DB',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--name', default='Виктория Ларионова', help="Photographer's name")
    parser.add_argument('--city', default='Самара', help='City where you shoot')
    parser.add_argument('--niche', default='Кинематографичный естественный портрет и семейные истории', help='Photography niche')
    parser.add_argument('--services', nargs='*', default=['Индивидуальная кинематографичная съёмка', 'Семейная фотосессия', 'Love Story на закате Волги', 'Экспресс-съёмка'])
    parser.add_argument('--genres', nargs='*', default=['Женский портрет', 'Семейная съёмка', 'Love Story', 'Индивидуальная фотосессия'])
    parser.add_argument('--price-light', default='5000')
    parser.add_argument('--price-optimal', default='8500')
    parser.add_argument('--price-premium', default='15000')
    parser.add_argument('--tone', default='Теплый, кинематографичный, заботливый, без клише и навязчивости')
    parser.add_argument('--audience', default='Девушки и семьи 25-42 лет, ценящие искренние эмоции, естественный свет и спокойную эстетику')
    parser.add_argument('--goals', nargs='*', default=['Плотная запись на месяц вперед', 'Чек от 10 000 ₽', 'Узнаваемый визуальный почерк в Самаре'])
    parser.add_argument('--forbidden-words', nargs='*', default=['красоточка', 'волшебство', 'раскрою женственность', 'девочки', 'скидочка', 'налетай', 'уникальный прайс'])
    args = parser.parse_args()

    try:
        from src.brain.engines.profile_engine import ProfileEngine
        from src.brain.models.profile import UserProfile
    except ImportError as e:
        print(f"[ERROR] Cannot import brain modules: {e}")
        sys.exit(1)

    engine = ProfileEngine()
    profile = engine.get_profile()
    profile.identity = args.name
    if args.city: profile.city = args.city
    if args.niche: profile.niche = args.niche
    if args.services: profile.services = args.services
    if args.genres: profile.genres = args.genres
    if args.tone: profile.tone = args.tone
    if args.audience: profile.audience = args.audience
    if args.goals: profile.goals = args.goals
    if args.forbidden_words: profile.forbidden_words = args.forbidden_words

    if args.price_light or args.price_optimal or args.price_premium:
        profile.pricing = {}
        if args.price_light: profile.pricing['ЛАЙТ'] = f'{args.price_light} ₽'
        if args.price_optimal: profile.pricing['ОПТИМАЛЬНЫЙ'] = f'{args.price_optimal} ₽'
        if args.price_premium: profile.pricing['ПРЕМИУМ'] = f'{args.price_premium} ₽'
        if hasattr(profile, 'prices'): profile.prices = profile.pricing

    engine.save_profile(profile)
    print(f"\n✅ Profile saved! Name: {profile.identity}, Niche: {profile.niche or '(not set)'}")
    print("\n💡 Start bot: docker-compose up -d")


if __name__ == '__main__':
    main()
