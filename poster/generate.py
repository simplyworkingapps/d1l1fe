"""Writes one post, saves it to the page, and pings your phone.

Two streams:
  social   - casual Facebook text + Instagram caption and picture
  linkedin - professional IT-industry post

Run by GitHub Actions on a schedule. Locally:
    python poster/generate.py --fake                       # test social post, no API key
    python poster/generate.py --channel linkedin --fake    # test LinkedIn post
    python poster/generate.py --topic cats                 # force a topic
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "poster" / "config.yaml"
POSTS = ROOT / "docs" / "posts.json"
IMAGES = ROOT / "docs" / "img"

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_ATTEMPTS = 3
CHANNELS = ("social", "linkedin")

# Last-line safety net. The writing instructions already keep things clean;
# this catches anything that slips through.
BLOCKED = re.compile(
    r"\b(fuck|shit|bitch|damn|ass(hole)?|sex|sexy|nude|naked|drunk|wasted|hungover|"
    r"weed|cannabis|420|high af|suicid\w*|self[- ]harm|overdose|"
    r"democrat\w*|republican\w*|trump|biden|election|abortion|religio\w*|"
    r"hate|crypto|bitcoin)\b",
    re.IGNORECASE,
)

SAFETY_RULES = """\
Hard rules (this person may be seen by employers, so everything must be safe for work):
- No profanity, innuendo, alcohol-centric or drug content, politics, religion, money/crypto,
  complaints about jobs or employers, or anything about dating.
- Mental-wellness content stays gentle and general: no medical advice, diagnoses, medication,
  crisis talk, or personal health disclosures.
- Never invent facts. Never claim you did something specific (went somewhere, bought
  something, own a pet). Phrase plans as maybes ("might check this out").
- Never name or tag real private people. Never endorse a brand or product.
- Plain text only. At most one emoji per version.

Tone rules (just as important as the rules above):
- Never cocky, arrogant, smug, or show-offy. No bragging, no "I'm better than", no flexing.
- No snark, sarcasm aimed at people, or superiority about places, tastes, or lifestyles.
  Comparisons between cities are affectionate toward both.
- Show empathy whenever it reasonably fits: acknowledge that things can be hard,
  that people are busy or tired, that it's okay not to have it all figured out.
- When humor shows up, it's warm and pointed at yourself or the situation, never at others.
- Invite people in where it fits ("anyone else?", "hope your week's going okay").
"""

LINKEDIN_RULES = """\
LinkedIn-specific rules (hiring managers will read this):
- Never claim a current job, employer, title, project, certification, or result that isn't
  listed in the background above. Learning is fine to mention ("been brushing up on...");
  achievements are not unless they're in the background.
- Don't mention job hunting or being between roles unless told above that it's okay.
- Never criticize a company, product, vendor, or person. Never share confidential-sounding
  details or anything a security team would wince at (no real IPs, credentials, internal names).
- No hype or "thought leader" style: no "Agree?", no one-sentence-per-line drama, no
  "Here's what nobody tells you", no humblebrags, no engagement bait.
- Credit the source when talking about news, and keep claims to what the source says.
- Humble and curious: share what you find useful or interesting, admit what you're still
  figuring out, and make room for other people's experience.
- Empathy fits naturally here too: outages are stressful, help desks are underappreciated,
  everyone was new once, burnout is real.
- 60 to 180 words, short paragraphs, blank lines between them. End with 2 or 3 relevant
  hashtags on their own line. At most one emoji, usually none.
