from pathlib import Path
from bs4 import BeautifulSoup

for html_name in ["messages.html", "messages2.html"]:
    p = Path(r"C:\Users\пп\Desktop\вика курсы") / html_name
    if not p.exists():
        continue
    soup = BeautifulSoup(p.read_bytes(), "html.parser")
    history = soup.find("div", class_="history")
    msgs = history.find_all("div", class_="message") if history else []
    
    parsed = []
    for m in msgs:
        classes = m.get("class", [])
        if "service" in classes:
            continue
        text_div = m.find("div", class_="text")
        text = text_div.get_text(" ", strip=True) if text_div else ""
        
        media_links = []
        for a in m.find_all("a"):
            href = a.get("href", "")
            if any(href.startswith(pref) for pref in ["files/", "video_files/", "voice_messages/", "photos/"]):
                media_links.append(href)
                
        if not text and not media_links:
            continue
            
        date_div = m.find("div", class_="date")
        date_str = date_div.get("title", "") if date_div else ""
        
        parsed.append({"id": m.get("id"), "date": date_str, "text": text, "media": media_links})
        
    print(f"{html_name}: {len(msgs)} raw messages -> {len(parsed)} educational messages with lessons/media")
    for item in parsed[:3]:
        print(f"  [{item['date']}] {item['text'][:60]} -> {item['media']}")
