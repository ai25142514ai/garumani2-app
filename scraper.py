import json
import time
import re
import math
from datetime import datetime
from playwright.sync_api import sync_playwright

def scrape_garumani():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            locale='ja-JP',
        )
        page = context.new_page()

        print("[INFO] DLsiteにアクセス中...")
        page.goto("https://www.dlsite.com/girls-touch/ranking/day?sort=sale", timeout=30000)
        page.wait_for_timeout(3000)

        html = page.content()
        print(f"[DEBUG] HTML文字数: {len(html)}")
        print(html[:3000])

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        ranking_items = soup.select('.n_worklist_item')
        print(f"[DEBUG] 取得件数: {len(ranking_items)}")

        processed_data = []
        all_tags_count = {}

        for item in ranking_items[:30]:
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
                title = title_elem.get_text(strip=True) if title_elem else "不明"

                circle_elem = item.select_one('.maker_name') or item.select_one('.work_maker') or item.select_one('.n_maker_name a')
                circle = circle_elem.get_text(strip=True) if circle_elem else "不明"

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

                num_str = work_id[2:]
                try:
                    num_int = int(num_str)
                    folder_num = math.ceil(num_int / 1000) * 1000
                    folder_id = f"RJ{str(folder_num).zfill(len(num_str))}"
                    thumb_url = f"https://img.dlsite.jp/modpub/images2/work/doujin/{folder_id}/{work_id}_img_main.jpg"
                except:
                    thumb_url = ""

                work_url = f"https://www.dlsite.com/girls-touch/work/=/product_id/{work_id}.html"

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

            except Exception as e:
                print(f"Error: {e}")
                continue

        browser.close()

    with open('ranking_data.json', 'w', encoding='utf-8') as f:
        json.dump(processed​​​​​​​​​​​​​​​​
