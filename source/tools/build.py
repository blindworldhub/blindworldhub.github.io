#!/usr/bin/env python3
"""
Builds the Blind World Hub website into _site/.

Where the content comes from:
- Apps and files: the Releases of this repository. Each release is one version of an app; its title is the app name
  and version, its first lines say the category, platform and links (the Add an app page writes them), and the files
  attached to it are the downloads. Every upload is shown as "Uploaded by Waqas".
- Guides and news: Markdown files in content/guides and content/news, and issues of this repository opened by the
  owner with the label "guide" or "news" (the Write an article page opens them). Closing such an issue removes it.
- Extra videos: issues by the owner with the label "video". The latest channel videos come from the YouTube feed.
- Fixed pages: content/pages.

The sources live in source/; the finished site is written to SITE_OUT (or source/_site) and the publish workflow
copies it to the top of the repository, which GitHub Pages serves.

Plain Python, no packages, so it runs anywhere. Usage: build.py [--sample sample.json] [--offline]
"""
import datetime as dt
import html
import json
import os
import re
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("SITE_OUT") or os.path.join(ROOT, "_site")
CFG = json.load(open(os.path.join(ROOT, "site.json"), encoding="utf-8"))
SITE = CFG["url"].rstrip("/")
NAME = CFG["name"]
CATS = dict(CFG["categories"])
PLATS = dict(CFG["platforms"])
ARGS = sys.argv[1:]
OFFLINE = "--offline" in ARGS
SAMPLE = ARGS[ARGS.index("--sample") + 1] if "--sample" in ARGS else None
YEAR = dt.date.today().year
ASSET_VER = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")
pages_for_sitemap = []
search_items = []
warnings = []


def esc(s):
    return html.escape(str(s or ""), quote=True)


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return s or "item"


def fmt_date(d):
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def parse_date(s):
    if not s:
        return dt.datetime(2026, 1, 1)
    s = str(s).strip().replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        d = dt.datetime.strptime(s[:10], "%Y-%m-%d")
    return d.replace(tzinfo=None)


def human_size(n):
    n = float(n or 0)
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return (f"{n:.0f} {unit}" if unit in ("bytes", "KB") else f"{n:.1f} {unit}").replace(".0 ", " ")
        n /= 1024


def plural(n, word):
    return f"{n:,} {word}" + ("" if n == 1 else "s")


# ---------------------------------------------------------------- Markdown (a small, safe subset)

def safe_url(u):
    u = u.strip()
    if re.match(r"^(https?://|mailto:|/|#)", u):
        return u
    return "#"


def inline(text):
    """Escapes text, then turns [links](url), **bold**, *italic*, `code` and bare web addresses into HTML."""
    parts = []
    pos = 0
    for m in re.finditer(r"\[([^\]]+)\]\(([^)\s]+)\)|(https?://[^\s<>()]+[^\s<>().,;:!?'\"])", text):
        parts.append(esc(text[pos:m.start()]))
        if m.group(1):
            parts.append(f'<a href="{esc(safe_url(m.group(2)))}">{inline_plain(m.group(1))}</a>')
        else:
            u = m.group(3)
            parts.append(f'<a href="{esc(u)}">{esc(u)}</a>')
        pos = m.end()
    parts.append(esc(text[pos:]))
    out = "".join(parts)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out


def inline_plain(text):
    out = esc(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    return out


def youtube_id(u):
    if not u:
        return None
    m = re.search(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/))([\w-]{11})", u)
    return m.group(1) if m else None


def markdown(md, top=2):
    """Headings start at level `top` (a page already has its h1). A YouTube link alone on a line becomes a video."""
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out, para, lst = [], [], None

    def flush():
        nonlocal para, lst
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para = []
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
            lst = None

    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            flush()
            continue
        h = re.match(r"^(#{1,6})\s+(.*)$", s)
        if h:
            flush()
            level = min(6, top + max(0, len(h.group(1)) - 2))      # "#" and "##" are the page's own parts
            out.append(f"<h{level}>{inline(h.group(2))}</h{level}>")
            continue
        vid = youtube_id(s) if re.fullmatch(r"<?https?://\S+>?", s) else None
        if vid:
            flush()
            out.append(video_embed(vid, "Video"))
            continue
        ul = re.match(r"^[-*+]\s+(.*)$", s)
        ol = re.match(r"^\d+[.)]\s+(.*)$", s)
        if ul or ol:
            if para:
                out.append("<p>" + inline(" ".join(para)) + "</p>")
                para = []
            tag = "ul" if ul else "ol"
            if lst and lst[0] != tag:
                flush()
            if not lst:
                lst = (tag, [])
            lst[1].append((ul or ol).group(1))
            continue
        if lst and raw.startswith(("  ", "\t")):
            lst[1][-1] += " " + s
            continue
        if lst:
            flush()
        para.append(s)
    flush()
    return "\n".join(out)


def plain_summary(md, n=170):
    for block in re.split(r"\n\s*\n", md or ""):
        b = block.strip()
        if not b or b.startswith("#") or re.match(r"^[-*+\d]", b) or youtube_id(b) and " " not in b:
            continue
        t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", b)
        t = re.sub(r"[*`#>]", "", t)
        t = " ".join(t.split())
        if len(t) > n:
            t = t[:n].rsplit(" ", 1)[0] + "..."
        return t
    return ""


def front_matter(text):
    meta, body = {}, text
    if "\n---" in text:
        head, body = text.split("\n---", 1)
        for line in head.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        body = body.lstrip("-").lstrip("\n")
    return meta, body


# ---------------------------------------------------------------- data from GitHub and YouTube

def gh_get(path):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    req = urllib.request.Request("https://api.github.com" + path, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "blindworldhub-site",
        **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def gh_all(path):
    items, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        batch = gh_get(f"{path}{sep}per_page=100&page={page}")
        items += batch
        if len(batch) < 100 or page >= 20:
            return items
        page += 1


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; blindworldhub-site)",
                                               "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def load_sources():
    if SAMPLE:
        data = json.load(open(SAMPLE, encoding="utf-8"))
        return data.get("releases", []), data.get("issues", []), data.get("videos", [])
    releases, issues, videos = [], [], []
    if OFFLINE:
        return releases, issues, videos
    repo = CFG["repo"]
    try:
        releases = gh_all(f"/repos/{repo}/releases")
    except Exception as e:
        warnings.append(f"releases could not be read: {e}")
    try:
        issues = [i for i in gh_all(f"/repos/{repo}/issues?state=open") if "pull_request" not in i]
    except Exception as e:
        warnings.append(f"issues could not be read: {e}")
    try:
        videos = youtube_videos()
    except Exception as e:
        warnings.append(f"YouTube videos could not be read: {e}")
        try:  # keep the videos of the last good build
            with open("videos.json", encoding="utf-8") as f:
                videos = json.load(f)
        except Exception:
            pass
    return releases, issues, videos


CHANNEL = {}


EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3]+")


def clean_title(t):
    """Video titles without emoji, which screen readers read out as words."""
    return re.sub(r"\s{2,}", " ", EMOJI.sub(" ", t or "")).strip(" -|,") or "Video"


