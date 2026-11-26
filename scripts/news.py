"""Holt jeden Morgen die Late-Night-Themen und schreibt sie nach news.json.

Läuft auf GitHub (siehe .github/workflows/news.yml). Braucht das Secret
OPENAI_API_KEY. Der Auftrag an die KI steht in index.html (NEWS_PROMPT),
damit App und dieses Skript immer dasselbe verlangen.
"""
import datetime, json, os, re, sys, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

if not os.environ.get("OPENAI_API_KEY"):
    print("Noch kein Secret OPENAI_API_KEY eingetragen – überspringe (die App lädt die News dann selbst).")
    sys.exit(0)

now = datetime.datetime.now(ZoneInfo("Europe/Vienna"))
html = open("index.html", encoding="utf-8").read()
tpl = re.search(r"const NEWS_PROMPT=\(\)=>`(.*?)`;", html, re.S).group(1)
prompt = tpl.replace("${new Date().toDateString()}", now.strftime("%a %b %d %Y"))

body = {
    "model": "gpt-6-luna",
    "input": prompt,
    "reasoning": {"effort": "low"},
    "max_output_tokens": 32000,
    "tools": [{"type": "web_search"}],
    "max_tool_calls": 16,
}
req = urllib.request.Request(
    "https://api.openai.com/v1/responses",
    data=json.dumps(body).encode(),
    headers={"content-type": "application/json", "authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
)
def ask():
    with urllib.request.urlopen(urllib.request.Request(req.full_url, data=req.data, headers=dict(req.header_items())), timeout=300) as r:
        res = json.load(r)
    text = "".join(
        c.get("text", "")
        for o in res.get("output", []) if o.get("type") == "message"
        for c in o.get("content", []) if c.get("type") == "output_text"
    )
    print("Status:", res.get("status"), res.get("incomplete_details") or "", "| Textlänge:", len(text))
    print("Anfang:", text[:300].replace("\n", " "))
    return text

text = ask()
def clean(t):
    t = re.sub(r"\(\s*\[[^\]]*\]\([^)]*\)\s*\)", "", t or "")
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\(?https?://[^\s)]+\)?", "", t)
    return re.sub(r"\s{2,}", " ", t).strip()

def objects(t):
    out, depth, start, in_str, esc = [], 0, -1, False, False
    for i, c in enumerate(t):
        if in_str:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': in_str = False
            continue
        if c == '"': in_str = True
        elif c == "{":
            if depth == 0: start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(t[start:i + 1]); start = -1
    return out

items = []
for raw in objects(text):
    try:
        it = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if it.get("title") and it.get("summary"):
        for k in ("title", "gist", "summary", "host_open"):
            it[k] = clean(it.get(k, ""))
        items.append(it)

if len(items) < 8:
    print("Zu wenig – zweiter Versuch …")
    text = ask(); items = []
    for raw in objects(text):
        try:
            it = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if it.get("title") and it.get("summary"):
            for k in ("title", "gist", "summary", "host_open"):
                it[k] = clean(it.get(k, ""))
            items.append(it)

if len(items) < 8:
    sys.exit(f"Zu wenige Storys gefunden ({len(items)}), news.json bleibt unverändert.")

def wiki_img(title):
    if not title:
        return ""
    try:
        u = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "late-night-english/1.0"}), timeout=15) as r:
            j = json.load(r)
        t = (j.get("thumbnail") or {}).get("source", "")
        orig = (j.get("originalimage") or {}).get("source", "")
        # only real photos – no flags, logos, seals, maps or charts (those are SVG/PNG)
        if not t or not re.search(r"\.jpe?g", orig or t, re.I):
            return ""
        return t.split("?")[0]
    except Exception as e:
        print("Kein Bild für", title, e)
        return ""

# download the photos into the repo, so the app loads them from its own address (no hotlinking problems)
import shutil
shutil.rmtree("news_img", ignore_errors=True)
os.makedirs("news_img", exist_ok=True)
stamp = now.strftime("%Y%m%d")
UA_WEB = {"User-Agent": "Mozilla/5.0 (compatible; late-night-english/1.0; link preview)", "Accept-Language": "en,de;q=0.8"}

def preview_img(page):
    """The article's own preview picture (og:image), like messengers show for links."""
    if not page or not page.startswith("http"):
        return ""
    try:
        with urllib.request.urlopen(urllib.request.Request(page, headers=UA_WEB), timeout=15) as r:
            html = r.read(600000).decode("utf-8", "replace")
        for pat in (r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
            m = re.search(pat, html, re.I)
            if m:
                return urllib.parse.urljoin(page, m.group(1).replace("&amp;", "&"))
    except Exception as e:
        print("Keine Vorschau:", page, e)
    return ""

for n, it in enumerate(items[:14]):
    src = it.get("source") or {}
    url = preview_img(src.get("url", "") if isinstance(src, dict) else "")
    it["img_from"] = "article" if url else ""
    if not url:
        url = wiki_img(it.get("wiki", ""))
        it["img_from"] = "wikipedia" if url else ""
    it["img"] = ""
    if not url:
        continue
    try:
        req2 = urllib.request.Request(url, headers={"User-Agent": "late-night-english/1.0 (https://github.com/imitosis/late-night-english)"})
        with urllib.request.urlopen(req2, timeout=20) as r:
            data = r.read(3000000)
        if len(data) > 2000:
            ext = ".png" if data[:4] == b"\x89PNG" else ".webp" if data[8:12] == b"WEBP" else ".jpg"
            fn = f"news_img/{stamp}-{n}{ext}"
            open(fn, "wb").write(data)
            it["img"] = fn
    except Exception as e:
        print("Bild nicht geladen:", url, e)

json.dump({"date": now.strftime("%Y-%m-%d"), "items": items[:14]},
          open("news.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(items[:14])} Storys gespeichert.")
