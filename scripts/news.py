"""Holt jeden Morgen die Late-Night-Themen und schreibt sie nach news.json.

Läuft auf GitHub (siehe .github/workflows/news.yml). Braucht das Secret
OPENAI_API_KEY. Der Auftrag an die KI steht in index.html (NEWS_PROMPT),
damit App und dieses Skript immer dasselbe verlangen.
"""
import datetime, json, os, re, sys, urllib.request
from zoneinfo import ZoneInfo

now = datetime.datetime.now(ZoneInfo("Europe/Vienna"))
html = open("index.html", encoding="utf-8").read()
tpl = re.search(r"const NEWS_PROMPT=\(\)=>`(.*?)`;", html, re.S).group(1)
prompt = tpl.replace("${new Date().toDateString()}", now.strftime("%a %b %d %Y"))

body = {
    "model": "gpt-6-luna",
    "input": prompt,
    "reasoning": {"effort": "medium"},
    "max_output_tokens": 6000,
    "tools": [{"type": "web_search"}],
    "max_tool_calls": 6,
}
req = urllib.request.Request(
    "https://api.openai.com/v1/responses",
    data=json.dumps(body).encode(),
    headers={"content-type": "application/json", "authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
)
with urllib.request.urlopen(req, timeout=300) as r:
    res = json.load(r)

text = "".join(
    c.get("text", "")
    for o in res.get("output", []) if o.get("type") == "message"
    for c in o.get("content", []) if c.get("type") == "output_text"
)
items = []
for line in text.splitlines():
    line = line.strip()
    if not line.startswith("{"):
        continue
    try:
        it = json.loads(line)
    except json.JSONDecodeError:
        continue
    if it.get("title") and it.get("summary"):
        items.append(it)

if len(items) < 3:
    sys.exit(f"Zu wenige Storys gefunden ({len(items)}), news.json bleibt unverändert.")

json.dump({"date": now.strftime("%Y-%m-%d"), "items": items[:5]},
          open("news.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(items[:5])} Storys gespeichert.")