"""

SOCIAL_FORMATS = """Write three versions of the same idea:
1. "text" (Facebook): 1 to 4 sentences. No hashtags, or one at most.
2. "instagram" (Instagram caption): 1 to 4 sentences, a bit more descriptive since it sits
   under a picture. No links (they don't work there); for an event, name it, the day, and
   the place instead. End with a blank line and 3 to 5 relevant, friendly hashtags.
3. "card": the short line printed on the Instagram image. 4 to 14 words, no hashtags,
   no emoji, no links. It should make sense on its own."""

TONE_REVIEW_SOCIAL = """You're checking a casual social media post before a job-seeker shares it.
Rewrite any part ONLY if it could come across as cocky, arrogant, smug, bragging, snarky,
judgmental, or cold, or if it misses an easy, natural chance to show a little empathy.
Keep the same topic, facts, length, format, and casual voice. Don't add emojis.
Don't make it sappy or preachy; a light touch of warmth is enough.

Facebook post:
{text}

Instagram caption:
{instagram}

Image text:
{card}

Reply with ONLY a JSON object (copy any part unchanged if it was already fine):
{{"text": "...", "instagram": "...", "card": "...", "changed": true or false}}"""

TONE_REVIEW_LINKEDIN = """You're checking a LinkedIn post before an IT professional who is looking
for work shares it. Hiring managers will read it.
Rewrite it ONLY if any part could come across as cocky, arrogant, know-it-all, bragging,
preachy, hype-y, critical of others, or cold; if it claims experience or results that aren't
supported by this background: {background}; or if it misses an easy, natural chance to
show a little empathy or humility. Keep the same topic, facts, length, paragraphs, and hashtags.
Don't make it sappy.

Post:
{text}

Reply with ONLY a JSON object (copy it unchanged if it was already fine):
{{"text": "...", "changed": true or false}}"""

PARTS = {"social": ("text", "instagram", "card"), "linkedin": ("text",)}
LIMITS = {
    "social": {"text": 600, "instagram": 900, "card": 110},
    "linkedin": {"text": 1600},
}


# ── storage ──────────────────────────────────────────────────────────────

def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def load_posts() -> list[dict]:
    if POSTS.exists():
        return json.loads(POSTS.read_text())
    return []


def channel_of(post: dict) -> str:
    return post.get("channel", "social")


def save_posts(posts: list[dict], keep: int) -> None:
    """Keep the newest `keep` posts of each stream."""
    counts: dict[str, int] = {}
    kept = []
    for p in posts:
        c = channel_of(p)
        counts[c] = counts.get(c, 0) + 1
        if counts[c] <= keep:
            kept.append(p)
    POSTS.parent.mkdir(parents=True, exist_ok=True)
    POSTS.write_text(json.dumps(kept, indent=2, ensure_ascii=False) + "\n")
    keep_ids = {p["id"] for p in kept}
    for f in IMAGES.glob("*.jpg"):
        if f.stem not in keep_ids:
            f.unlink()


# ── writing ──────────────────────────────────────────────────────────────

def channel_cfg(cfg: dict, channel: str) -> dict:
    return cfg if channel == "social" else cfg["linkedin"]


def pick_topic(topics: dict, history: list[dict], forced: str | None) -> str:
    if forced:
        if forced not in topics:
            sys.exit(f"Unknown topic '{forced}'. Choose from: {', '.join(topics)}")
        return forced
    recent = {p["topic"] for p in history[:2]}
    choices = [t for t in topics if t not in recent] or list(topics)
    weights = [topics[t].get("weight", 1) for t in choices]
    return random.choices(choices, weights=weights, k=1)[0]


def search_note(t: dict, now: datetime, channel: str) -> str:
    if not t.get("search"):
        return "Don't search; this one comes from general knowledge."
    if channel == "linkedin":
        return (
            "Search the web first so the post is based on something real and current. "
            f"Today is {now:%A, %B %-d, %Y}. Use news or events from the last 14 days "
            "(or, for events, the next 21 days). Put the source URL in link. If you can't "
            "confirm something real and recent, write a timeless practical post on the same "
            "theme instead and leave link empty."
        )
    return (
        "Search the web first so the post is based on something real and current. "
        f"Today is {now:%A, %B %-d, %Y}. Only use events dated between today and "
        f"{(now + timedelta(days=10)):%B %-d}. If you can't confirm a real, upcoming, "
        "safe-for-work item, write a non-event post on the same city instead and leave "
        "link empty."
    )


def build_prompt(cfg: dict, channel: str, topic: str, history: list[dict], now: datetime) -> str:
    cc = channel_cfg(cfg, channel)
    t = cc["topics"][topic]
    recent = "\n".join(f"- {p['text'][:280]}" for p in history[:10]) or "(none yet)"
    if channel == "linkedin":
        return f"""You're ghost-writing a LinkedIn post for an IT professional.

Who's posting: {cc['voice'].strip()}

Their real background (the ONLY experience you may reference): {cc['background'].strip()}
{"They're open to new roles; it's fine to mention that lightly in about one post out of four, never desperately." if cc.get('mention_job_search') else ""}

Topic: {t['brief'].strip()}

{search_note(t, now, channel)}

{SAFETY_RULES}
{LINKEDIN_RULES}
Don't repeat ideas or phrasing from these recent LinkedIn posts:
{recent}

Reply with ONLY a JSON object, no other text:
{{"text": "the LinkedIn post", "link": "source URL for news or an event, or empty string", "why": "one short line on what this is about"}}"""

    return f"""You're ghost-writing a casual personal social media post (Facebook and Instagram).

Who's posting: {cc['voice'].strip()}

Topic: {t['brief'].strip()}

{search_note(t, now, channel)}

{SAFETY_RULES}
{SOCIAL_FORMATS}

Don't repeat ideas or phrasing from these recent posts:
{recent}

Reply with ONLY a JSON object, no other text:
{{"text": "Facebook post", "instagram": "Instagram caption", "card": "image text", "link": "source URL for an event or news item, or empty string", "why": "one short line on what this is about"}}"""


def _text_of(resp) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def call_claude(prompt: str, use_search: bool, cfg: dict, parts: tuple[str, ...]) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    tools = []
    if use_search:
        tools.append({
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 4,
            "user_location": {
                "type": "approximate",
                "city": "Portland",
                "region": "Oregon",
                "country": "US",
                "timezone": cfg.get("timezone", "America/Los_Angeles"),
            },
        })
    messages = [{"role": "user", "content": prompt}]
    for _ in range(4):  # searches can pause mid-way; resume a few times
        kwargs = dict(model=MODEL, max_tokens=2500, messages=messages)
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)
        if resp.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": resp.content}]
    return parse_json(_text_of(resp), parts)


def review_tone(post: dict, channel: str, cfg: dict) -> dict:
    """Second read-through focused only on tone. Keeps the original on any hiccup."""
    import anthropic

    parts = PARTS[channel]
    if channel == "linkedin":
        prompt = TONE_REVIEW_LINKEDIN.format(text=post["text"], background=cfg["linkedin"]["background"].strip())
    else:
        prompt = TONE_REVIEW_SOCIAL.format(**{k: post[k] for k in parts})
    try:
        resp = anthropic.Anthropic().messages.create(
            model=MODEL, max_tokens=1500, messages=[{"role": "user", "content": prompt}]
        )
        data = parse_json(_text_of(resp), parts)
        if data.get("changed"):
            print(f"Tone check softened the post.\n  before: {post['text']}")
        return {**post, **{k: str(data[k]).strip() for k in parts}}
    except Exception as e:  # tone check is a bonus; never lose a post over it
        print(f"Warning: tone check skipped: {e}")
        return post


def parse_json(text: str, parts: tuple[str, ...]) -> dict:
    for m in reversed(re.findall(r"\{.*\}", text, re.DOTALL)):
        try:
            data = json.loads(m)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and all(str(data.get(k, "")).strip() for k in parts):
            return data
    raise ValueError(f"No usable post in reply: {text[:300]!r}")


def fake_post(channel: str, topic: str) -> dict:
    if channel == "linkedin":
        return {
            "text": (
                "Spent some time this week reading up on passkeys and how teams are rolling "
                "them out. The tech is the easy part. The hard part is helping people trust "
                "something new after years of being told to guard their passwords.\n\n"
                "If you've been through a rollout, I'd love to hear what made it click for "
                "your users. And to every help desk fielding those first-week questions: "
                "you're the real MVPs.\n\n#CyberSecurity #ITSupport #Passkeys"
            ),
            "link": "",
            "why": f"test post ({topic})",
        }
    samples = {
        "cats": "Cats sleep around 15 hours a day and still look tired. Honestly, relatable this week. Hope everyone gets some rest this weekend.",
        "clothing": "Still learning the Portland layering game. Any tips on a rain jacket that actually breathes?",
        "wellness": "Gray season is here. Reminder to grab some daylight on lunch, even if it's just a lap around the block.",
        "portland_events": "Might check out a pumpkin patch out on Sauvie Island this weekend. Anyone been lately?",
        "portland_local": "Third straight day of drizzle and the coffee shops are packed. If the gray is getting to you too, you're not alone.",
        "chicago_local": "Still haven't found a tavern-style thin crust out here that's cut in squares. Chicago folks, I miss it.",
    }
    cards = {
        "cats": "Cats sleep 15 hours a day and still look tired. Relatable.",
        "clothing": "Still learning the Portland layering game.",
        "wellness": "Grab a little daylight today, even just a lap around the block.",
        "portland_events": "Pumpkin patch season on Sauvie Island.",
        "portland_local": "Drizzle outside, full coffee shops inside.",
        "chicago_local": "Still looking for tavern-style thin crust, cut in squares.",
    }
    return {
        "text": samples[topic],
        "instagram": samples[topic] + "\n\n#portland #pnwlife #pdx",
        "card": cards[topic],
        "link": "",
        "why": f"test post ({topic})",
    }


def is_clean(post: dict, channel: str) -> tuple[bool, str]:
    for key, limit in LIMITS[channel].items():
        value = str(post.get(key, "")).strip()
        if not value:
            return False, f"empty {key}"
        if len(value) > limit:
            return False, f"{key} too long"
        hit = BLOCKED.search(value.replace("#", " "))
        if hit:
            return False, f"blocked word in {key}: {hit.group(0)}"
    if channel == "social" and ("http" in post["instagram"] or "http" in post["card"]):
        return False, "link in Instagram text"
    link = post.get("link", "")
    if link and not link.startswith("https://"):
        return False, "bad link"
    return True, ""


# ── phone ping ───────────────────────────────────────────────────────────

def notify(post: dict, page_url: str) -> None:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print("NTFY_TOPIC not set; skipping phone notification.")
        return
    preview = post["text"] if len(post["text"]) <= 140 else post["text"][:137] + "..."
    title = "LinkedIn post ready - tap to share" if channel_of(post) == "linkedin" else "New post ready - tap to share"
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=preview.encode("utf-8"),
            headers={"Title": title, "Click": f"{page_url}#{post['id']}", "Tags": "memo"},
            timeout=20,
        ).raise_for_status()
        print("Phone notification sent.")
    except requests.RequestException as e:
        # The post is still saved on the page; a missed ping isn't fatal.
        print(f"Warning: notification failed: {e}")


# ── main ─────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", choices=CHANNELS, default=os.environ.get("CHANNEL") or "social")
    ap.add_argument("--fake", action="store_true", help="test run, no API call")
    ap.add_argument("--topic", help="force a topic from config.yaml")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--notify-only", action="store_true",
                    help="just ping the phone about the newest saved post in this stream")
    args = ap.parse_args()
    channel = args.channel

    cfg = load_config()
    posts = load_posts()
    history = [p for p in posts if channel_of(p) == channel]
    page_url = os.environ.get("PAGE_URL", "").rstrip("/")

    if args.notify_only:
        if history and page_url:
            notify(history[0], page_url)
        return

    cc = channel_cfg(cfg, channel)
    now = datetime.now(ZoneInfo(cfg.get("timezone", "America/Los_Angeles")))
    topic = pick_topic(cc["topics"], history, args.topic or os.environ.get("FORCE_TOPIC") or None)
    use_search = bool(cc["topics"][topic].get("search"))
    print(f"Stream: {channel}  Topic: {topic}  (web search: {use_search})")

    post, reason = None, ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if args.fake:
            candidate = fake_post(channel, topic)
        else:
            prompt = build_prompt(cfg, channel, topic, history, now)
            candidate = call_claude(prompt, use_search, cfg, PARTS[channel])
            candidate = review_tone(candidate, channel, cfg)
        ok, reason = is_clean(candidate, channel)
        if ok:
            post = candidate
            break
        print(f"Attempt {attempt} rejected ({reason}); retrying.")
    if not post:
        sys.exit(f"Couldn't get a clean post after {MAX_ATTEMPTS} tries ({reason}).")

    entry = {
        "id": uuid.uuid4().hex[:8],
        "channel": channel,
        "created": now.isoformat(timespec="minutes"),
        "topic": topic,
        "text": post["text"].strip(),
        "link": str(post.get("link", "")).strip(),
        "why": str(post.get("why", "")).strip(),
    }
    if channel == "social":
        from card import make_card

        entry["instagram"] = post["instagram"].strip()
        entry["card"] = post["card"].strip()
        make_card(entry["card"], topic, IMAGES / f"{entry['id']}.jpg")
        entry["image"] = f"img/{entry['id']}.jpg"

    posts.insert(0, entry)
    save_posts(posts, cfg.get("keep_history", 40))
    print(f"Saved post {entry['id']}:\n{entry['text']}")

    if page_url and not args.no_notify:
        notify(entry, page_url)


if __name__ == "__main__":
    main()
