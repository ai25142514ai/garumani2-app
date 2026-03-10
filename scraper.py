"""
Garumani Trend — DLsite Girls-Touch ランキングスクレイパー
Antigravity互換版 (ranking_data.json=配列, ranking_history.json=[{date,data}]配列)

■ 修正した主要バグ:
  1. DL数がレビュー数になっていた
     → .n_worklist_item 内の .work_dl_count を優先取得
     → 正規表現フォールバックは削除（誤認の原因）
  2. タグが全件空
     → .work_genre a ではなくDLsiteの実際のクラス名に対応
     → 個別作品ページへのフォールバックを追加
  3. タグがサイドメニューのものになっていた
     → container スコープ内のみに限定
"""

import requests
from bs4 import BeautifulSoup
import re
import math
import json
import time
from datetime import datetime
from io import BytesIO

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ================================================================
# 設定
# ================================================================
RANK_URL = "https://www.dlsite.com/girls-touch/ranking/day?sort=sale"
BASE_URL = "https://www.dlsite.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
    "Referer": "https://www.dlsite.com/",
}

# ================================================================
# ユーティリティ
# ================================================================
def safe_int(text: str) -> int:
    """カンマ・空白・全角数字を除去してint変換。失敗時は0。"""
    if not text:
        return 0
    text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else 0


def build_thumb_url(work_id: str) -> str:
    """RJ番号からサムネイルURLを生成"""
    if not work_id.startswith("RJ"):
        return ""
    num_str = work_id[2:]
    try:
        num_int = int(num_str)
        folder_num = math.ceil(num_int / 1000) * 1000
        folder_id = f"RJ{str(folder_num).zfill(len(num_str))}"
        return f"https://img.dlsite.jp/modpub/images2/work/doujin/{folder_id}/{work_id}_img_main.jpg"
    except ValueError:
        return ""