def ago_to_date(text):
    m = re.search(r"(\d+)\s*(min|h|d|w|mo|y)", (text or "").replace("minute", "min").replace("hour", "h")
                  .replace("day", "d").replace("week", "w").replace("month", "mo").replace("year", "y"))
    now = dt.datetime.now(dt.timezone.utc)
    if not m:
        return now.isoformat()
    n, unit = int(m.group(1)), m.group(2)
    days = {"min": n / 1440, "h": n / 24, "d": n, "w": 7 * n, "mo": 30 * n, "y": 365 * n}[unit]
    return (now - dt.timedelta(days=days)).isoformat()


def channel_page_videos(cid):
    """The newest uploads, in order, from the channel's own Videos page."""
    page = fetch_text(f"https://www.youtube.com/channel/{cid}/videos")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", page, re.S)
    if not m:
        raise RuntimeError("no video data on the channel page")
    data = json.loads(m.group(1))
    title = re.search(r'<meta property="og:title" content="([^"]*)"', page)
    CHANNEL.update(id=cid, title=html.unescape(title.group(1)) if title else "")
    out = []

    def walk(o):
        if isinstance(o, dict):
            if "lockupViewModel" in o:
                v = o["lockupViewModel"]
                if v.get("contentType", "").endswith("VIDEO") and v.get("contentId"):
                    md = v.get("metadata", {}).get("lockupMetadataViewModel", {})
                    rows = md.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
                    parts = [p.get("text", {}).get("content", "") for r in rows for p in r.get("metadataParts", [])]
                    out.append({"id": v["contentId"], "title": md.get("title", {}).get("content", ""),
                                "date": ago_to_date(next((p for p in parts if "ago" in p), "")), "description": ""})
                return
            if "videoRenderer" in o:  # older page layout
                v = o["videoRenderer"]
                out.append({"id": v.get("videoId"), "title": "".join(r.get("text", "") for r in v.get("title", {}).get("runs", [])),
                            "date": ago_to_date(v.get("publishedTimeText", {}).get("simpleText", "")),
                            "description": ""})
                return
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(data)
    if not out:
        raise RuntimeError("no videos found on the channel page")
    return out


def channel_feed_videos(cid):
    """Backup: the channel's RSS feed, which YouTube sometimes answers with 404."""
    xml = fetch_text(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
          "m": "http://search.yahoo.com/mrss/"}
    root = ET.fromstring(xml)
    CHANNEL.update(id=cid, title=root.findtext("a:title", "", ns))
    out = [{"id": e.findtext("yt:videoId", "", ns), "title": e.findtext("a:title", "", ns),
            "date": e.findtext("a:published", "", ns), "description": e.findtext("m:group/m:description", "", ns) or ""}
           for e in root.findall("a:entry", ns)]
    out.sort(key=lambda v: v["date"], reverse=True)
    return out


def youtube_videos():
    cid = CFG.get("youtubeChannelId") or ""  # fixed in site.json, so only this one channel is ever used
    if not cid:
        page = fetch_text(CFG["youtube"])
        m = re.search(r'rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"', page)
        if not m:
            raise RuntimeError("channel id not found on the channel page")
        cid = m.group(1)
    errors = []
    for get in (channel_page_videos, channel_feed_videos):
        try:
            vids = get(cid)
            break
        except Exception as e:
            errors.append(f"{get.__name__}: {e}")
    else:
        raise RuntimeError(f"channel {cid}: " + "; ".join(errors))
    print(f"YouTube channel: {CHANNEL.get('title')} ({cid})")
    for v in vids:
        v["title"] = clean_title(v["title"])
    return vids[:int(CFG.get("latestVideos", 3))]


# ---------------------------------------------------------------- apps

FIELD_KEYS = {"name": "name", "app": "name", "version": "version", "category": "category", "platform": "platform",
              "summary": "summary", "short description": "summary", "video": "video", "youtube": "video",
              "play store": "playstore", "google play": "playstore", "website": "website", "developer": "developer",
              "virustotal": "virustotal", "virus scan": "virustotal", "price": "price",
              "written by": "author", "author": "author"}


def parse_release_body(body):
    fields, rest, started = {}, [], False
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        if not started:
            m = re.match(r"^\s*\**([A-Za-z ]{2,20}?)\**\s*:\s*(.*)$", line)
            if m and m.group(1).strip().lower() in FIELD_KEYS:
                fields[FIELD_KEYS[m.group(1).strip().lower()]] = m.group(2).strip()
                continue
            if not line.strip():
                continue
            started = True
        rest.append(line)
    return fields, "\n".join(rest).strip()


def match_key(value, table, default):
    v = (value or "").strip().lower()
    if not v:
        return None
    for k, label in table.items():
        if v == k or v == label.lower() or label.lower().startswith(v) or k.startswith(v):
            return k
    for k, label in table.items():
        if any(w and w in label.lower() for w in re.split(r"\W+", v) if len(w) > 3):
            return k
    return default


def platform_from_files(assets):
    ext = {".apk": "android", ".apks": "android", ".xapk": "android", ".aab": "android", ".exe": "windows",
           ".msi": "windows", ".dmg": "mac", ".pkg": "mac", ".ipa": "ios", ".deb": "linux", ".appimage": "linux",
           ".pdf": "all", ".epub": "all", ".mp3": "all", ".docx": "all", ".txt": "all"}
    for a in assets:
        e = os.path.splitext(a["name"].lower())[1]
        if e in ext:
            return ext[e]
    return None


def file_kind(name):
    e = os.path.splitext(name.lower())[1].lstrip(".")
    return {"apk": "APK file", "apks": "APKS file", "xapk": "XAPK file", "exe": "Windows installer",
            "msi": "Windows installer", "zip": "ZIP file", "pdf": "PDF document", "epub": "EPUB book",
            "mp3": "MP3 audio", "dmg": "Mac disk image", "ipa": "iPhone app"}.get(e, (e.upper() + " file") if e else "file")


def build_apps(releases):
    versions = []
    for r in releases:
        if r.get("draft"):
            continue
        fields, desc = parse_release_body(r.get("body"))
        title = (r.get("name") or r.get("tag_name") or "").strip()
        name = fields.get("name") or title
        version = fields.get("version") or ""
        if not fields.get("name"):
            m = re.match(r"^(.*?)[\s_-]+v?(\d+(?:\.\d+)+[\w.-]*|\d+)$", title)
            if m:
                name, version = m.group(1).strip(), version or m.group(2)
        assets = [a for a in r.get("assets", []) if a.get("state", "uploaded") == "uploaded"]
        plat = match_key(fields.get("platform"), PLATS, "all") or platform_from_files(assets) or "all"
        cat = match_key(fields.get("category"), CATS, "other") or (
            "documents" if plat == "all" and assets and all(file_kind(a["name"]).endswith(("document", "book"))
                                                            for a in assets) else "other")
        versions.append({
            "name": name, "version": version, "slug": slugify(name), "category": cat, "platform": plat,
            "summary": fields.get("summary") or plain_summary(desc) or f"{name} for {PLATS[plat]}.",
            "description": desc, "video": youtube_id(fields.get("video")), "playstore": fields.get("playstore", ""),
            "website": fields.get("website", ""), "developer": fields.get("developer", ""),
            "virustotal": fields.get("virustotal", ""),
            "date": parse_date(r.get("published_at") or r.get("created_at")),
            "files": [{"name": a["name"], "size": a.get("size", 0), "url": a["browser_download_url"],
                       "downloads": a.get("download_count", 0)} for a in assets],
            "tag": r.get("tag_name", ""), "prerelease": bool(r.get("prerelease")),
        })
    apps = {}
    for v in sorted(versions, key=lambda v: v["date"], reverse=True):
        a = apps.setdefault(v["slug"], {"slug": v["slug"], "versions": []})
        a["versions"].append(v)
    out = []
    for a in apps.values():
        latest = next((v for v in a["versions"] if not v["prerelease"]), a["versions"][0])
        a.update({k: latest[k] for k in ("name", "version", "category", "platform", "summary", "description",
                                         "playstore", "website", "developer", "virustotal", "files")})
        a["video"] = latest["video"] or next((v["video"] for v in a["versions"] if v["video"]), None)
        a["updated"] = latest["date"]
        a["added"] = a["versions"][-1]["date"]
        a["downloads"] = sum(f["downloads"] for v in a["versions"] for f in v["files"])
        a["url"] = f"/apps/{a['slug']}/"
        a["label"] = f"{a['name']} {a['version']}".strip()
        out.append(a)
    out.sort(key=lambda a: a["updated"], reverse=True)
    return out


