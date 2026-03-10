import os
import json
import time
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

def main():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
    })
    
    # 1. 最初にベースページにアクセスしてCookieを引き継ぐ
    print("Fetching base page to set cookies...")
    try:
        session.get('https://www.dlsite.com/girls-touch/', timeout=10)
    except Exception as e:
        print(f"Error fetching base page: {e}")
    time.sleep(1.2)
    
    url = 'https://www.dlsite.com/girls-touch/ranking/day'
    print(f"Fetching ranking page: {url}")
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching ranking page: {e}")
        return

    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # 画像の抽出
    # サムネイルはランキングページのHTML内 template[data-id] の data-samples 属性に含まれている
    thumbnails = {}
    for t in soup.select('template[data-id]'):
        data_id = t.get('data-id')
        data_samples = t.get('data-samples')
        if data_id and data_samples:
            try:
                # DLsite usually embeds JSON strings in data-samples "[{...}]"
                samples = json.loads(data_samples)
                if isinstance(samples, list) and len(samples) > 0 and 'url' in samples[0]:
                    thumbnails[data_id] = "https:" + samples[0]['url']
                elif isinstance(samples, str):
                    thumbnails[data_id] = "https:" + samples if samples.startswith('//') else samples
            except:
                if data_samples.startswith('//'):
                    thumbnails[data_id] = "https:" + data_samples
                else:
                    thumbnails[data_id] = data_samples

    ranking = []
    
    # 作品ごとの要素を取得
    # .n_worklist_item または類似のコンテナを探す
    item_nodes = soup.select('.n_worklist_item, .work_1col, .work_item, .ranking_item')
    if not item_nodes:
        # Fallback: find any element containing a link to a work RJ...
        all_links = soup.find_all('a', href=re.compile(r'/work/=/product_id/RJ\d+'))
        # Get unique parent containers
        parents = []
        for a in all_links:
            p = a.find_parent('td') or a.find_parent('li') or a.find_parent('div', class_=re.compile(r'item|work'))
            if p and p not in parents:
                parents.append(p)
        item_nodes = parents

    print(f"Found {len(item_nodes)} item nodes.")
    
    rank = 1
    exclude_tags = {'マンガ', 'ボイス・ASMR', 'ゲーム', '動画'}
    
    for node in item_nodes:
        if rank > 30:
            break
            
        a_tag = node.find('a', href=re.compile(r'/work/=/product_id/(RJ\d+)'))
        if not a_tag:
            continue
            
        product_id = re.search(r'RJ\d+', a_tag['href']).group(0)
        
        # skip 000
        if product_id.endswith('000'):
            continue
            
        # Title
        title = a_tag.get_text(strip=True) or a_tag.get('title', '')
        if not title:
            title_node = node.select_one('.work_name')
            if title_node:
                title = title_node.get_text(strip=True)
                
        link = a_tag['href']
        
        # Circle
        circle_node = node.select_one('.maker_name, .circle')
        circle = circle_node.get_text(strip=True) if circle_node else "Unknown"
        
        node_text = node.get_text(" ", strip=True)
        
        # Price extraction: 50,000円以下の最大価格を正規価格として採用
        prices = [int(p) for p in re.findall(r'(\d{1,3}(?:,\d{3})*|\d+)\s*円', node_text.replace(',', ''))]
        valid_prices = [p for p in prices if p <= 50000]
        price = max(valid_prices) if valid_prices else 0
        
        # Tags: aタグのうち、hrefに 'tag' か 'genre' を含むもの
        all_tags = [a.get_text(strip=True) for a in node.find_all('a') if a.get('href') and ('tag' in a.get('href') or 'genre' in a.get('href'))]
        tags = [t for t in all_tags if t not in exclude_tags]
        
        # Subgenre filter: remove generic terms if misclassified
        tags = [t for t in tags if t and t != '']
        
        # DL count
        dl_match = re.search(r'([\d,]+)\s*(?:DL|ダウンロード)', node_text)
        downloads = int(dl_match.group(1).replace(',', '')) if dl_match else 0
        
        # Date: YYYY年MM月DD日 または YYYY/MM/DD
        date_match = re.search(r'(\d{4})[年/]\s*(\d{1,2})[月/]\s*(\d{1,2})', node_text)
        release_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}" if date_match else ""
        
        thumb_url = thumbnails.get(product_id, "")
        if not thumb_url:
            # Fallback inline img
            img = node.find('img')
            if img:
                thumb_url = img.get('src') or img.get('data-src') or ""
                if thumb_url.startswith('//'):
                    thumb_url = "https:" + thumb_url
                    
        ranking.append({
            "rank": rank,
            "id": product_id,
            "title": title,
            "circle": circle,
            "url": link,
            "price": price,
            "tags": list(set(tags)),
            "downloads": downloads,
            "release_date": release_date,
            "thumbnail": thumb_url
        })
        print(f"Parsed rank {rank}: {title[:15]}... ({price}円, {downloads}DL)")
        rank += 1
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Save ranking_data.json
    with open('ranking_data.json', 'w', encoding='utf-8') as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)
        
    # Tag ranking
    tag_counts = {}
    for item in ranking:
        for tag in item['tags']:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    with open('tag_ranking.json', 'w', encoding='utf-8') as f:
        json.dump([{"tag": t, "count": c} for t, c in sorted_tags], f, ensure_ascii=False, indent=2)
        
    # History
    history = {}
    if os.path.exists('ranking_history.json'):
        with open('ranking_history.json', 'r', encoding='utf-8') as f:
            try:
                history = json.load(f)
            except:
                pass
                
    history[today_str] = ranking
    
    # Keep only last 90 days
    sorted_dates = sorted(history.keys())
    if len(sorted_dates) > 90:
        for d in sorted_dates[:-90]:
            del history[d]
            
    with open('ranking_history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print("Scraping completed successfully.")

if __name__ == "__main__":
    main()
