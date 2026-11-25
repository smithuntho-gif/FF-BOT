"""Screenshot today's Forex Factory red-folder news + bank holidays and post it to Discord.

Times are shown in India time (Asia/Kolkata). If Forex Factory blocks the
browser, it draws the same table from Forex Factory's calendar feed instead.
"""
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
TZ = ZoneInfo("Asia/Kolkata")
NY = ZoneInfo("America/New_York")
TODAY = dt.datetime.now(TZ)
OUT = "calendar.png"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

# Hide every row that is not red (high) impact or a holiday, then return
# how many rows are left. Forex Factory marks impact with icon classes.
FILTER_JS = r"""
() => {
  const rows = [...document.querySelectorAll('tr.calendar__row')];
  let kept = 0;
  for (const r of rows) {
    if (r.classList.contains('calendar__row--day-breaker')) continue;
    const icon = r.querySelector('.calendar__impact span');
    const cls = icon ? icon.className : '';
    const keep = /impact-red|impact-gra|holiday/i.test(cls);
    if (keep) { kept++; } else { r.style.display = 'none'; }
  }
  // remove page chrome around the table
  document.querySelectorAll('header, footer, .sidebar, #flexBox_flex_minicalendar, .calendar__options')
    .forEach(e => e.style.display = 'none');
  return kept;
}
"""


# Add a "New York" column next to the time column. off = minutes NY is behind/ahead of IST.
NY_COL_JS = r"""
(off) => {
  const fmt = (m) => { let h = Math.floor(m/60), mm = m%60, ap = h>=12?'pm':'am'; h = h%12||12;
                       return h + ':' + String(mm).padStart(2,'0') + ap; };
  const head = document.querySelector('table.calendar__table thead tr, tr.calendar__header');
  const timeHead = head && head.querySelector('.calendar__time, th:nth-child(2)');
  if (timeHead) { const th = document.createElement('th'); th.textContent = 'New York';
                  th.className = timeHead.className; timeHead.after(th);
                  if (!/IST/.test(timeHead.textContent)) timeHead.textContent = 'IST'; }
  let last = '';
  for (const r of document.querySelectorAll('tr.calendar__row')) {
    const tc = r.querySelector('.calendar__time');
    if (!tc) continue;
    let txt = tc.innerText.trim();
    if (txt) last = txt; else txt = last;
    let out = txt;
    const m = /^(\d{1,2}):(\d{2})(am|pm)$/i.exec(txt);
    if (m) {
      let mins = (parseInt(m[1]) % 12 + (m[3].toLowerCase()==='pm'?12:0)) * 60 + parseInt(m[2]) + off;
      let day = '';
      if (mins < 0) { mins += 1440; day = ' (prev day)'; }
      else if (mins >= 1440) { mins -= 1440; day = ' (next day)'; }
      out = fmt(mins) + day;
    }
    const td = document.createElement('td');
    td.className = tc.className; td.textContent = (tc.innerText.trim() || r.style.display==='none') ? out : '';
    if (!tc.innerText.trim()) td.textContent = '';
    tc.after(td);
  }
}
"""


def screenshot_forexfactory(pw):
    browser = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(user_agent=UA, timezone_id="Asia/Kolkata",
                              viewport={"width": 1280, "height": 1400}, locale="en-US")
    page = ctx.new_page()
    page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    page.goto("https://www.forexfactory.com/calendar?day=today", wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("table.calendar__table", timeout=25000)
    except Exception:
        browser.close()
        return None, "blocked"
    kept = page.evaluate(FILTER_JS)
    off = int((TODAY.astimezone(NY).utcoffset() - TODAY.utcoffset()).total_seconds() // 60)
    page.evaluate(NY_COL_JS, off)
    table = page.query_selector("table.calendar__table")
    table.screenshot(path=OUT)
    browser.close()
    return kept, "forexfactory"


def draw_from_feed(pw):
    data = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                        headers={"User-Agent": UA}, timeout=30).json()
    rows = []
    for e in data:
        if e.get("impact") not in ("High", "Holiday"):
            continue
        t = dt.datetime.fromisoformat(e["date"]).astimezone(TZ)
        if t.date() != TODAY.date():
            continue
        rows.append((t, e))
    rows.sort(key=lambda x: x[0])
    trs = ""
    for t, e in rows:
        icon = "#d1252a" if e["impact"] == "High" else "#9aa0a6"
        if e["impact"] == "Holiday":
            when = ny = "All Day"
        else:
            when = t.strftime("%-I:%M%p").lower()
            n = t.astimezone(NY)
            ny = n.strftime("%-I:%M%p").lower() + ("" if n.date() == t.date() else f" {n:%a}")
        trs += (f"<tr><td>{when}</td><td>{ny}</td><td>{e['country']}</td>"
                f"<td><span style='display:inline-block;width:18px;height:14px;background:{icon}'></span></td>"
                f"<td class=t>{e['title']}</td><td></td><td>{e.get('forecast','')}</td><td>{e.get('previous','')}</td></tr>")
    if not trs:
        trs = "<tr><td colspan=8 style='text-align:center;padding:16px'>No red news or holidays today</td></tr>"
    html = f"""<html><body style='margin:0;font-family:Verdana,Arial,sans-serif;font-size:15px'>
    <div style='background:#2c3e70;color:#fff;padding:10px 14px;font-weight:bold'>{TODAY:%a %b %-d} &middot; Red news &amp; holidays &middot; IST and New York ({TODAY.astimezone(NY):%Z})</div>
    <table style='border-collapse:collapse;width:1100px;background:#f3f4f8'>
    <tr style='background:#7a8bb8;color:#fff'><th>IST</th><th>New York</th><th>Currency</th><th>Impact</th><th style='text-align:left'></th><th>Actual</th><th>Forecast</th><th>Previous</th></tr>
    {trs}</table>
    <style>td,th{{padding:10px 14px;border-bottom:1px solid #dde0e8;text-align:center}} td.t{{text-align:left}}</style>
    </body></html>"""
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1000, "height": 300})
    page.set_content(html)
    page.query_selector("body > div").evaluate("e => e.parentElement.style.display='inline-block'")
    page.query_selector("body").screenshot(path=OUT)
    browser.close()
    return len(rows), "feed"


def main():
    with sync_playwright() as pw:
        try:
            kept, source = screenshot_forexfactory(pw)
        except Exception as ex:
            print("Forex Factory screenshot failed:", ex)
            kept, source = None, "error"
        if kept is None:
            kept, source = draw_from_feed(pw)
    note = f"**Red news & holidays — {TODAY:%a %b %-d}** (times in IST and New York)"
    if kept == 0:
        note += "\nNo red news or bank holidays today."
    payload = {"username": "forex-factory", "content": note}
    with open(OUT, "rb") as f:
        r = requests.post(WEBHOOK, data={"payload_json": json.dumps(payload)},
                          files={"files[0]": ("calendar.png", f, "image/png")}, timeout=30)
    print("source:", source, "rows:", kept, "discord:", r.status_code)
    if r.status_code >= 300:
        print(r.text)
        sys.exit(1)


if __name__ == "__main__":
    main()