# ---------------------------------------------------------------- articles and videos

def build_articles(issues):
    arts = {"guide": [], "news": []}
    for kind, folder in (("guide", "guides"), ("news", "news")):
        d = os.path.join(ROOT, "content", folder)
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not f.endswith(".md"):
                continue
            meta, body = front_matter(open(os.path.join(d, f), encoding="utf-8").read())
            arts[kind].append({"title": meta.get("title", f[:-3]), "slug": f[:-3], "body": body,
                               "description": meta.get("description") or plain_summary(body),
                               "date": parse_date(meta.get("date")), "author": (meta.get("author") or "").strip()})
    owners = {o.lower() for o in CFG.get("owners", [])}
    extra_videos = []
    for i in issues:
        if (i.get("user") or {}).get("login", "").lower() not in owners or i.get("state") != "open":
            continue
        labels = {(l["name"] if isinstance(l, dict) else l).lower() for l in i.get("labels", [])}
        body = i.get("body") or ""
        fields, rest = parse_release_body(body)
        if "video" in labels:
            vid = youtube_id(fields.get("video") or body)
            if vid:
                extra_videos.append({"id": vid, "title": i["title"], "date": i.get("created_at"),
                                     "description": fields.get("summary") or rest})
            continue
        kind = "news" if "news" in labels else "guide" if "guide" in labels else None
        if not kind:
            continue
        slug = slugify(i["title"])
        taken = {a["slug"] for a in arts[kind]}
        if slug in taken:
            slug = f"{slug}-{i['number']}"
        arts[kind].append({"title": i["title"], "slug": slug, "body": rest,
                           "description": fields.get("summary") or plain_summary(rest),
                           "date": parse_date(i.get("created_at")), "author": (fields.get("author") or "").strip()})
    for k in arts:
        arts[k].sort(key=lambda a: a["date"], reverse=True)
    return arts, extra_videos


def build_videos(feed, extra, apps):
    seen, out = set(), []
    for v in list(feed) + list(extra):
        if not v.get("id") or v["id"] in seen:
            continue
        seen.add(v["id"])
        out.append({"id": v["id"], "title": v.get("title") or "Video", "date": parse_date(v.get("date")),
                    "description": plain_summary(v.get("description") or "", 200)})
    for a in apps:
        if a["video"] and a["video"] not in seen:
            seen.add(a["video"])
            out.append({"id": a["video"], "title": f"{a['name']} review", "date": a["updated"],
                        "description": a["summary"], "app": a})
    for v in out:
        v["app"] = v.get("app") or next((a for a in apps if a["video"] == v["id"]), None)
    out.sort(key=lambda v: v["date"], reverse=True)
    return out


# ---------------------------------------------------------------- page parts

BRAILLE = {  # dots 1 to 6 of each braille letter, for the logo and the app marks
    "a": "1", "b": "12", "c": "14", "d": "145", "e": "15", "f": "124", "g": "1245", "h": "125", "i": "24",
    "j": "245", "k": "13", "l": "123", "m": "134", "n": "1345", "o": "135", "p": "1234", "q": "12345",
    "r": "1235", "s": "234", "t": "2345", "u": "136", "v": "1236", "w": "2456", "x": "1346", "y": "13456",
    "z": "1356"}
DOT_POS = {"1": (0, 0), "2": (0, 1), "3": (0, 2), "4": (1, 0), "5": (1, 1), "6": (1, 2)}


def braille_svg(word, cls="braille", r=2.6, gap=8, cell=21):
    dots = []
    for n, ch in enumerate(word.lower()):
        raised = BRAILLE.get(ch, "")
        for d, (cx, cy) in DOT_POS.items():
            x = 4 + n * cell + cx * gap
            y = 4 + cy * gap
            on = d in raised
            dots.append(f'<circle cx="{x}" cy="{y}" r="{r if on else r * 0.55:.2f}" class="{"on" if on else "off"}"/>')
    w = 8 + (len(word) - 1) * cell + gap
    return (f'<svg class="{cls}" viewBox="0 0 {w} 24" width="{w}" height="24" aria-hidden="true" focusable="false">'
            + "".join(dots) + "</svg>")


def app_mark(name):
    letter = next((c for c in name.lower() if c in BRAILLE), "a")
    return f'<span class="app-mark" aria-hidden="true">{braille_svg(letter, "mark-dots", 3.4, 10, 0)}</span>'


NAV = [("/", "Home"), ("/apps/", "Apps"), ("/videos/", "Videos"), ("/guides/", "Guides"), ("/news/", "News"),
       ("/about/", "About"), ("/contact/", "Contact")]


def header(current):
    items = []
    for href, label in NAV:
        cur = ' aria-current="page"' if current == href else ""
        items.append(f'<li><a href="{href}"{cur}>{label}</a></li>')
    return f"""<a class="skip" href="#main">Skip to main content</a>
<header class="masthead">
  <div class="wrap bar">
    <a class="brand" href="/">{braille_svg("bwh", "brand-dots")}<span class="brand-name">{esc(NAME)}</span></a>
    <div class="bar-tools">
      <button type="button" class="tool-btn menu-btn" aria-expanded="false" aria-controls="site-nav">Menu</button>
      <button type="button" class="tool-btn settings-btn" aria-expanded="false" aria-controls="display-settings">Display settings</button>
    </div>
    <nav id="site-nav" class="site-nav" aria-label="Main">
      <ul>{''.join(items)}</ul>
    </nav>
    <form class="site-search" role="search" action="/search/" method="get">
      <label for="site-q" class="vh">Search apps, guides and videos</label>
      <input id="site-q" name="q" type="search" placeholder="Search apps and guides" autocomplete="off">
      <button type="submit">Search</button>
    </form>
  </div>
  <div id="display-settings" class="settings" hidden>
    <div class="wrap settings-inner" role="group" aria-labelledby="settings-title">
      <h2 id="settings-title" class="settings-title">Display settings</h2>
      <div class="settings-row">
        <span class="settings-label" id="ts-label">Text size</span>
        <button type="button" data-text="-1">Smaller text</button>
        <button type="button" data-text="0">Normal text</button>
        <button type="button" data-text="1">Larger text</button>
      </div>
      <div class="settings-row">
        <button type="button" data-toggle="contrast" aria-pressed="false">High contrast</button>
        <button type="button" data-toggle="theme" aria-pressed="false">Dark theme</button>
        <button type="button" data-toggle="motion" aria-pressed="true">3D effects</button>
      </div>
      <p class="settings-status" role="status" aria-live="polite"></p>
    </div>
  </div>
</header>"""


