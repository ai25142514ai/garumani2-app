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
            # `data_id` から `RJxxxxxx` 形式のメイン画像URLを直接生成する (確実な直リンク)
            if data_id.startswith('RJ'):
                # 前方一致で RJ 以下の数字部分を使う (RJ123456 -> RJ123456_img_main.jpg)
                thumb_map[data_id] = f"https://img.dlsite.jp/modpub/images2/work/doujin/{data_id}/{data_id}_img_main.jpg"
            else:
                thumb_map[data_id] = ""

    # ランキングアイテムの取得
    ranking_items = soup.select('.n_work_item')
    if not ranking_items:
        ranking_items = soup.select('.work_1col') # 予備のセレクタ
    ranking_items = ranking_items[:30]

    processed_data = []
    all_tags_count = {}

    for item in ranking_items:
        try:
            # RJ番号の取得
            id_link = item.select_one('a[href*="RJ"]')
            if not id_link: continue
            
            href = id_link.get('href', '')
            work_id_match = re.search(r'RJ\d+', href)
            if not work_id_match: continue
            
            work_id = work_id_match.group()
            if work_id.endswith('000'): continue

            title_elem = item.select_one('.work_name') or item.select_one('.n_work_name a')
            title = title_elem.get_text(strip=True) if title_elem else "不明なタイトル"

            circle_elem = item.select_one('.maker_name') or item.select_one('.work_maker') or item.select_one('.n_maker_name a')
            circle = circle_elem.get_text(strip=True) if circle_elem else "不明なサークル"

            work_url = href
            full_text = item.get_text(" ", strip=True) # スペース区切りで取得

            # 価格の抽出 (50,000円以下の最大値) (\d{1,3}(?:,\d{3})*)\s?円 という正規表現を使用
            price_matches = re.findall(r'(\d{1,3}(?:,\d{3})*)\s?円', full_text)
            prices = [int(p.replace(',', '')) for p in price_matches]
            base_price = max([p for p in prices if p <= 50000]) if prices else 0

            # DL数の抽出: 価格より後に出現する最初のカッコ内の数字 \(\s?([\d,]+)\s?\) を抽出
            dl_count = 0
            if base_price > 0:
                # 雑ですが、テキスト全体からカッコ内のDL数を拾う
                dl_match = re.search(r'\(\s?([\d,]+)\s?\)', full_text)
                if dl_match:
                    dl_count = int(dl_match.group(1).replace(',', ''))
            
            if dl_count == 0:
                # 念のため元のフォールバックも残す
                dl_match_alt = re.search(r'([\d,]+)(?:\s?DL|ダウンロード)', full_text)
                if dl_match_alt:
                    dl_count = int(dl_match_alt.group(1).replace(',', ''))

            # 発売日の抽出
            date_match = re.search(r'\d{4}[年/]\d{1,2}[月/]\d{1,2}', full_text)
            release_date = date_match.group().replace('年', '-').replace('月', '-').replace('/', '-') if date_match else "不明"

            # タグの取得 (詳細ページへアクセスして取得)
            exclude_formats = {"マンガ", "ボイス・ASMR", "ゲーム", "動画", "その他", "少女マンガ", "同人誌", "CG・イラスト"}
            # ブラックリストの文字列を含むものを除外
            blacklist_words = ["ジャンル一覧", "保存した検索条件", "割引中", "クーポン", "一覧へ", "すべて見る", "ランキング"]
            filtered_tags = []
            voice_actors = set()
            
            try:
                # 紳士的なスクレイピングのための待機 (一覧取得後も最低限待機)
                time.sleep(1.5)
                
                # 個別ページへアクセス
                detail_res = session.get(work_url, headers=headers, timeout=15)
                detail_soup = BeautifulSoup(detail_res.content, 'html.parser')

                # 作品詳細のメインエリアにあるジャンルタグのみを抽出（サイドバーのランキング等を無視）
                raw_tags_elems = detail_soup.select('.main_genre a[href*="/genre/"]')
                
                for t_elem in raw_tags_elems:
                    t_text = t_elem.get_text(strip=True)
                    if not t_text: continue
                    
                    # 不要な記号を除外し、前後の空白を取る
                    clean_text = t_text.replace('#', '').strip()
                    
                    # 先頭の数字とそれに続く不要な空白を除去 (例: "4クンニ" -> "クンニ")
                    clean_text = re.sub(r'^\d+\s*', '', clean_text)
                    
                    # ブラックリスト確認（ノイズの除去）
                    if any(bw in clean_text for bw in blacklist_words):
                        continue
                        
                    # 声優名ならスキップ
                    if clean_text in voice_actors:
                        continue
                        
                    # 除外フォーマットに含まれておらず、空でなければ追加
                    if clean_text and clean_text not in exclude_formats:
                        filtered_tags.append(clean_text)
                            
            except Exception as tag_e:
                print(f"[DEBUG] 詳細ページからのタグ取得失敗 - ID: {work_id}, URL: {work_url}, Error: {tag_e}")

            unique_tags = list(set(filtered_tags))
            print(f"Work {work_id}: Found {len(unique_tags)} tags")

            for tag in unique_tags: # 重複を避けてカウント
                all_tags_count[tag] = all_tags_count.get(tag, 0) + 1
                        
            # デバッグ情報出力
            if base_price == 0 or dl_count == 0 or not filtered_tags:
                print(f"[DEBUG] 取得漏れあり - ID: {work_id}")
                print(f"Price: {base_price}, DL: {dl_count}, Tags: {filtered_tags}")
                print(f"Raw text:\n{full_text}\n---")

            processed_data.append({
                "rank": len(processed_data) + 1,
                "id": work_id,
                "title": title,
                "circle": circle,
                "price": base_price,
                "dl": dl_count,
                "date": release_date,
                "tags": list(set(filtered_tags)),
                "thumb": thumb_map.get(work_id, ""),
                "url": work_url
            })
            time.sleep(1.2)
        except Exception as e:
            print(f"Error processing item: {e}")
            continue

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
    # 各要素が辞書形式であることを確認してからフィルタリングする (リスト形式の保証)
    history = [h for h in history if isinstance(h, dict) and h.get('date') != today_str]
    history.append({"date": today_str, "data": processed_data})
    history = history[-90:]

    with open('ranking_history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    scrape_garumani()