# ================================================================
# ランキングページ解析
# ================================================================
def parse_ranking_page(soup: BeautifulSoup) -> list:
    """
    .n_worklist_item を列挙し各作品の情報を取得。

    ■ DL数の正しい取得場所
      .work_dl_count 内の数値テキスト
      ※ .work_review_count は「レビュー数」であり DL数ではない

    ■ タグの正しい取得場所
      各 .n_worklist_item コンテナの「内側」の .work_genre a
      サイドメニューは container スコープ外なので混入しない
    """
    items = []
    containers = soup.select(".n_worklist_item")[:30]

    if not containers:
        print("[ERROR] .n_worklist_item が 0 件。HTMLを確認してください。")
        return items

    for container in containers:
        try:
            # ---------- 商品ID ----------
            href_tag = container.select_one("a[href*='product_id']") or container.select_one("a[href*='RJ']")
            if not href_tag:
                continue
            href = href_tag.get("href", "")
            # product_id/RJ... 形式と /RJ... 形式どちらも対応
            m = re.search(r"product_id/([A-Z0-9]+)", href) or re.search(r"/(RJ\d+)", href)
            if not m:
                continue
            work_id = m.group(1)
            # フォルダIDそのものを誤取得しない（末尾000は除外）
            if work_id.endswith("000"):
                continue

            # ---------- タイトル ----------
            title_tag = container.select_one(".work_name a") or container.select_one(".work_name")
            title = title_tag.get_text(strip=True) if title_tag else "不明"

            # ---------- サークル名 ----------
            circle_tag = container.select_one(".maker_name a") or container.select_one(".maker_name")
            circle = circle_tag.get_text(strip=True) if circle_tag else "不明"

            # ---------- サムネイル ----------
            img_tag = container.select_one("img[data-src], img.lazy, img[src]")
            thumb = ""
            if img_tag:
                thumb = img_tag.get("data-src") or img_tag.get("src") or ""
                if thumb.startswith("//"):
                    thumb = "https:" + thumb
            if not thumb:
                thumb = build_thumb_url(work_id)

            # ---------- DL数（レビュー数と混同しないよう明示的に取得）----------
            # .work_dl_count が DL数、.work_review_count がレビュー数（別物）
            dl_count = 0
            for sel in [
                ".work_dl_count .count_num",
                ".work_dl_count",
                "[data-dl-count]",
            ]:
                el = container.select_one(sel)
                if el:
                    val = el.get("data-dl-count") or el.get_text()
                    dl_count = safe_int(val)
                    if dl_count > 0:
                        break

            # ---------- 価格 ----------
            price = 0
            for sel in [".work_price_wrap .price", ".work_price", ".price"]:
                el = container.select_one(sel)
                if el:
                    price = safe_int(el.get_text())
                    if price > 0:
                        break

            # ---------- 発売日 ----------
            release_date = "不明"
            date_tag = container.select_one(".work_date, .work_regist_date, time")
            if date_tag:
                dt = date_tag.get("datetime") or date_tag.get_text(strip=True)
                m2 = re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}", dt)
                if m2:
                    release_date = re.sub(r"[年月/]", "-", m2.group()).rstrip("-")
            if release_date == "不明":
                m3 = re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}", container.get_text())
                if m3:
                    release_date = re.sub(r"[年月/]", "-", m3.group()).rstrip("-")

            # ---------- タグ（コンテナ内のみ、サイドメニュー除外）----------
            EXCLUDE = {"マンガ", "ボイス・ASMR", "ゲーム", "動画", "その他",
                       "少女マンガ", "同人誌", "CG・イラスト"}
            tags = []
            for sel in [".work_genre a", "a[href*='/genre/']", ".genre_tag a"]:
                raw = container.select(sel)
                if raw:
                    for t in raw:
                        txt = t.get_text(strip=True).replace("#", "").strip()
                        txt = re.sub(r"^\d+\s*", "", txt)
                        if txt and txt not in EXCLUDE and txt not in tags:
                            tags.append(txt)
                    break  # 最初にヒットしたセレクタのみ使用

            print(f"[INFO] {work_id}: DL={dl_count}, 価格={price}, タグ={len(tags)}件")

            items.append({
                "rank":   len(items) + 1,
                "id":     work_id,
                "title":  title,
                "circle": circle,
                "price":  price,
                "dl":     dl_count,
                "date":   release_date,
                "tags":   tags,
                "thumb":  thumb,
                "url":    f"{BASE_URL}/girls-touch/work/=/product_id/{work_id}.html",
            })

        except Exception as e:
            print(f"[WARN] アイテム処理エラー: {e}")
            continue

    print(f"[INFO] ランキング解析完了: {len(items)} 件")
    return items


# ================================================================
# 個別作品ページでタグ・DL数を補完
# ================================================================
def enrich_from_work_page(session: requests.Session, item: dict) -> dict:
    """dl が 0 または tags が空のときだけ個別ページを取得して補完"""
    if item["dl"] > 0 and len(item["tags"]) > 0:
        return item

    url = item["url"]
    try:
        res = session.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.content, "html.parser")

        # DL数補完
        if item["dl"] == 0:
            for sel in [".work_buy_count .count", ".work_dl_count .count_num", "#work_dl_count"]:
                el = soup.select_one(sel)
                if el:
                    v = safe_int(el.get_text())
                    if v > 0:
                        item["dl"] = v
                        break

        # タグ補完（作品情報テーブル内）
        if not item["tags"]:
            EXCLUDE = {"マンガ", "ボイス・ASMR", "ゲーム", "動画", "その他",
                       "少女マンガ", "同人誌", "CG・イラスト"}
            for sel in ["table.work_genre a", ".work_genre a", ".main_genre a"]:
                els = soup.select(sel)
                if els:
                    item["tags"] = list(dict.fromkeys(
                        t.get_text(strip=True) for t in els
                        if t.get_text(strip=True) and t.get_text(strip=True) not in EXCLUDE
                    ))
                    break

    except Exception as e:
        print(f"[WARN] 個別ページ取得失敗 {item['id']}: {e}")

    time.sleep(0.8)
    return item