def footer():
    return f"""<footer class="site-foot">
  <div class="wrap foot-grid">
    <div class="foot-brand">
      <p class="foot-name">{braille_svg("bwh", "brand-dots")}<span>{esc(NAME)}</span></p>
      <p>{esc(CFG['tagline'])} Run by {esc(CFG['uploader'])}.</p>
    </div>
    <nav aria-label="Explore"><h2>Explore</h2><ul>
      <li><a href="/apps/">Apps</a></li><li><a href="/videos/">Videos</a></li>
      <li><a href="/guides/">Guides</a></li><li><a href="/news/">News</a></li></ul></nav>
    <nav aria-label="About the site"><h2>About</h2><ul>
      <li><a href="/about/">About Blind World Hub</a></li><li><a href="/contact/">Contact</a></li>
      <li><a href="/accessibility/">Accessibility statement</a></li></ul></nav>
    <nav aria-label="Policies"><h2>Policies</h2><ul>
      <li><a href="/privacy/">Privacy policy</a></li><li><a href="/terms/">Terms of use</a></li>
      <li><a href="/disclaimer/">Disclaimer and copyright</a></li></ul></nav>
    <div class="foot-community"><h2>Community</h2><ul>
      <li><a href="{esc(CFG['whatsapp'])}" rel="noopener">Join the WhatsApp community</a></li>
      <li><a href="{esc(CFG['youtube'])}" rel="noopener">Subscribe on YouTube</a></li></ul></div>
  </div>
  <p class="wrap copyright">Copyright {YEAR} {esc(NAME)}. Apps belong to their developers.</p>
</footer>"""


PREFS_JS = ("(function(){var d=document.documentElement;d.className+=' js';try{var s=localStorage,t=s.getItem('bwh-text');"
            "if(t)d.style.setProperty('--scale',t);if(s.getItem('bwh-contrast')==='1')d.setAttribute('data-contrast','high');"
            "var th=s.getItem('bwh-theme');if(th)d.setAttribute('data-theme',th);if(s.getItem('bwh-motion')==='0')"
            "d.setAttribute('data-motion','off');}catch(e){}})();")


def page(path, title, description, body, current=None, jsonld=None, noindex=False, extra_head="", scripts="",
         full_title=None, og_type="website", sitemap=True, priority="0.6"):
    url = SITE + path
    t = full_title or f"{title} | {NAME}"
    lds = "".join(f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>'
                  for j in (jsonld or []))
    verify = (f'<meta name="google-site-verification" content="{esc(CFG["googleSiteVerification"])}">'
              if CFG.get("googleSiteVerification") else "")
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(t)}</title>
<meta name="description" content="{esc(description)}">
{'<meta name="robots" content="noindex, nofollow">' if noindex else '<meta name="robots" content="index, follow, max-image-preview:large">'}
<link rel="canonical" href="{esc(url)}">
<meta name="theme-color" content="#0f2340">
<meta property="og:site_name" content="{esc(NAME)}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(t)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{SITE}/assets/img/og.jpg">
<meta property="og:image:alt" content="Blind World Hub: a globe made of raised yellow dots on dark blue.">
<meta name="twitter:card" content="summary_large_image">
{verify}
<link rel="icon" href="/assets/img/icon.svg" type="image/svg+xml">
<link rel="icon" href="/assets/img/icon-192.png" sizes="192x192" type="image/png">
<link rel="apple-touch-icon" href="/assets/img/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="preload" href="/assets/fonts/AtkinsonHyperlegible-Regular.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/AtkinsonHyperlegible-Bold.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/css/site.css?v={ASSET_VER}">
<script>{PREFS_JS}</script>
{extra_head}{lds}
</head>
<body>
{header(current)}
<main id="main" tabindex="-1">
{body}
</main>
{footer()}
<script src="/assets/js/site.js?v={ASSET_VER}" defer></script>
{scripts}
</body>
</html>
"""
    write(path, doc)
    if sitemap and not noindex:
        pages_for_sitemap.append((path, priority))


def write(path, content):
    p = os.path.join(OUT, path.lstrip("/"))
    if path.endswith("/"):
        p = os.path.join(p, "index.html")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def crumbs(items):
    """items: [(href or None, label)]. Visible breadcrumb plus its structured data."""
    li = []
    for href, label in items:
        li.append(f'<li><a href="{href}">{esc(label)}</a></li>' if href else f'<li aria-current="page">{esc(label)}</li>')
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": n + 1, "name": label, **({"item": SITE + href} if href else {})}
        for n, (href, label) in enumerate(items)]}
    return f'<nav class="crumbs" aria-label="Breadcrumb"><ol>{"".join(li)}</ol></nav>', ld


def meta_line(a):
    parts = [f'{esc(PLATS[a["platform"]])}, {esc(CATS[a["category"]])}.',
             f'Uploaded by <a href="/about/">{esc(CFG["uploader"])}</a> on <time datetime="{a["updated"]:%Y-%m-%d}">{fmt_date(a["updated"])}</time>.']
    if a["downloads"]:
        parts.append(f'{plural(a["downloads"], "download")}.')
    return " ".join(parts)


def app_row(a, level=3):
    search_text = " ".join([a["name"], a["summary"], CATS[a["category"]], PLATS[a["platform"]]]).lower()
    return f"""<li class="app-row" data-cat="{a['category']}" data-plat="{a['platform']}" data-text="{esc(search_text)}">
  {app_mark(a['name'])}
  <div class="app-row-body">
    <h{level} class="app-row-title"><a href="{a['url']}">{esc(a['label'])}</a></h{level}>
    <p class="app-row-sum">{esc(a['summary'])}</p>
    <p class="meta">{meta_line(a)}</p>
  </div>
</li>"""


def video_embed(vid, title):
    t = esc(title)
    return f"""<div class="yt" data-id="{esc(vid)}" data-title="{t}">
  <img src="https://i.ytimg.com/vi/{esc(vid)}/hqdefault.jpg" alt="" loading="lazy" decoding="async" width="480" height="360">
  <button type="button" class="yt-play"><span class="yt-icon" aria-hidden="true"></span><span>Play video: {t}</span></button>
</div>"""


def video_item(v, level=3):
    app_link = (f' <a href="{v["app"]["url"]}">Open the {esc(v["app"]["name"])} page</a>.' if v.get("app") else "")
    return f"""<li class="video-item">
  {video_embed(v['id'], v['title'])}
  <h{level} class="video-title"><a href="https://www.youtube.com/watch?v={esc(v['id'])}" rel="noopener">{esc(v['title'])}</a></h{level}>
  <p class="meta"><time datetime="{v['date']:%Y-%m-%d}">{fmt_date(v['date'])}</time>.{app_link}</p>
