import requests
from bs4 import BeautifulSoup
import re
import math
import json
import time
import gzip
from datetime import datetime
from io import BytesIO
from PIL import Image

def get_dominant_color_category(img_url, session):
    try:
        r = session.get(img_url, timeout=5)
        if r.status_code != 200:
            return "取得失敗"
        img = Image.open(BytesIO(r.content)).convert('RGB')
        img.thumbnail((50, 50))
        colors = img.getcolors(50 * 50)
        colors.sort(reverse=True, key=lambda x: x[0])
        dominant_rgb = colors[0][1]
        categories = {
            '黒髪系/ダーク': (30, 30, 30),
            'ホワイト/明るめ': (240, 240, 240),
            'ネオンピンク': (255, 105, 180),
            'ブルー系': (100, 149, 237),
            'レッド/情熱': (220, 20, 60),
            'パープル/小悪魔': (138, 43, 226),
            'イエロー/ブロンド': (255, 215, 0),
            'グリーン/ナチュラル': (60, 179, 113),
            'ブラウン/肌色系': (210, 180, 140)
        }
        min_dist = float('inf')
        closest_name = "その他"
        for name, code in categories.items():
            dist = (dominant_rgb[0] - code[0])**2 + (dominant_rgb[1] - code[1])**2 + (dominant_rgb[2] - code[2])**2
            if dist < min_dist:
                min_dist = dist
                closest_name = name
        return closest_name
    except:
        return "取得失敗"

def scrape_garumani():
    session = requests.Session()
    session.get("https://www.dlsite.com/girls-touch/", timeout=15)
    time.sleep(1.5)

    url = "https://www.dlsite.com/girls-touch/ranking/day?sort=sale"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    res = session.get(url, headers=headers, timeout=15)

    if res.content[:2] == b'\x1f\x8b':
        text = gzip.decompress(res.content).decode('utf-8', errors='replace')
    else:
        text = res.text
    print(f"[DEBUG] status={res.status_code} len={len(text)}")
    print(text[:2000])

    soup = BeautifulSoup(text, 'html.parser')

    thumb_map = {}
    templates = soup.find_all('template')
    for t in templates:
        data_id = t.get('data-id')
        if data_id and data_id.startswith('RJ'):
            num_str = data_id[2:]
            try:
                num_int = int(num_str)
                folder_num = math.ceil(num_int / 1000) * 1000
                folder_id = f"RJ{str(folder_num).zfill(len(num_str))}"
                thumb_map[data_id] = f"https://img.dlsite.jp/modpub/images2/work/doujin/{folder_id}/{data_id}_img_main.jpg"
            except:
                thumb_map[data_id] = ""

    ranking_items = soup.select('.n_worklist_item')
    if not ranking_items:
        ranking_items = soup.select('.n_work_item')
    if not ranking_items:
        ranking_items = soup.select('.work_1col')

    print(f"[DEBUG] 取得件数: {len(ranking_items)}")
    ranking_items = ranking_items[:30]

    processed_data = []
    all_tags_count = {}
    all_colors_count = {}

    for item in ranking_items:
        try:
            id_link = item.select_one('a[href*="RJ"]')
            if not id_link:
                continue
            href = id_link.get('href', '')
            work_id_match = re.search(r'RJ\d+', href)
            if not work_id_match:
                continue
            work_id = work_id_match.group()
            if work_id.endswith('000'):
                continue
            title_elem = item.select_one('.work_name') or item.select_one('.n_work_name a')
            title = title_elem.get_text(strip=True) if title_elem else "不明なタイトル"
            circle_elem = item.select_one('.maker_name') or item.select_one('.work_maker') or item.select_one('.n_maker_name a')
            circle = circle_elem.get_text(strip=True) if circle_elem else "不明なサークル"
            work_url = f"https://www.dlsite.com/girls-touch/work/=/product_id/{work_id}.html"
            full_text = item.get_text(" ", strip=True)
            price_matches = re.findall(r'(\d{1,3}(?:,\d{3})*)\s?円', full_text)
            prices = [int(p.replace(',', '')) for p in price_matches]
            base_price = max([p for p in prices if p <= 50000]) if prices else 0
            dl_count = 0
            dl_elem = item.select_one('.work_dl_count .count_num') or item.select_one('.work_dl_count')
            if dl_elem:
                dl_text = re.sub(r'[^\d]', '', dl_elem.get_text())
                dl_count = int(dl_text) if dl_text else 0
            date_match = re.search(r'\d{4}[年/]\d{1,2}[月/]\d{1,2}', full_text)
            release_date = date_match.group().replace('年', '-').replace('月', '-').replace('/', '-') if date_match else "不明"
            exclude_formats = {"マンガ", "ボイス・ASMR", "ゲーム", "動画", "その他", "少女マンガ", "同人誌", "CG・イラスト"}
            filtered_tags = []
            raw_tags_elems = item.select('.work_genre a, a[href*="/genre/"]')
            for t_elem in raw_tags_elems:
                t_text = t_elem.get_text(strip=True).replace('#', '').strip()
                t_text = re.sub(r'^\d+\s*', '', t_text)
                if t_text and t_text not in exclude_formats and t_text not in filtered_tags:
                    filtered_tags.append(t_text)
            for tag in filtered_tags:
                all_tags_count[tag] = all_tags_count.get(tag, 0) + 1
            thumb_url = thumb_map.get(work_id, "")
            color_category = "取得失敗"
            if thumb_url:
                color_category = get_dominant_color_category(thumb_url, session)
                if color_category != "取得失敗":
                    all_colors_count[color_category] = all_colors_count.get(color_category, 0) + 1
            processed_data.append({
                "rank": len(processed_data) + 1,
                "id": work_id,
                "title": title,
                "circle": circle,
                "price": base_price,
                "dl": dl_count,
                "date": release_date,
                "tags": filtered_tags,
                "thumb": thumb_url,
                "url": work_url
            })
            time.sleep(0.5)
        except Exception as e:
            print(f"Error processing item: {e}")
            continue

    with open('ranking_data.json', 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=2)
    tag_ranking = sorted([{"tag": k, "count": v} for k, v in all_tags_count.items()], key=lambda x: x['count'], reverse=True)[:20]
    with open('tag_ranking.json', 'w', encoding='utf-8') as f:
        json.dump(tag_ranking, f, ensure_ascii=False, indent=2)
    color_ranking = sorted([{"color": k, "count": v} for k, v in all_colors_count.items()], key=lambda x: x['count'], reverse=True)
    with open('color_ranking.json', 'w', encoding='utf-8') as f:
        json.dump(color_ranking, f, ensure_ascii=False, indent=2)
    try:
        with open('ranking_history.json', 'r', encoding='utf-8') as f:
            history = json.load(f)
            if not isinstance(history, list):
                history = []
    except:
        history = []
    today_str = datetime.now().strftime('%Y-%m-%d')
    history = [h for h in history if isinstance(h, dict) and h.get('date') != today_str]
    history.append({"date": today_str, "data": processed_data})
    history = history[-90:]
    with open('ranking_history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 完了: {len(processed_data)}件取得")

if __name__ == "__main__":
    scrape_garumani()
