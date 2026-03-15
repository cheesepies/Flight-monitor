#!/usr/bin/env python3
"""
机票价格监控 — 东京 ↔ 香港
使用 fast-flights（免费，无次数限制）+ Bark 推送
"""

import os
import json
import time
import urllib.parse
import requests
from datetime import datetime
from pathlib import Path
from fast_flights import FlightData, Passengers, Result, get_flights

# ─── 你的配置（修改这里）────────────────────────────────────────────────────

BARK_KEY = os.environ.get("BARK_KEY", "")
BARK_URL = os.environ.get("BARK_URL", "https://api.day.app")

# 出发地 / 目的地
ORIGIN      = "TYO"   # 东京（会自动搜索成田+羽田）
DESTINATION = "HKG"   # 香港

# 你可接受的去程日期（按优先顺序）
OUTBOUND_DATES = ["2025-08-08", "2025-08-09"]

# 你可接受的回程日期（按优先顺序）
INBOUND_DATES = ["2025-08-15", "2025-08-16"]

# 往返总价目标（日元）—— 低于此价或刷新历史最低时推送
TARGET_PRICE = 36000

PASSENGERS = Passengers(adults=1)

PRICE_HISTORY_FILE = "price_history.json"

# 每次查询之间的间隔秒数（避免请求过于密集）
QUERY_INTERVAL = 5


# ─── 价格历史 ─────────────────────────────────────────────────────────────────