</li>"""


def is_owner_name(name):
    return not name or name.strip().lower() == CFG["uploader"].strip().lower()


def byline_text(a):
    au = a.get("author")
    return f"by {CFG['uploader']}" if is_owner_name(au) else f"by {au}, shared by {CFG['uploader']}"


def byline_html(a):
    me = f'<a href="/about/">{esc(CFG["uploader"])}</a>'
    au = a.get("author")
    return f"By {me}" if is_owner_name(au) else f"Written by {esc(au)}, shared by {me}"


def article_row(a, kind, level=3):
    folder = "guides" if kind == "guide" else "news"
    return f"""<li class="article-row">
  <h{level}><a href="/{folder}/{a['slug']}/">{esc(a['title'])}</a></h{level}>
  <p>{esc(a['description'])}</p>
  <p class="meta"><time datetime="{a['date']:%Y-%m-%d}">{fmt_date(a['date'])}</time>, {byline_text(a)}.</p>
</li>"""


def empty_note(text, link=None):
    return f'<p class="empty">{text}{(" " + link) if link else ""}</p>'


# ---------------------------------------------------------------- pages

def home(apps, videos, arts):
    recent = apps[:6]
    popular = sorted([a for a in apps if a["downloads"] > 0], key=lambda a: a["downloads"], reverse=True)[:5]
    hero = f"""<section class="hero" aria-labelledby="hero-title">
  <div class="wrap hero-grid">
    <div class="hero-copy">
      <h1 id="hero-title" class="hero-title">Blind World Hub</h1>
      <p class="hero-braille">{braille_svg("blind", "hero-dots", 3.2, 10, 26)}{braille_svg("world", "hero-dots", 3.2, 10, 26)}{braille_svg("hub", "hero-dots", 3.2, 10, 26)}</p>
      <p class="lede">Accessible apps, guides and video reviews for blind and visually impaired people, shared by {esc(CFG['uploader'])}, a blind creator who reviews apps with a screen reader.</p>
      <form class="hero-search" role="search" action="/search/" method="get">
        <label for="hero-q">Find an app or a guide</label>
        <div class="hero-search-row"><input id="hero-q" name="q" type="search" placeholder="For example: voice, reader, WhatsApp" autocomplete="off"><button type="submit">Search</button></div>
      </form>
      <p class="hero-actions"><a class="btn btn-primary" href="/apps/">Browse apps</a><a class="btn btn-ghost" href="/videos/">Watch videos</a></p>
    </div>
    <div class="hero-globe" aria-hidden="true"><canvas id="globe" width="600" height="600"></canvas></div>
  </div>
</section>"""
    parts = [hero]
    parts.append(f"""<section class="band" aria-labelledby="new-apps">
  <div class="wrap">
    <div class="band-head"><h2 id="new-apps">New apps</h2><a class="more" href="/apps/">See all apps</a></div>
    {('<ul class="app-list">' + ''.join(app_row(a) for a in recent) + '</ul>') if recent else empty_note("The first apps are on their way. To hear as soon as they arrive,", '<a href="' + esc(CFG["whatsapp"]) + '">join the WhatsApp community</a>.')}
  </div>
</section>""")
    if popular:
        parts.append(f"""<section class="band band-alt" aria-labelledby="popular">
  <div class="wrap">
    <div class="band-head"><h2 id="popular">Most downloaded</h2></div>
    <ol class="rank-list">{''.join(f'<li><a href="{a["url"]}">{esc(a["label"])}</a> <span class="meta">{plural(a["downloads"], "download")}</span></li>' for a in popular)}</ol>
  </div>
</section>""")
    vids = videos[:int(CFG.get("latestVideos", 3))]
    parts.append(f"""<section class="band" aria-labelledby="latest-videos">
  <div class="wrap">
    <div class="band-head"><h2 id="latest-videos">Latest videos</h2><a class="more" href="/videos/">All videos</a></div>
    {('<ul class="video-grid">' + ''.join(video_item(v) for v in vids) + '</ul>') if vids else empty_note('New video reviews appear here. Meanwhile, visit the', f'<a href="{esc(CFG["youtube"])}">Blind World Hub YouTube channel</a>.')}
  </div>
</section>""")
    parts.append(f"""<section class="band band-alt" aria-labelledby="learn">
  <div class="wrap two-col">
    <div><div class="band-head"><h2 id="learn">Guides</h2><a class="more" href="/guides/">All guides</a></div>
      {('<ul class="article-list">' + ''.join(article_row(a, 'guide') for a in arts['guide'][:3]) + '</ul>') if arts['guide'] else empty_note('New guides are on their way.')}</div>
    <div><div class="band-head"><h2 id="news-h">News</h2><a class="more" href="/news/">All news</a></div>
      {('<ul class="article-list">' + ''.join(article_row(a, 'news') for a in arts['news'][:3]) + '</ul>') if arts['news'] else empty_note('News is on its way.')}</div>
  </div>
</section>""")
    parts.append(community_band())
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": NAME, "url": SITE + "/",
           "description": CFG["description"], "potentialAction": {
               "@type": "SearchAction", "target": SITE + "/search/?q={search_term_string}",
               "query-input": "required name=search_term_string"}},
          {"@context": "https://schema.org", "@type": "Organization", "name": NAME, "url": SITE + "/",
           "logo": SITE + "/assets/img/icon-512.png", "sameAs": [CFG["youtube"]],
           "founder": {"@type": "Person", "name": CFG["uploader"]}}]
    page("/", NAME, CFG["description"], "\n".join(parts), current="/", jsonld=ld,
         full_title=f"{NAME}: accessible apps, guides and videos for blind people",
         extra_head=f'<meta name="keywords" content="{esc(CFG["keywords"])}">',
         scripts=f'<script src="/assets/js/globe.js?v={ASSET_VER}" defer></script>', priority="1.0")


def community_band():
    return f"""<section class="community" aria-labelledby="community-title">
  <div class="wrap community-inner">
    <div>
      <h2 id="community-title">Join the community</h2>
      <p>Ask questions, suggest apps and hear about new uploads first.</p>
    </div>
    <p class="community-actions">
      <a class="btn btn-dark" href="{esc(CFG['whatsapp'])}" rel="noopener">Join the WhatsApp community</a>
      <a class="btn btn-dark-ghost" href="{esc(CFG['youtube'])}" rel="noopener">Subscribe on YouTube</a>
    </p>
  </div>
</section>"""


def page_head(h1, intro, crumb_html=""):
    return f"""<div class="page-head"><div class="wrap">{crumb_html}<h1>{esc(h1)}</h1>{f'<p class="lede">{intro}</p>' if intro else ''}</div></div>"""


def apps_index(apps):
    used_c = [k for k in CATS if any(a["category"] == k for a in apps)]
    used_p = [k for k in PLATS if any(a["platform"] == k for a in apps)]
    filters = f"""<form class="filters" id="app-filters" aria-labelledby="filter-title" onsubmit="return false">
  <h2 id="filter-title" class="vh">Filter the apps</h2>
  <div class="field"><label for="f-text">Name or word</label><input id="f-text" type="search" autocomplete="off"></div>
  <div class="field"><label for="f-cat">Category</label><select id="f-cat"><option value="">All categories</option>{''.join(f'<option value="{k}">{esc(CATS[k])}</option>' for k in used_c)}</select></div>
  <div class="field"><label for="f-plat">Platform</label><select id="f-plat"><option value="">All platforms</option>{''.join(f'<option value="{k}">{esc(PLATS[k])}</option>' for k in used_p)}</select></div>
