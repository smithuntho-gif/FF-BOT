"""Post a reminder ~15 minutes before each red-folder Forex Factory event.

Runs every 5 minutes from GitHub Actions. Events already posted are saved in
sent.json so nothing is posted twice.
"""
import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
TZ = ZoneInfo("Asia/Kolkata")
NY = ZoneInfo("America/New_York")
NOW = dt.datetime.now(TZ)
LEAD_MAX = 17          # post when the event is at most this many minutes away
STATE = "sent.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/129.0 Safari/537.36"


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return []


def main():
    data = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                        headers={"User-Agent": UA}, timeout=30).json()
    sent = load_state()
    groups = {}
    for e in data:
        if e.get("impact") != "High":
            continue
        t = dt.datetime.fromisoformat(e["date"]).astimezone(TZ)
        mins = (t - NOW).total_seconds() / 60
        key = t.isoformat()
        if 0 < mins <= LEAD_MAX and key not in sent:
            groups.setdefault(key, (t, []))[1].append(e)
    if not groups:
        print("nothing due")
        return
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for key, (t, events) in sorted(groups.items()):
            mins = round((t - NOW).total_seconds() / 60)
            when = t.strftime("%-I:%M%p").lower()
            n = t.astimezone(NY)
            ny = n.strftime("%-I:%M%p").lower() + ("" if n.date() == t.date() else f" {n:%a}")
            nyz = n.strftime("%Z")
            trs = "".join(
                f"<tr><td>{when}</td><td>{ny}</td><td>{e['country']}</td>"
                f"<td><span style='display:inline-block;width:18px;height:14px;background:#d1252a'></span></td>"
                f"<td class=t>{e['title']}</td><td>{e.get('forecast','')}</td><td>{e.get('previous','')}</td></tr>"
                for e in events)
            html = f"""<html><body style='margin:0;font-family:Verdana,Arial,sans-serif;font-size:15px'>
            <div id=card style='display:inline-block'>
            <div style='background:#b42318;color:#fff;padding:10px 14px;font-weight:bold'>Red news in {mins} min &middot; {when} IST / {ny} New York ({nyz}) &middot; {t:%a %b %-d}</div>
            <table style='border-collapse:collapse;width:1100px;background:#f3f4f8'>
            <tr style='background:#7a8bb8;color:#fff'><th>IST</th><th>New York</th><th>Currency</th><th>Impact</th><th></th><th>Forecast</th><th>Previous</th></tr>
            {trs}</table></div>
            <style>td,th{{padding:10px 14px;border-bottom:1px solid #dde0e8;text-align:center}} td.t{{text-align:left}}</style>
            </body></html>"""
            page = browser.new_page(viewport={"width": 1000, "height": 200})
            page.set_content(html)
            page.query_selector("#card").screenshot(path="remind.png")
            page.close()
            payload = {"username": "forex-factory",
                       "content": f"**Red news in {mins} min** — {when} IST / {ny} New York ({nyz})"}
            with open("remind.png", "rb") as f:
                r = requests.post(WEBHOOK, data={"payload_json": json.dumps(payload)},
                                  files={"files[0]": ("red-news.png", f, "image/png")}, timeout=30)
            print(key, "discord:", r.status_code)
            if r.status_code < 300:
                sent.append(key)
        browser.close()
    sent = sent[-200:]
    with open(STATE, "w") as f:
        json.dump(sent, f, indent=0)


if __name__ == "__main__":
    main()
