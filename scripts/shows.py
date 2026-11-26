"""Find the newest late-night monologues on YouTube and save them to shows.json.

Runs as a GitHub Action. Uses the public YouTube RSS feeds, so no key is needed.
"""
import json, re, sys, urllib.request, datetime
import xml.etree.ElementTree as ET

SHOWS = [
    # name, host, YouTube handle, known channel id, words that mark the main segment
    ("Jimmy Kimmel Live!", "Jimmy Kimmel", "JimmyKimmelLive", "UCa6vGFO9ty8v5KZJXQxdhaw", ["monologue"]),
    ("The Tonight Show", "Jimmy Fallon", "FallonTonight", "UC8-Th83bH_thdKZDJCrn88g", ["monologue"]),
    ("Late Night", "Seth Meyers", "LateNightSeth", "UCVTyTA7-g9nopHeHbeuvpRA", ["a closer look", "monologue"]),
]
UA = {"User-Agent": "Mozilla/5.0 (late-night-english bot)", "Accept-Language": "en-US,en;q=0.8"}
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def feed(channel_id):
    return ET.fromstring(get("https://www.youtube.com/feeds/videos.xml?channel_id=" + channel_id))


def channel_from_handle(handle):
    html = get("https://www.youtube.com/@" + handle)
    m = re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', html)
    return m.group(1) if m else None


items = []
for name, host, handle, cid, marks in SHOWS:
    root = None
    try:
        root = feed(cid)
    except Exception as e:
        print(f"{name}: feed with stored id failed ({e}), looking up @{handle}", file=sys.stderr)
        try:
            cid2 = channel_from_handle(handle)
            if cid2:
                root = feed(cid2)
        except Exception as e2:
            print(f"{name}: lookup failed too ({e2})", file=sys.stderr)
    if root is None:
        continue
    picked = 0
    entries = []
    for en in root.findall("a:entry", NS):
        link = en.find("a:link", NS)
        if link is not None and "/shorts/" in (link.get("href") or ""):
            continue  # skip YouTube Shorts
        entries.append(en)
    print(f"{name}: newest titles:", [e.findtext("a:title", "", NS) for e in entries[:6]])
    marked = [e for e in entries if any(m in (e.findtext("a:title", "", NS) or "").lower() for m in marks)]
    def score(t):
        t = re.sub(r"\s*\|\s*(The Tonight Show|Late Night|Jimmy Kimmel Live)[^|]*$", "", t)  # the channel's own suffix
        lo = t.lower()
        sc = 3 * len(re.findall(r"\b(trump|musk|putin|xi|biden|vance|congress|president|white house|maga|election|senate|government|shutdown)\b", lo))
        sc += min(3, t.count(","))
        if re.match(r"^[A-Z][\w.'’-]+(?: [A-Z][\w.'’-]+)* (?:on|talks|reveals|thought|dives|helps|explains|shares|recalls|and)\b", t): sc -= 6  # guest interview
        if "|" in t or " – " in t or "catchphrase" in lo: sc -= 6  # music, games
        return sc
    if not marked:
        ranked = sorted(entries[:10], key=lambda e: -score(e.findtext("a:title", "", NS) or ""))
        marked = [e for e in ranked if score(e.findtext("a:title", "", NS) or "") > 2][:1]
    for en in marked:
        title = (en.findtext("a:title", "", NS) or "").strip()
        vid = en.findtext("yt:videoId", "", NS)
        desc = (en.findtext("media:group/media:description", "", NS) or "").strip()
        desc = re.sub(r"https?://\S+", "", desc)
        desc = re.split(r"\n\s*(?:SUBSCRIBE|Subscribe|Watch more|Connect with|Follow|Like Jimmy|Get more)", desc)[0].strip()[:700]
        items.append({"show": name, "host": host, "title": title, "id": vid,
                      "published": en.findtext("a:published", "", NS), "desc": desc})
        picked += 1
        if picked >= 3:
            break
    print(f"{name}: {picked} monologue(s)")

if not items:
    print("No monologues found – keeping the old file.")
    sys.exit(0)

items.sort(key=lambda x: x["published"], reverse=True)

# Prepare Jimmy's notes for each monologue in advance, so "Watch & talk" starts instantly.
# Keeps notes from the previous file for videos we already know; needs the OPENAI_API_KEY secret.
import os
old = {}
try:
    old = {i["id"]: i.get("recap") for i in json.load(open("shows.json", encoding="utf-8")).get("items", []) if i.get("recap")}
except Exception:
    pass
key = os.environ.get("OPENAI_API_KEY", "")
for it in items:
    if it["id"] in old:
        it["recap"] = old[it["id"]]
        continue
    if not key:
        continue
    prompt = (f'Find news coverage, recaps or articles about this late-night segment: "{it["title"]}" by {it["host"]} ({it["show"]}), '
              f'published on YouTube {it["published"][:10]}. YouTube description: "{it["desc"]}".\n'
              'Reply JSON only: {"topics":["3-5 short topics he joked about"],"jokes":["up to 5 jokes, paraphrased in your own words, max 20 words each"],'
              '"questions":["3 easy listening-check questions about what was said, answerable after watching once"]}. '
              'If you find nothing reliable, base it only on the title and description and keep it general.')
    body = {"model": "gpt-6-luna", "input": prompt, "reasoning": {"effort": "low"}, "max_output_tokens": 4000,
            "tools": [{"type": "web_search"}], "max_tool_calls": 3}
    try:
        req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json", "authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=180) as r:
            res = json.load(r)
        text = "".join(c.get("text", "") for o in res.get("output", []) if o.get("type") == "message"
                       for c in o.get("content", []) if c.get("type") == "output_text")
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            it["recap"] = json.loads(m.group(0))
            print("Notizen fertig:", it["host"])
    except Exception as e:
        print("Keine Notizen für", it["host"], e)
with open("shows.json", "w", encoding="utf-8") as f:
    json.dump({"updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), "items": items}, f, ensure_ascii=False, indent=1)
print(f"Saved {len(items)} items.")