</form>
<p class="count" id="app-count" role="status" aria-live="polite">{plural(len(apps), "app")}.</p>"""
    cat_links = "".join(f'<li><a href="/apps/category/{k}/">{esc(CATS[k])}</a></li>' for k in used_c)
    plat_links = "".join(f'<li><a href="/apps/platform/{k}/">{esc(PLATS[k])}</a></li>' for k in used_p)
    body = page_head("Apps and downloads", "Every app has its own page with the version, a description and a download button. Newest first.")
    body += f"""<div class="wrap page-body">
{filters if apps else ''}
{('<ul class="app-list" id="app-list">' + ''.join(app_row(a, 2) for a in apps) + '</ul>') if apps else empty_note("No apps have been added yet. New apps appear here as soon as they are uploaded.")}
{f'<section aria-labelledby="by-cat" class="browse"><h2 id="by-cat">Browse by category</h2><ul class="chips">{cat_links}</ul><h2>Browse by platform</h2><ul class="chips">{plat_links}</ul></section>' if apps else ''}
</div>"""
    page("/apps/", "Apps and downloads", f"Accessible apps for blind and visually impaired people: {', '.join(CATS[k] for k in used_c[:5]) or 'screen readers, voices and tools'}. Free downloads with descriptions and video reviews.",
         body, current="/apps/", priority="0.9")
    for key, table, folder in (("category", CATS, "category"), ("platform", PLATS, "platform")):
        for k in (used_c if key == "category" else used_p):
            subset = [a for a in apps if a[key] == k]
            label = table[k]
            title = f"{label} apps" if key == "category" else f"Apps for {label}"
            cr, ld = crumbs([("/", "Home"), ("/apps/", "Apps"), (None, title)])
            b = page_head(title, f"{plural(len(subset), 'app')}, newest first.", cr)
            b += f'<div class="wrap page-body"><ul class="app-list">{"".join(app_row(a, 2) for a in subset)}</ul><p><a href="/apps/">See all apps</a></p></div>'
            page(f"/apps/{folder}/{k}/", title, f"{title} for blind and visually impaired people, with free downloads and reviews on {NAME}.",
                 b, current="/apps/", jsonld=[ld], priority="0.7")


def app_page(a, apps):
    cr, ld_c = crumbs([("/", "Home"), ("/apps/", "Apps"), (None, a["name"])])
    dl = []
    for f in a["files"]:
        kind = file_kind(f["name"])
        dl.append(f"""<li><a class="btn btn-primary btn-download" href="{esc(f['url'])}">Download {esc(a['label'])}, {kind}, {human_size(f['size'])}</a>
  <span class="meta">{esc(f['name'])}{f', downloaded {plural(f["downloads"], "time")}' if f['downloads'] else ''}</span></li>""")
    if a["playstore"]:
        dl.append(f'<li><a class="btn btn-primary" href="{esc(safe_url(a["playstore"]))}" rel="noopener">Get {esc(a["name"])} on Google Play</a></li>')
    if a["website"]:
        dl.append(f'<li><a class="btn btn-ghost-dark" href="{esc(safe_url(a["website"]))}" rel="noopener">Visit the {esc(a["name"])} website</a></li>')
    if a["virustotal"]:
        dl.append(f'<li><a href="{esc(safe_url(a["virustotal"]))}" rel="noopener">Virus scan report on VirusTotal</a></li>')
    install = ""
    if a["platform"] == "android" and a["files"]:
        install = ''
    older = [v for v in a["versions"] if v["version"] != a["version"] or v["files"] != a["files"]][:20] if len(a["versions"]) > 1 else []
    older_html = ""
    if older:
        rows = []
        for v in older:
            links = ", ".join(f'<a href="{esc(f["url"])}">Download {esc(v["version"] or v["tag"])}, {file_kind(f["name"])}, {human_size(f["size"])}</a>' for f in v["files"]) or "No file"
            rows.append(f'<li>Version {esc(v["version"] or v["tag"])}, uploaded on <time datetime="{v["date"]:%Y-%m-%d}">{fmt_date(v["date"])}</time>: {links}</li>')
        older_html = f'<section aria-labelledby="older"><h2 id="older">Older versions</h2><ul class="plain-list">{"".join(rows)}</ul></section>'
    related = [x for x in apps if x["slug"] != a["slug"] and x["category"] == a["category"]][:4]
    related += [x for x in apps if x["slug"] != a["slug"] and x not in related][:4 - len(related)]
    desc_html = markdown(a["description"], top=3) if a["description"] else f"<p>{esc(a['summary'])}</p>"
    body = f"""<article class="app-page">
<div class="page-head"><div class="wrap">{cr}
  <div class="app-head">{app_mark(a['name'])}<div>
    <h1>{esc(a['name'])}</h1>
    <p class="app-version">{('Version ' + esc(a['version'])) if a['version'] else ''}</p>
    <p class="meta">Uploaded by <a href="/about/">{esc(CFG['uploader'])}</a> on <time datetime="{a['updated']:%Y-%m-%d}">{fmt_date(a['updated'])}</time>.{' Developer: ' + esc(a['developer']) + '.' if a['developer'] else ''}</p>
    <ul class="chips"><li><a href="/apps/platform/{a['platform']}/">{esc(PLATS[a['platform']])}</a></li><li><a href="/apps/category/{a['category']}/">{esc(CATS[a['category']])}</a></li></ul>
  </div></div>
  <p class="lede">{esc(a['summary'])}</p>
</div></div>
<div class="wrap page-body app-body">
  <section aria-labelledby="download" class="download-box">
    <h2 id="download">Download</h2>
    {('<ul class="download-list">' + ''.join(dl) + '</ul>') if dl else '<p>No download for this app yet.</p>'}
    {install}
  </section>
  {f'<section aria-labelledby="video"><h2 id="video">Video review</h2>{video_embed(a["video"], a["name"] + " review")}</section>' if a['video'] else ''}
  <section aria-labelledby="about-app" class="prose"><h2 id="about-app">About this app</h2>{desc_html}</section>
  {older_html}
  <p class="disclaimer">This app is shared as it is, for personal use. It belongs to its developer. Read the <a href="/disclaimer/">disclaimer</a>.</p>
  {f'<section aria-labelledby="more-apps"><h2 id="more-apps">More apps</h2><ul class="app-list">{"".join(app_row(x, 3) for x in related)}</ul></section>' if related else ''}
