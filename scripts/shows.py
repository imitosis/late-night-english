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
    for en in root.findall("a:entry", NS):
        title = (en.findtext("a:title", "", NS) or "").strip()
        if not any(m in title.lower() for m in marks):
            continue
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
with open("shows.json", "w", encoding="utf-8") as f:
    json.dump({"updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), "items": items}, f, ensure_ascii=False, indent=1)
print(f"Saved {len(items)} items.")
