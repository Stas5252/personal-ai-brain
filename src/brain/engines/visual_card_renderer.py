"""
Visual Card Renderer for Personal AI Brain.
Renders magazine-style, aesthetic moodboard and outfit visual cards (PNG/JPEG)
that photographers can instantly forward to their clients in Telegram/WhatsApp.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont

BG_COLOR = (248, 246, 242)       # Warm linen / ivory
CARD_BG = (255, 255, 255)        # Pure crisp white
TEXT_DARK = (40, 36, 32)         # Deep warm charcoal
TEXT_MUTED = (120, 115, 105)     # Warm taupe / gray
BORDER_COLOR = (228, 222, 214)   # Subtle hairline border
ACCENT_GOLD = (184, 142, 85)     # Muted champagne gold

FONT_SERIF = "C:/Windows/Fonts/georgia.ttf"
FONT_SANS = "C:/Windows/Fonts/segoeui.ttf"
FONT_SANS_BOLD = "C:/Windows/Fonts/segoeuib.ttf"

def hex_to_rgb(hex_str: str) -> tuple:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 6:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    return (160, 140, 120)

def render_moodboard_card(
    title: str,
    subtitle: str,
    photographer_name: str,
    city: str,
    palette: List[Dict[str, str]], # [{"name": "Песочный", "hex": "#D8C4B6"}, ...]
    outfit_sections: List[Dict[str, Any]], # [{"role": "Мама", "items": ["..."]}, ...]
    location_note: str,
    output_path: str
) -> str:
    width = 1200
    height = 1600
    img = Image.new("RGB", (width, height), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Load fonts
    try:
        f_brand = ImageFont.truetype(FONT_SANS, 22)
        f_title = ImageFont.truetype(FONT_SERIF, 44)
        f_subtitle = ImageFont.truetype(FONT_SERIF, 24)
        f_section = ImageFont.truetype(FONT_SANS_BOLD, 22)
        f_body = ImageFont.truetype(FONT_SANS, 20)
        f_tag = ImageFont.truetype(FONT_SANS, 16)
        f_watermark = ImageFont.truetype(FONT_SANS, 18)
    except Exception:
        f_brand = f_title = f_subtitle = f_section = f_body = f_tag = f_watermark = ImageFont.load_default()

    # 1. Outer border frame
    draw.rectangle([40, 40, width - 40, height - 40], outline=BORDER_COLOR, width=2)
    draw.rectangle([48, 48, width - 48, height - 48], outline=BORDER_COLOR, width=1)

    # 2. Header: Photographer branding
    brand_text = f"ПЕРСОНАЛЬНЫЙ ГИД ПО СЪЕМКЕ · {photographer_name.upper()}"
    if city:
        brand_text += f" · {city.upper()}"
    draw.text((width // 2, 80), brand_text, fill=TEXT_MUTED, font=f_brand, anchor="mm")

    # Thin separator
    draw.line([width // 2 - 150, 105, width // 2 + 150, 105], fill=ACCENT_GOLD, width=2)

    # 3. Title & Concept
    draw.text((width // 2, 145), title.upper(), fill=TEXT_DARK, font=f_title, anchor="mm")
    draw.text((width // 2, 190), subtitle, fill=TEXT_MUTED, font=f_subtitle, anchor="mm")

    # 4. Color Palette Section
    pal_y = 230
    draw.rectangle([80, pal_y, width - 80, pal_y + 110], fill=CARD_BG, outline=BORDER_COLOR, width=1)
    draw.text((100, pal_y + 18), "ПАЛИТРА ЦВЕТОВ", fill=TEXT_MUTED, font=f_section)

    swatch_x = 320
    swatch_spacing = 135
    for idx, col in enumerate(palette[:6]):
        cx = swatch_x + idx * swatch_spacing
        cy = pal_y + 45
        r = 24
        rgb = hex_to_rgb(col.get("hex", "#A08C78"))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb, outline=BORDER_COLOR, width=1)
        name = col.get("name", "")[:12]
        draw.text((cx, cy + r + 8), name, fill=TEXT_DARK, font=f_tag, anchor="mt")

    # 5. Outfit / Mood Grid (4 Cards: 2x2)
    grid_top = 370
    card_w = 490
    card_h = 490
    spacing = 30
    positions = [
        (90, grid_top),
        (90 + card_w + spacing, grid_top),
        (90, grid_top + card_h + spacing),
        (90 + card_w + spacing, grid_top + card_h + spacing),
    ]

    for idx, sec in enumerate(outfit_sections[:4]):
        x, y = positions[idx]
        draw.rectangle([x, y, x + card_w, y + card_h], fill=CARD_BG, outline=BORDER_COLOR, width=1)
        
        # Header banner inside card
        draw.rectangle([x, y, x + card_w, y + 45], fill=(244, 241, 236))
        role_label = sec.get("role", f"Образ {idx+1}")
        draw.text((x + 20, y + 22), role_label.upper(), fill=TEXT_DARK, font=f_section, anchor="lm")

        # Items list
        items = sec.get("items", [])
        curr_y = y + 70
        for item in items[:6]:
            draw.text((x + 25, curr_y), "•", fill=ACCENT_GOLD, font=f_body)
            draw.text((x + 45, curr_y), str(item)[:48], fill=TEXT_DARK, font=f_body)
            curr_y += 38

        # Note / styling tip inside card
        tip = sec.get("tip", "")
        if tip:
            draw.rectangle([x + 15, y + card_h - 75, x + card_w - 15, y + card_h - 15], fill=(250, 249, 247))
            draw.text((x + 25, y + card_h - 60), "Стиль:", fill=ACCENT_GOLD, font=f_section)
            draw.text((x + 25, y + card_h - 35), tip[:55], fill=TEXT_MUTED, font=f_tag)

    # 6. Bottom Banner: Location & Atmosphere
    loc_y = grid_top + card_h * 2 + spacing + 30
    draw.rectangle([90, loc_y, width - 90, loc_y + 110], fill=CARD_BG, outline=BORDER_COLOR, width=1)
    draw.text((115, loc_y + 20), "СВЕТ И ЛОКАЦИЯ", fill=ACCENT_GOLD, font=f_section)
    draw.text((115, loc_y + 55), location_note[:110], fill=TEXT_DARK, font=f_body)

    # 7. Footer Watermark
    footer_text = f"Создано с заботой о вашей съемке · {photographer_name}"
    draw.text((width // 2, height - 60), footer_text, fill=TEXT_MUTED, font=f_watermark, anchor="mm")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=95)
    return output_path