</div>
</article>"""
    sw = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": a["name"],
          "softwareVersion": a["version"] or None, "operatingSystem": PLATS[a["platform"]],
          "applicationCategory": "AccessibilityApplication" if a["category"] in ("screen-readers", "voices", "reading") else "UtilitiesApplication",
          "description": a["summary"], "datePublished": a["added"].strftime("%Y-%m-%d"),
          "dateModified": a["updated"].strftime("%Y-%m-%d"), "url": SITE + a["url"],
          "isAccessibleForFree": True, "publisher": {"@type": "Organization", "name": NAME}}
    if a["files"]:
        sw["downloadUrl"] = a["files"][0]["url"]
        sw["fileSize"] = human_size(a["files"][0]["size"])
        sw["offers"] = {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    if a["developer"]:
        sw["author"] = {"@type": "Organization", "name": a["developer"]}
    sw = {k: v for k, v in sw.items() if v is not None}
    title = f"{a['label']} for {PLATS[a['platform']]}: download"
    page(a["url"], title, f"Download {a['label']} for {PLATS[a['platform']]}. {a['summary']}"[:300], body,
         current="/apps/", jsonld=[sw, ld_c], og_type="article", priority="0.8")
    search_items.append({"t": a["label"], "u": a["url"], "d": a["summary"], "k": "App",
                         "x": f"{CATS[a['category']]} {PLATS[a['platform']]}"})


def videos_page(videos):
    body = page_head("Videos", f'Video reviews of apps from the Play Store and beyond, tested with a screen reader. <a href="{esc(CFG["youtube"])}" rel="noopener">Subscribe to the YouTube channel</a> to get every new video.')
    if videos:
        inner = '<ul class="video-grid">' + "".join(video_item(v, 2) for v in videos) + "</ul>"
    else:
        inner = empty_note("Videos appear here as soon as they are published on the",
                           '<a href="' + esc(CFG["youtube"]) + '">YouTube channel</a>.')
    body += '<div class="wrap page-body">' + inner + "</div>"
    if CHANNEL:
        body += f"<!-- channel: {esc(CHANNEL['title'])} {CHANNEL['id']} -->"
    for w in warnings:
        body += f"<!-- {esc(w)} -->"
    ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": n + 1, "url": f"https://www.youtube.com/watch?v={v['id']}", "name": v["title"]}
        for n, v in enumerate(videos[:30])]}
    page("/videos/", "Videos", "Video reviews of accessible apps for blind and visually impaired people, from the Blind World Hub YouTube channel.",
         body, current="/videos/", jsonld=[ld] if videos else None, priority="0.8")
    for v in videos:
        search_items.append({"t": v["title"], "u": "/videos/", "d": v["description"][:140], "k": "Video", "x": ""})


def articles_pages(arts):
    for kind, folder, label, intro in (("guide", "guides", "Guides", "Step by step help for using apps and your phone with a screen reader."),
                                       ("news", "news", "News", "News from Blind World Hub and the world of accessibility.")):
        items = arts[kind]
        body = page_head(label, intro)
        inner = ('<ul class="article-list">' + "".join(article_row(a, kind, 2) for a in items) + "</ul>"
                 if items else empty_note("Nothing here yet."))
        body += '<div class="wrap page-body">' + inner + "</div>"
        page(f"/{folder}/", label, f"{label} from {NAME}: {intro}", body, current=f"/{folder}/", priority="0.8")
        for a in items:
            cr, ld_c = crumbs([("/", "Home"), (f"/{folder}/", label), (None, a["title"])])
            body = f"""<article>
<div class="page-head"><div class="wrap">{cr}<h1>{esc(a['title'])}</h1>
<p class="meta">{byline_html(a)}, <time datetime="{a['date']:%Y-%m-%d}">{fmt_date(a['date'])}</time>.</p></div></div>
<div class="wrap page-body prose">{markdown(a['body'])}
<p class="back"><a href="/{folder}/">All {label.lower()}</a></p></div>
</article>"""
            ld = {"@context": "https://schema.org", "@type": "Article" if kind == "guide" else "NewsArticle",
                  "headline": a["title"], "description": a["description"], "datePublished": a["date"].strftime("%Y-%m-%d"),
                  "author": ({"@type": "Person", "name": a["author"]} if a.get("author") else
                             {"@type": "Person", "name": CFG["uploader"], "url": SITE + "/about/"}),
                  "publisher": {"@type": "Organization", "name": NAME, "logo": {"@type": "ImageObject", "url": SITE + "/assets/img/icon-512.png"}},
                  "mainEntityOfPage": SITE + f"/{folder}/{a['slug']}/"}
            page(f"/{folder}/{a['slug']}/", a["title"], a["description"], body, current=f"/{folder}/",
                 jsonld=[ld, ld_c], og_type="article", priority="0.7")
            search_items.append({"t": a["title"], "u": f"/{folder}/{a['slug']}/", "d": a["description"],
                                 "k": "Guide" if kind == "guide" else "News", "x": ""})


def static_pages():
    d = os.path.join(ROOT, "content", "pages")
    for f in sorted(os.listdir(d)):
        if not f.endswith(".md"):
            continue
        meta, md = front_matter(open(os.path.join(d, f), encoding="utf-8").read())
        slug = f[:-3]
        title = meta.get("title", slug.title())
        body = page_head(title, "") + f'<div class="wrap page-body prose">{markdown(md)}</div>'
        if slug in ("about", "contact"):
            body += community_band()
        page(f"/{slug}/", title, meta.get("description", ""), body,
             current=f"/{slug}/" if slug in ("about", "contact") else None, priority="0.5")
        search_items.append({"t": title, "u": f"/{slug}/", "d": meta.get("description", ""), "k": "Page", "x": ""})


def search_page():
    body = page_head("Search", "")
    body += """<div class="wrap page-body">
<form class="search-big" role="search" action="/search/" method="get">
  <label for="search-q">Search apps, guides, news and videos</label>
  <div class="hero-search-row"><input id="search-q" name="q" type="search" autocomplete="off"><button type="submit">Search</button></div>
</form>
<p id="search-status" class="count" role="status" aria-live="polite"></p>
<ol id="search-results" class="search-results"></ol>
<noscript><p>Search needs JavaScript. You can browse all <a href="/apps/">apps</a>, <a href="/guides/">guides</a> and <a href="/videos/">videos</a> instead.</p></noscript>
</div>"""
    page("/search/", "Search", f"Search {NAME} for apps, guides, news and videos.", body, sitemap=False)


def owner_pages():
    """Helper forms for the owner. They open GitHub with everything filled in; only the owner can publish there."""
    repo = CFG["repo"]
    cat_opts = "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for _, v in CFG["categories"])
    plat_opts = "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for _, v in CFG["platforms"])
    admin = page_head("Owner tools", "For Waqas. These pages fill in GitHub for you; only you can publish there.")
    admin += f"""<div class="wrap page-body prose">
<ul class="tool-list">
  <li><a class="btn btn-primary" href="/add-app/">Add an app or file</a> Upload an APK, a PDF or any file, or add a Play Store app with its video.</li>
  <li><a class="btn btn-primary" href="/write/">Write a guide or news</a> Publish an article.</li>
  <li><a class="btn btn-primary" href="/add-video/">Add a video</a> Show an older YouTube video on the Videos page. New channel videos appear by themselves.</li>
  <li><a class="btn btn-ghost-dark" href="https://github.com/{repo}/releases">Change or delete apps on GitHub</a></li>
  <li><a class="btn btn-ghost-dark" href="https://github.com/{repo}/issues">Change or delete articles and videos on GitHub</a></li>
</ul>
</div>"""
    page("/admin/", "Owner tools", "Owner tools.", admin, noindex=True, sitemap=False)

    add = page_head("Add an app or file", "Fill in what you know; only the name is needed. Then press Continue to GitHub, attach the file there and press Publish release.")
    add += f"""<div class="wrap page-body">