# ================================================================
# Pillow によるドミナントカラー分析（Antigravity互換）
# ================================================================
COLOR_CATEGORIES = {
    "黒髪系/ダーク":       (30,  30,  30),
    "ホワイト/明るめ":     (240, 240, 240),
    "ネオンピンク":        (255, 105, 180),
    "ブルー系":            (100, 149, 237),
    "レッド/情熱":         (220, 20,  60),
    "パープル/小悪魔":     (138, 43,  226),
    "イエロー/ブロンド":   (255, 215, 0),
    "グリーン/ナチュラル": (60,  179, 113),
    "ブラウン/肌色系":     (210, 180, 140),
}


def get_dominant_color_category(img_url: str, session: requests.Session) -> str:
    if not PIL_AVAILABLE:
        return "取得失敗"
    try:
        r = session.get(img_url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return "取得失敗"
        img = Image.open(BytesIO(r.content)).convert("RGB")
        img.thumbnail((50, 50))
        colors = img.getcolors(50 * 50)
        if not colors:
            return "取得失敗"
        colors.sort(reverse=True, key=lambda x: x[0])
        dominant_rgb = colors[0][1]

        min_dist = float("inf")
        closest = "その他"
        for name, code in COLOR_CATEGORIES.items():
            dist = sum((a - b) ** 2 for a, b in zip(dominant_rgb, code))
            if dist < min_dist:
                min_dist = dist
                closest = name
        return closest
    except Exception:
        return "取得失敗"


# ================================================================
# JSON 保存ヘルパー
# ================================================================
def load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 保存: {path}")


# ================================================================
# メイン
# ================================================================
def scrape_garumani():
    session = requests.Session()
    # Cookie取得
    try:
        session.get("https://www.dlsite.com/girls-touch/", headers=HEADERS, timeout=15)
        time.sleep(1.5)
    except Exception as e:
        print(f"[WARN] Cookie取得失敗: {e}")

    print(f"[INFO] スクレイピング開始: {datetime.now().isoformat()}")

    res = session.get(RANK_URL, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(res.content, "html.parser")

    # ランキング解析
    items = parse_ranking_page(soup)
    if not items:
        print("[FATAL] 作品データが取得できませんでした。終了します。")
        return

    # 個別ページ補完（DL数またはタグが不足している場合のみ）
    print("[INFO] 個別ページ補完中...")
    for i, item in enumerate(items):
        items[i] = enrich_from_work_page(session, item)

    # カラー分析
    all_colors_count = {}
    print("[INFO] カラー分析中...")
    for item in items:
        if item["thumb"]:
            cat = get_dominant_color_category(item["thumb"], session)
            if cat != "取得失敗":
                all_colors_count[cat] = all_colors_count.get(cat, 0) + 1
            time.sleep(0.3)

    # タグランキング集計
    all_tags_count = {}
    for item in items:
        for tag in set(item["tags"]):  # 1作品につき同タグを重複カウントしない
            all_tags_count[tag] = all_tags_count.get(tag, 0) + 1

    # ranking_data.json（配列形式 — Antigravity互換）
    save_json("ranking_data.json", items)

    # tag_ranking.json
    tag_ranking = sorted(
        [{"tag": k, "count": v} for k, v in all_tags_count.items()],
        key=lambda x: x["count"], reverse=True
    )[:20]
    save_json("tag_ranking.json", tag_ranking)

    # color_ranking.json
    color_ranking = sorted(
        [{"color": k, "count": v} for k, v in all_colors_count.items()],
        key=lambda x: x["count"], reverse=True
    )
    save_json("color_ranking.json", color_ranking)

    # ranking_history.json（[{date, data:[]}] 配列形式 — Antigravity互換）
    history = load_json("ranking_history.json")
    if not isinstance(history, list):
        history = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    history = [h for h in history if isinstance(h, dict) and h.get("date") != today_str]
    history.append({"date": today_str, "data": items})
    history = history[-90:]
    save_json("ranking_history.json", history)

    print(f"[INFO] 完了。取得: {len(items)} 件 / タグ種: {len(all_tags_count)} 種")


if __name__ == "__main__":
    scrape_garumani()