def load_history() -> dict:
    if Path(PRICE_HISTORY_FILE).exists():
        with open(PRICE_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(history: dict):
    with open(PRICE_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ─── Bark 通知 ────────────────────────────────────────────────────────────────

def bark_push(title: str, body: str, url: str = ""):
    if not BARK_KEY:
        print("  ⚠️  BARK_KEY 未设置，跳过推送")
        return
    push_url = f"{BARK_URL}/{BARK_KEY}/{urllib.parse.quote(title)}/{urllib.parse.quote(body)}"
    params = {"sound": "minuet"}
    if url:
        params["url"] = url
    try:
        r = requests.get(push_url, params=params, timeout=10)
        if r.status_code == 200:
            print(f"  📲 Bark 推送成功：{title}")
        else:
            print(f"  ❌ Bark 推送失败：{r.status_code}")
    except Exception as e:
        print(f"  ❌ Bark 推送异常：{e}")


# ─── 价格查询 ─────────────────────────────────────────────────────────────────

def fetch_roundtrip(outbound: str, inbound: str) -> dict | None:
    """
    查询指定日期组合的往返最低价
    返回: {"price": int, "outbound_flight": str, "inbound_flight": str, "stops": str}
    """
    try:
        result: Result = get_flights(
            flight_data=[
                FlightData(date=outbound, from_airport=ORIGIN, to_airport=DESTINATION),
                FlightData(date=inbound,  from_airport=DESTINATION, to_airport=ORIGIN),
            ],
            trip="round-trip",
            seat="economy",
            passengers=PASSENGERS,
            fetch_mode="playwright",
        )

        if not result or not result.flights:
            return None

        # 找最低价航班
        valid = [f for f in result.flights if f.price and f.price > 0]
        if not valid:
            return None

        cheapest = min(valid, key=lambda f: f.price)

        # 提取航空公司信息
        airline = cheapest.name if hasattr(cheapest, "name") else "未知航空"
        stops_raw = cheapest.stops if hasattr(cheapest, "stops") else ""
        stops_text = "直飞" if "nonstop" in str(stops_raw).lower() or stops_raw == "0" else str(stops_raw)

        # fast-flights 返回的价格单位通常为 USD，需要转换为日元
        # 如果 current_price 字段有货币信息优先使用
        price_usd = cheapest.price

        # 尝试读取页面标注的价格趋势
        price_level = result.current_price if hasattr(result, "current_price") else ""

        return {
            "price_usd": price_usd,
            "airline": airline,
            "stops": stops_text,
            "price_level": price_level,  # "low" / "typical" / "high"
        }

    except Exception as e:
        print(f"  ❌ 查询失败 ({outbound} → {inbound})：{e}")
        return None


def usd_to_jpy(usd: float) -> int:
    """
    获取实时美元→日元汇率并换算
    汇率数据来自 exchangerate-api（免费，无需 key）
    """
    try:
        r = requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=10
        )
        rate = r.json()["rates"]["JPY"]
        return int(usd * rate)
    except Exception:
        # 汇率获取失败时用兜底值
        print("  ⚠️  汇率获取失败，使用默认值 150")
        return int(usd * 150)


# ─── 主逻辑 ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"✈️  东京 ↔ 香港 机票监控  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   目标总价：¥{TARGET_PRICE:,}")
    print("=" * 60)

    history = load_history()
    now_str = datetime.now().isoformat()

    # 获取一次汇率供本轮所有查询使用
    print("\n💱 获取美元汇率...")
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        jpy_rate = r.json()["rates"]["JPY"]
        print(f"   1 USD = {jpy_rate:.1f} JPY")
    except Exception:
        jpy_rate = 150
        print(f"   汇率获取失败，使用默认值：1 USD = {jpy_rate} JPY")

    # 生成所有日期组合
    combinations = [
        (out, inc)
        for out in OUTBOUND_DATES
        for inc in INBOUND_DATES
    ]

    results = []

    for outbound, inbound in combinations:
        combo_id = f"{outbound}_{inbound}"
        print(f"\n🔍 查询：去程 {outbound}  回程 {inbound}")

        data = fetch_roundtrip(outbound, inbound)

        if not data:
            print(f"  ⚠️  未获取到价格，跳过")
            time.sleep(QUERY_INTERVAL)
            continue

        price_jpy = int(data["price_usd"] * jpy_rate)
        level_emoji = {"low": "🟢", "typical": "🟡", "high": "🔴"}.get(
            str(data.get("price_level", "")).lower(), "⚪"
        )

        print(f"  💴 ¥{price_jpy:,}  ({data['airline']} · {data['stops']})  {level_emoji} {data.get('price_level','')}")

        # 更新历史
        combo_history = history.get(combo_id, {"records": [], "min_price_jpy": None})
        records = combo_history.get("records", [])
        records.append({"time": now_str, "price_jpy": price_jpy, "airline": data["airline"]})
        records = records[-200:]
        combo_history["records"] = records
        combo_history["last_checked"] = now_str

        old_min = combo_history.get("min_price_jpy")
        is_new_min = old_min is None or price_jpy < old_min
        if is_new_min:
            combo_history["min_price_jpy"] = price_jpy
            print(f"  🎉 此组合历史最低！")

        history[combo_id] = combo_history

        results.append({
            "outbound": outbound,
            "inbound": inbound,
            "combo_id": combo_id,
            "price_jpy": price_jpy,
            "airline": data["airline"],
            "stops": data["stops"],
            "price_level": data.get("price_level", ""),
            "is_new_min": is_new_min,
            "old_min": old_min,
        })

        time.sleep(QUERY_INTERVAL)

    # ── 分析结果，决定是否推送 ────────────────────────────────────────────────

    if not results:
        print("\n❌ 本次所有查询均失败")
        save_history(history)
        return

    # 按价格排序
    results.sort(key=lambda x: x["price_jpy"])
    cheapest = results[0]
    price = cheapest["price_jpy"]

    print(f"\n{'─'*60}")
    print(f"📊 本次最低价：¥{price:,}  ({cheapest['outbound']} 去 / {cheapest['inbound']} 回)")
    print(f"   {cheapest['airline']} · {cheapest['stops']}")
    print(f"   目标价格：¥{TARGET_PRICE:,}  差距：¥{price - TARGET_PRICE:+,}")
    print(f"{'─'*60}")

    # 推送条件：低于目标价，或刷新历史最低
    should_notify = False
    notify_reason = ""

    if price <= TARGET_PRICE:
        should_notify = True
        notify_reason = f"低于目标价 ¥{TARGET_PRICE:,}"
    elif cheapest["is_new_min"] and cheapest["old_min"] is not None:
        should_notify = True
        notify_reason = f"刷新历史最低（原¥{cheapest['old_min']:,}）"

    if should_notify:
        level_map = {"low": "价格偏低🟢", "typical": "价格正常🟡", "high": "价格偏高🔴"}
        level_text = level_map.get(cheapest["price_level"].lower(), "")

        title = f"✈️ 东京↔香港 ¥{price:,}"
        body = (
            f"{cheapest['outbound']} 去 / {cheapest['inbound']} 回\n"
            f"{cheapest['airline']} · {cheapest['stops']}\n"
            f"{notify_reason}"
            + (f" · {level_text}" if level_text else "")
        )
        search_url = (
            f"https://www.google.com/travel/flights?q=Flights+from+Tokyo+to+Hong+Kong"
        )
        bark_push(title, body, url=search_url)
    else:
        print(f"  💤 价格未达到推送条件（目标 ¥{TARGET_PRICE:,}，当前最低 ¥{price:,}）")

    # 打印所有组合汇总
    print("\n📋 所有组合价格：")
    for r in results:
        marker = "👉" if r["combo_id"] == cheapest["combo_id"] else "  "
        new_min_tag = " ★新低" if r["is_new_min"] else ""
        print(f"  {marker} {r['outbound']} 去 / {r['inbound']} 回  ¥{r['price_jpy']:,}{new_min_tag}")

    save_history(history)
    print(f"\n✅ 完成，历史已保存")


if __name__ == "__main__":
    main()