<form id="add-app" class="owner-form" data-repo="{esc(repo)}" novalidate>
  <div class="field"><label for="a-name">App or file name (needed)</label><input id="a-name" name="name" required autocomplete="off"></div>
  <div class="field"><label for="a-version">Version, for example 2.1</label><input id="a-version" name="version" autocomplete="off"></div>
  <div class="field"><label for="a-cat">Category</label><select id="a-cat" name="category">{cat_opts}</select></div>
  <div class="field"><label for="a-plat">Platform</label><select id="a-plat" name="platform">{plat_opts}</select></div>
  <div class="field"><label for="a-sum">Short description, one sentence</label><input id="a-sum" name="summary" autocomplete="off"></div>
  <div class="field"><label for="a-desc">Full description and features</label><textarea id="a-desc" name="description" rows="6"></textarea></div>
  <div class="field"><label for="a-video">YouTube video link (optional)</label><input id="a-video" name="video" type="url" inputmode="url" autocomplete="off"></div>
  <div class="field"><label for="a-play">Play Store link (optional)</label><input id="a-play" name="playstore" type="url" inputmode="url" autocomplete="off"></div>
  <div class="field"><label for="a-web">Developer website (optional)</label><input id="a-web" name="website" type="url" inputmode="url" autocomplete="off"></div>
  <div class="field"><label for="a-vt">VirusTotal report link (optional)</label><input id="a-vt" name="virustotal" type="url" inputmode="url" autocomplete="off"></div>
  <p class="form-error" id="add-app-error" role="alert"></p>
  <button type="submit" class="btn btn-primary">Continue to GitHub</button>
</form>
<section class="prose" aria-labelledby="next-steps"><h2 id="next-steps">On the GitHub page</h2>
<ol><li>Everything you typed is already filled in. Do not change the tag.</li>
<li>Find the button "Attach binaries by dropping them here or selecting them" and choose the APK or other file. Skip this for a Play Store app without a file.</li>
<li>Wait until the file has finished uploading, then press "Publish release".</li>
<li>About two minutes later the app has its own page here, with your name and a download button.</li></ol></section>
</div>"""
    page("/add-app/", "Add an app or file", "Owner tools.", add, noindex=True, sitemap=False)

    wr = page_head("Write a guide or news", "Write here, press Continue to GitHub, then press Create there.")
    wr += f"""<div class="wrap page-body">
<form id="write-article" class="owner-form" data-repo="{esc(repo)}" novalidate>
  <fieldset><legend>Type</legend>
    <label class="choice"><input type="radio" name="kind" value="guide" checked> Guide</label>
    <label class="choice"><input type="radio" name="kind" value="news"> News</label></fieldset>
  <div class="field"><label for="w-title">Title (needed)</label><input id="w-title" name="title" required autocomplete="off"></div>
  <div class="field"><label for="w-by">Written by. Type your friend's name here. Leave it empty if you wrote it yourself.</label><input id="w-by" name="author" autocomplete="off"></div>
  <div class="field"><label for="w-sum">Short description, one sentence</label><input id="w-sum" name="summary" autocomplete="off"></div>
  <div class="field"><label for="w-text">Text. Start a line with ## for a heading and with - for a list item. A YouTube link alone on a line becomes a video.</label><textarea id="w-text" name="text" rows="12"></textarea></div>
  <p class="form-error" id="write-error" role="alert"></p>
  <button type="submit" class="btn btn-primary">Continue to GitHub</button>
</form>
<section class="prose" aria-labelledby="w-next"><h2 id="w-next">On the GitHub page</h2>
<ol><li>The title and the text are filled in, and the label guide or news is set.</li><li>Press "Create" (on some phones "Submit new issue").</li><li>About two minutes later the article is on the site. To remove it later, close that issue on GitHub.</li></ol></section>
</div>"""
    page("/write/", "Write a guide or news", "Owner tools.", wr, noindex=True, sitemap=False)

    av = page_head("Add a video", "New videos on the YouTube channel appear by themselves. Use this for an older video, or one from another channel.")
    av += f"""<div class="wrap page-body">
<form id="add-video" class="owner-form" data-repo="{esc(repo)}" novalidate>
  <div class="field"><label for="v-link">YouTube link (needed)</label><input id="v-link" name="video" type="url" inputmode="url" required autocomplete="off"></div>
  <div class="field"><label for="v-title">Title (needed)</label><input id="v-title" name="title" required autocomplete="off"></div>
  <div class="field"><label for="v-sum">Short description</label><input id="v-sum" name="summary" autocomplete="off"></div>
  <p class="form-error" id="video-error" role="alert"></p>
  <button type="submit" class="btn btn-primary">Continue to GitHub</button>
</form>
<p>On GitHub, press "Create". The video appears on the Videos page about two minutes later.</p>
</div>"""
    page("/add-video/", "Add a video", "Owner tools.", av, noindex=True, sitemap=False)


def not_found():
    body = page_head("Page not found", "This page does not exist, or it has moved.")
    body += """<div class="wrap page-body prose"><p>Try a search, or go to one of these pages:</p>
<ul><li><a href="/">Home</a></li><li><a href="/apps/">Apps</a></li><li><a href="/videos/">Videos</a></li><li><a href="/guides/">Guides</a></li></ul>
<form class="search-big" role="search" action="/search/" method="get"><label for="nf-q">Search Blind World Hub</label>
<div class="hero-search-row"><input id="nf-q" name="q" type="search"><button type="submit">Search</button></div></form></div>"""
    page("/404.html", "Page not found", "Page not found.", body, noindex=True, sitemap=False)


def finish():
    today = dt.date.today().isoformat()
    urls = "".join(f"<url><loc>{esc(SITE + p)}</loc><lastmod>{today}</lastmod><priority>{pr}</priority></url>"
                   for p, pr in pages_for_sitemap)
    write("/sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
    write("/robots.txt", f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /add-app/\nDisallow: /write/\nDisallow: /add-video/\nSitemap: {SITE}/sitemap.xml\n")
    write("/search.json", json.dumps(search_items, ensure_ascii=False, separators=(",", ":")))
    write("/manifest.webmanifest", json.dumps({
        "name": NAME, "short_name": "BW Hub", "start_url": "/", "display": "standalone",
        "background_color": "#0f2340", "theme_color": "#0f2340", "description": CFG["tagline"],
        "icons": [{"src": "/assets/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/assets/img/icon-512.png", "sizes": "512x512", "type": "image/png"}]}))
    write("/.nojekyll", "")
    v = CFG.get("googleSiteVerificationFile")
    if v:
        write("/" + v, f"google-site-verification: {v}\n")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "static"), OUT)
    releases, issues, feed = load_sources()
    apps = build_apps(releases)
    arts, extra_videos = build_articles(issues)
    videos = build_videos(feed, extra_videos, apps)
    if feed:
        write("/videos.json", json.dumps(feed, ensure_ascii=False))
    home(apps, videos, arts)
    apps_index(apps)
    for a in apps:
        app_page(a, apps)
    videos_page(videos)
    articles_pages(arts)
    static_pages()
    search_page()
    owner_pages()
    not_found()
    finish()
    print(f"built: {len(apps)} apps, {len(videos)} videos, {len(arts['guide'])} guides, {len(arts['news'])} news, "
          f"{len(pages_for_sitemap)} pages in the sitemap")
    for w in warnings:
        print("warning:", w)


main()
