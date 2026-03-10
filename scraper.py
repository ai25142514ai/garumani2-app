import requests
from bs4 import BeautifulSoup
import re
import json
import time
from datetime import datetime

def scrape_garumani():
    session = requests.Session()
    # Cookie取得とGirls版への明示的アクセス
    session.get("https://www.dlsite.com/girls-touch/", timeout=15)
    time.sleep(1.5)

    url = "https://www.dlsite.com/girls-touch/ranking/day"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'}
    res = session.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(res.content, 'html.parser')

    # サムネイル情報の抽出用
    templates = soup.find_all('template')
    thumb_map = {}
    for t in templates:
        data_id = t.get('data-id')
        data_samples = t.get('data-samples')
        if data_id and data_samples:
            thumb_url = "https:" + data_samples.split(',')[0]
            thumb_map[data_id] = thumb_url

    # ランキングアイテムの取得
    ranking_items = soup.select('.n_worklist_item')
    if not ranking_items:
        ranking_items = soup.select('.work_1col') # 予備のセレクタ
    ranking_items = ranking_items[:30]

    processed_data = []
    all_tags_count = {}

    for item in ranking_items:
        # RJ番号の取得
        id_link = item.select_one('a[href*="RJ"]')
        if not id_link: continue
        work_id = re.search(r'RJ\d+', id_link['href']).group()
        if work_id.endswith('000'): continue

        title = item.select_one('.work_name').get_text(strip=True)

        # サークル名の取得 (セレクタを強化)
        circle_elem = item.select_one('.maker_name') or item.select_one('.work_maker')
        circle = circle_elem.get_text(strip=True) if circle_elem else "不明なサークル"

        work_url = id_link['href']
        full_text = item.get_text(" ", strip=True) # スペース区切りで取得

        # 価格の抽出 (50,000円以下の最大値)
        prices = [int(p.replace(',', '')) for p in re.findall(r'(\d{1,3}(?:,\d{3})*)円', full_text)]
        base_price = max([p for p in prices if p <= 50000]) if prices else 0

        # DL数の抽出 (「12,345 DL」や「500+ ダウンロード」に対応)
        dl_match = re.search(r'([\d,]+)(?:\s?DL|ダウンロード)', full_text)
        dl_count = int(dl_match.group(1).replace(',', '')) if dl_match else 0

        # 発売日の抽出
        date_match = re.search(r'\d{4}/\d{2}/\d{2}', full_text)
        release_date = date_match.group() if date_match else "不明"

        # タグの取得 (除外設定)
        exclude_formats = ["マンガ", "ボイス・ASMR", "ゲーム", "動画", "その他", "少女マンガ", "同人誌"]
        raw_tags = item.select('.search_tag a')
        filtered_tags = []
        for t_elem in raw_tags:
            t_text = t_elem.get_text(strip=True)
            if t_text and t_text not in exclude_formats:
                filtered_tags.append(t_text)
                all_tags_count[t_text] = all_tags_count.get(t_text, 0) + 1

        processed_data.append({
            "rank": len(processed_data) + 1,
            "id": work_id,
            "title": title,
            "circle": circle,
            "price": base_price,
            "dl": dl_count,
            "date": release_date,
            "tags": filtered_tags,
            "thumb": thumb_map.get(work_id, ""),
            "url": work_url
        })
        time.sleep(1.2)

    # JSON保存
    with open('ranking_data.json', 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=2)

    # タグランキングの生成
    tag_ranking = sorted([{"tag": k, "count": v} for k, v in all_tags_count.items()], key=lambda x: x['count'], reverse=True)[:20]
    with open('tag_ranking.json', 'w', encoding='utf-8') as f:
        json.dump(tag_ranking, f, ensure_ascii=False, indent=2)

    # 履歴の更新 (読み込みエラー対策を強化)
    try:
        with open('ranking_history.json', 'r', encoding='utf-8') as f:
            history = json.load(f)
            if not isinstance(history, list):
                history = []
    except:
        history = []
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    # 各要素が辞書形式であることを確認してからフィルタリングする
    history = [h for h in history if isinstance(h, dict) and h.get('date') != today_str]
    history.append({"date": today_str, "data": processed_data})
    history = history[-90:]

    with open('ranking_history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    scrape_garumani()
