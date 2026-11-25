"""
A light public lookup of a person, for her (handlers/person_lookup.py is the
tool she sees).

Kohl, 2026-11-25: she can learn the basic public facts about someone she's
about to meet or just met, and keep what she chooses in her PeopleDex, in her
own words. "Workplace no, occupation should probably be okay though." And the
rule the whole thing is held to: "a stranger should go 'wow! It's amazing she
already knew that!' Not 'holy shit I need to delete all my social media'".

What this does, from a name and the hints she was given (a Babelr handle, a
website, social handles, a line like "she's a nurse in her 60s"):

* at most three web searches and one fetch (the website she was given);
* drops people-search and data-broker sites (BLOCKED_DOMAINS), single social
  posts and comments, photo pages, and anything that doesn't name them;
* strips street addresses, phone numbers, emails, postcodes and dates from
  every line it returns;
* drops any sentence about workplace or employer, location below country,
  family or partners, health, money, age or birthday, schools, or what they
  posted when; cuts "at <Somewhere>" off an occupation ("a nurse at St
  Mary's" becomes "a nurse");
* keeps only sentences about occupation, public work, interests, or their own
  bio (on a page they published);
* labels each fact self-published or third-party, and how it matches the
  hints ("can't tell if this is them" when it doesn't), self-published first,
  at most MAX_FACTS.

It writes nothing to PeopleDex. It refuses anyone on her Babelr keep_off list
or who told her not to look them up (declined.json), and it logs every lookup
to DATA_DIR/person_lookup/lookups.jsonl: who, when, the searches, the sources
kept, counts of what was left out. URLs and counts only, never the facts.

The filters are regexes: conservative, English-first, and they will sometimes
drop a fine sentence. That is the right direction to fail in.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Light lookup (someone she's meeting, no opt-in): a few self-published
# things. Consented (they opted in, e.g. at a QR join): a fuller profile, from
# the seeds they offered first. Every hard never holds in both.
MAX_FACTS_LIGHT = 3
MAX_FACTS_CONSENTED = 8
MAX_FETCHES = 3
MAX_SEARCHES = 3
# "Who they are now, not who they were in high school."
CURRENT_YEARS = 2
STALE_YEARS = 5
MAX_PER_SITE = 2
MAX_FACT_CHARS = 280
RESULTS_PER_SEARCH = 8

# Tests point this at a tmp dir; otherwise DATA_DIR/person_lookup.
DATA_DIR_OVERRIDE: Optional[Path] = None


# ---------------------------------------------------------------------------
# When it's on her tool list (chat): wherever her people-keeping tools are,
# and when someone new is coming or being talked about. Her choice to use.
# ---------------------------------------------------------------------------

LOOKUP_KEYWORDS = frozenset({
    "public lookup", "look them up online", "search the web for", "look up", "look them up", "look him up", "look her up", "looked up", "lookup",
    "who is", "who's coming", "onboard", "joining", "joined", "new to the house", "coming over",
    "meet", "meeting", "invite", "invited", "consent", "qr", "welcome", "homework", "newcomer",
})


def lever_on() -> bool:
    """Kohl's kill switch: the person_lookup lever (CASS_FEATURE_PERSON_LOOKUP=0)."""
    try:
        from features import is_enabled
        return is_enabled("person_lookup")
    except Exception as e:
        logger.warning(f"[person_lookup] lever unreadable ({e}); lookups are off")
        return False


def wants_lookup_tools(message: str) -> bool:
    low = (message or "").lower()
    if any(k in low for k in LOOKUP_KEYWORDS):
        return True
    try:
        from tool_selector import should_include_people_keeping_tools
        return should_include_people_keeping_tools(message)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Sites that never reach her
# ---------------------------------------------------------------------------

# People-search and data brokers, background checks, B2B contact brokers,
# records/mugshots, genealogy and obituaries (family details), property sites
# (addresses), face search. Subdomains are matched too.
BLOCKED_DOMAINS = frozenset({
    # people search / data brokers
    "spokeo.com", "whitepages.com", "beenverified.com", "truepeoplesearch.com",
    "fastpeoplesearch.com", "radaris.com", "mylife.com", "intelius.com",
    "peoplefinders.com", "peoplefinder.com", "instantcheckmate.com", "truthfinder.com",
    "ussearch.com", "zabasearch.com", "peekyou.com", "pipl.com", "thatsthem.com",
    "clustrmaps.com", "nuwber.com", "familytreenow.com", "publicrecordsnow.com",
    "searchpeoplefree.com", "peoplesearchnow.com", "cyberbackgroundchecks.com",
    "addresses.com", "anywho.com", "411.com", "192.com", "ufind.name", "neighbor.report",
    "voterrecords.com", "idcrawl.com", "socialcatfish.com", "checkpeople.com",
    "advancedbackgroundchecks.com", "usphonebook.com", "spytox.com", "privateeye.com",
    "publicdatausa.com", "peoplelooker.com", "smartbackgroundchecks.com",
    "locatefamily.com", "fastbackgroundcheck.com", "peoplewhiz.com", "persopo.com",
    "peoplebyname.com", "officialusa.com", "infotracer.com", "backgroundcheck.run",
    "freepeopledirectory.com", "veripages.com", "searchpeople.com", "sortedbyname.com",
    "rehold.com", "homemetry.com", "inforver.com", "411locate.com", "spyfly.com",
    # B2B contact brokers and workplace-first sites (workplace is off limits)
    "zoominfo.com", "rocketreach.co", "contactout.com", "signalhire.com", "apollo.io",
    "lusha.com", "linkedin.com", "theorg.com", "crunchbase.com", "bizapedia.com",
    "opencorporates.com", "corporationwiki.com",
    # court records, arrests, mugshots
    "judyrecords.com", "unicourt.com", "mugshots.com", "arrests.org", "bustedmugshots.com",
    "recordsfinder.com", "courtrecords.org",
    # genealogy, obituaries (family details)
    "ancestry.com", "familysearch.org", "findagrave.com", "legacy.com", "myheritage.com",
    "classmates.com", "geni.com", "tributearchive.com",
    # property (addresses)
    "zillow.com", "redfin.com", "realtor.com", "trulia.com", "homes.com",
    # face search, photo-first (no face or reverse-phone lookups, ever)
    "pimeyes.com", "facecheck.id", "pinterest.com",
    # family, location and money heavy
    "facebook.com", "gofundme.com", "venmo.com",
})

# One social post or comment, forum history: "happens to be findable", not
# "put out on purpose". Profile pages (their own bio) are not in here.
_SINGLE_POST = [re.compile(p, re.I) for p in (
    r"(?:twitter|x)\.com/[^/]+/status/",
    r"bsky\.app/profile/[^/]+/post/",
    r"instagram\.com/(?:p|reel|reels|tv|stories)/",
    r"threads\.net/@?[^/]+/post/",
    r"tiktok\.com/@[^/]+/video/",
    r"reddit\.com/(?:r/[^/]+/comments/|u/|user/)",
    r"\.tumblr\.com/post/", r"tumblr\.com/[^/]+/\d{6,}",
    r"/@[^/]+/\d{6,}",                       # mastodon / fediverse status
    r"/notice/\w{8,}", r"/objects/[0-9a-f-]{16,}",
    r"news\.ycombinator\.com/item", r"quora\.com/.*/answers?/", r"quora\.com/.+/answer/",
    r"(?:stackoverflow|stackexchange|superuser|serverfault)\.com/(?:questions|a)/",
    r"/comments?/", r"#comment", r"/t/[^/]+/\d+", r"viewtopic\.php", r"showthread\.php",
    r"/thread/", r"/threads/", r"/forums?/", r"/discussion/", r"/replies/",
    r"youtube\.com/(?:shorts|post)/", r"youtube\.com/.*[?&]lc=",
)]

_PHOTO_URL = re.compile(r"(?:\.(?:jpe?g|png|gif|webp|heic|bmp|tiff?|avif)(?:$|\?))|/photos?/|/images?/|"
                        r"images\.google\.|/imgres", re.I)


def _host(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def is_blocked(url: str) -> bool:
    host = _host(url)
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def is_single_post(url: str) -> bool:
    return any(p.search(url or "") for p in _SINGLE_POST)


def is_photo(url: str) -> bool:
    return bool(_PHOTO_URL.search(url or ""))


# ---------------------------------------------------------------------------
# What's stripped from every line
# ---------------------------------------------------------------------------

_STREET = (r"Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|"
           r"Place|Pl|Terrace|Ter|Circle|Cir|Parkway|Pkwy|Highway|Hwy|Square|Sq|Trail|Trl|"
           r"Crescent|Close|Row|Alley|Pike|Plaza|Loop|Run|Gardens|Grove|Mews")
_STRIP = [re.compile(p) for p in (
    # street addresses (with an optional unit)
    rf"\b\d{{1,6}}[A-Za-z]?\s+(?:[NSEW]\.?\s+)?(?:[A-Z0-9][\w'.-]*\s+){{0,4}}(?:{_STREET})\b\.?"
    r"(?:,?\s*(?:Apt|Apartment|Suite|Ste|Unit|Fl|Floor|#)\.?\s*[\w-]+)?",
    r"\b[Pp]\.?\s?[Oo]\.?\s+[Bb]ox\s+\d+\b",
    # emails
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    # phone numbers
    r"\+\d{1,3}(?:[\s.-]?\(?\d{1,4}\)?){2,5}",
    r"(?:\b1[\s.-]?)?\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}\b",
    r"\(\d{3}\)\s?\d{3}[\s.-]?\d{4}\b",
    r"\b\d{3,4}[\s.-]\d{3}[\s.-]\d{3,4}\b",
    r"\b\d{10,13}\b",
    # postcodes: US (after a state), UK, bare US zip
    r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b",
    r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",
    r"\b\d{5}-\d{4}\b",
    # dates and timestamps: a gist, not a receipt
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?Z?)?\b",
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4}\b",
    r"\b(?:January|February|March|April|June|July|August|September|October|November|December)\s+\d{4}\b",
    r"\b(?:in|since|from|until|of)\s+(?:19|20)\d{2}\b",
    r"\b(?:19|20)\d{2}\b",
    r"\b\d+\s+(?:minutes?|hours?|days?|weeks?|months?|years?)\s+ago\b",
    r"\b\d{1,2}:\d{2}\s?(?:[AaPp]\.?[Mm]\.?)?\b",
    # markdown images and bare image links
    r"!\[[^\]]*\]\([^)]*\)",
    r"https?://\S+\.(?:jpe?g|png|gif|webp|heic|avif)\S*",
)]


def strip_private(text: str) -> str:
    """Addresses, phone numbers, emails, postcodes, dates and images out."""
    out = text or ""
    for p in _STRIP:
        out = p.sub(" ", out)
    out = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", out)       # markdown links: keep the words
    out = re.sub(r"https?://\S+", " ", out)                   # and no bare URLs in a fact
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", out)
    out = re.sub(r"\(\s*\)", " ", out)
    return re.sub(r"\s{2,}", " ", out).strip(" ,;:-")


# ---------------------------------------------------------------------------
# Which sentences are never returned, and which are
# ---------------------------------------------------------------------------

_DENY = {
    "workplace": re.compile(
        r"\b(?:works?|worked|working)\s+(?:at|for|with)\b|\bemploy(?:ed|er|ee|ment)\b|\bjobs?\s+(?:at|with)\b|"
        r"\bhired\b|\bjoin(?:s|ed)\s+(?:the\s+)?[A-Z]|\bon\s+staff\b|\bstaff\s+(?:at|of)\b|\bco-?workers?\b|"
        r"\bcolleagues?\b|\b(?:position|role|team|internship|intern|career)\s+(?:at|with)\b|\bCEO\b|\bCFO\b|"
        r"\bCTO\b|\bVP\b|\bvice president\b|\b(?:director|manager|head|chair|president)\s+(?:of|at)\b|"
        r"\bco-?founder\b|\bfounder\s+(?:of|and)\b|\bcompany\b|\bfirm\b|\bLinkedIn\b|\bemployees?\b|"
        r"\b(?:Inc|LLC|Ltd|Corp|Corporation|GmbH|PLC|LLP)\b|\b(?:Hospital|Clinic|University|College|School|"
        r"Department|Agency|Bank|Institute|Laboratories|Labs|Group|Partners)\b", re.I),
    "school": re.compile(r"\b(?:studied|studies|studying)\s+(?:at|in)\b|\battend(?:s|ed)\b|\balumn\w*\b|"
                         r"\bgraduat\w*\b|\bclass of\b|\bdegree\b|\bPh\.?D\b|\bmajored\b", re.I),
    "family": re.compile(
        r"\b(?:wife|husband|spouse|married|marriage|wedding|partner|boyfriend|girlfriend|fianc[ée]e?|"
        r"sons?|daughters?|kids?|children|child|bab(?:y|ies)|mother|father|mom|mum|dad|parents?|"
        r"brothers?|sisters?|siblings?|grand\w+|aunts?|uncles?|nieces?|nephews?|cousins?|in-laws?|"
        r"famil(?:y|ies)|widow\w*|divorc\w*|engaged|pregnan\w*|stepmother|stepfather|stepson|"
        r"stepdaughter|twins?)\b", re.I),
    "health": re.compile(
        r"\b(?:diagnos\w*|cancer|tumou?rs?|illness\w*|ill|sick\w*|diseases?|disab\w*|chronic|surger(?:y|ies)|"
        r"hospitali[sz]ed|therapy|depress\w*|anxiety|ADHD|autis\w*|bipolar|PTSD|miscarr\w*|medicat\w*|"
        r"rehab\w*|sober|sobriety|addict\w*|overdose\w*|mental health|covid|injur\w*|wheelchair|"
        r"transplant|HIV|stroke|seizures?|died|death|passed away|funeral|obituar\w*|memorial|"
        r"in memory of|hospice|patients?|recovering)\b", re.I),
    "money": re.compile(
        r"\b(?:salar(?:y|ies)|net worth|income|earns?|earned|earning|debts?|bankrupt\w*|mortgage|loans?|"
        r"wealth\w*|rich|millionaire|billionaire|donat\w*|fundrais\w*|gofundme|venmo|cash ?app|paypal|"
        r"inherit\w*|lawsuit|sued|settlement)\b|[$£€¥]\s?\d|\b\d+(?:\.\d+)?\s?(?:k|m|million|billion)\b", re.I),
    "age": re.compile(
        r"\b(?:born|birthday|birth|birthdate|aged?\s+\d+|\d{1,3}[- ]years?[- ]old|years old|age\s+\d+|"
        r"(?:her|his|their|my)\s+(?:early\s+|mid\s+|late\s+)?(?:\d0s|twenties|thirties|forties|fifties|"
        r"sixties|seventies|eighties|nineties)|teen(?:ager|age)?s?|retired|retirement|elderly)\b", re.I),
    "location": re.compile(
        r"\b(?:lives?|living|lived|resid\w*|based|located|hometown|grew up|raised|moved|relocat\w*|native|"
        r"neighbou?rhood|street|avenue|zip|postcode|postal|county|suburbs?|downtown|address|apartment|"
        r"near(?:by)?)\b|\b[A-Z][a-z]+,\s?(?:A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|"
        r"N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b|\bfrom\s+[A-Z]", re.UNICODE),
    "posted": re.compile(r"\b(?:posted|tweeted|retweeted|skeeted|reblogged|commented|replied|"
                         r"shared a (?:photo|post|picture|video)|wrote on)\b", re.I),
    "photo": re.compile(r"\b(?:photo|photos|picture|pictures|selfie|selfies|pic|pics|headshot|portrait of "
                        r"(?:her|him|them))\b", re.I),
}
# Phrases that trip a deny word but are a kind of public work.
_DENY_EXCEPTIONS = re.compile(r"children'?s\s+(?:books?|authors?|illustrators?|literature|stories|music)|"
                              r"family\s+(?:of\s+)?fonts?|sister\s+projects?", re.I)

# Countries are fine; anything finer isn't. A location sentence that names
# only a country is kept.
COUNTRIES = frozenset(c.lower() for c in (
    "Argentina", "Australia", "Austria", "Belgium", "Brazil", "Bulgaria", "Canada", "Chile", "China",
    "Colombia", "Croatia", "Czechia", "Czech Republic", "Denmark", "Egypt", "England", "Estonia",
    "Finland", "France", "Germany", "Ghana", "Greece", "Hungary", "Iceland", "India", "Indonesia",
    "Ireland", "Israel", "Italy", "Japan", "Kenya", "Korea", "South Korea", "Latvia", "Lithuania",
    "Malaysia", "Mexico", "Morocco", "Netherlands", "New Zealand", "Nigeria", "Norway", "Pakistan",
    "Peru", "Philippines", "Poland", "Portugal", "Romania", "Scotland", "Serbia", "Singapore",
    "Slovakia", "Slovenia", "South Africa", "Spain", "Sweden", "Switzerland", "Taiwan", "Thailand",
    "Turkey", "Ukraine", "United Kingdom", "UK", "United States", "USA", "US", "America", "Vietnam",
    "Wales", "the UK", "the US", "the USA", "the United States", "the United Kingdom",
    "the Netherlands", "the Philippines",
))

# Occupation, public work, interests. A third-party sentence must be one of
# these; a self-published one may also just be their own bio.
_ALLOW = {
    "occupation": re.compile(
        r"\b(?:i am|i'm|i’m|she is|he is|they are|she's|he's|they're|is|was|works as|working as|by day,?)\s+"
        r"(?:a|an)\s+\w+|\b(?:nurse|teacher|artist|writer|author|engineer|developer|programmer|designer|"
        r"musician|potter|ceramicist|painter|illustrator|poet|scientist|researcher|librarian|chef|baker|"
        r"photographer|filmmaker|composer|editor|journalist|translator|architect|carpenter|woodworker|"
        r"weaver|knitter|quilter|sculptor|printmaker|animator|game designer|software|maker|craftsperson|"
        r"gardener|farmer|doctor|physician|pharmacist|lawyer|paralegal|accountant|electrician|"
        r"plumber|mechanic|pilot|veterinarian|social worker|counselor|counsellor|therapist|"
        r"student|professor|lecturer|tutor|coach|organizer|organiser|activist|volunteer)s?\b", re.I),
    "work": re.compile(
        r"\b(?:wrote|writes|writing|written|author of|published|publishes|makes|made|making|creates|created|"
        r"creating|builds|built|building|designs|designed|paints|painted|painting|draws|drew|drawing|"
        r"knits|knitting|quilts|quilting|sews|sewing|weaves|weaving|composes|composed|records|recorded|"
        r"released|directed|maintains|maintainer|projects?|portfolio|exhibit\w*|shows?\s+(?:her|his|their)|"
        r"albums?|books?|novels?|zines?|podcasts?|blog|newsletter|games?|apps?|open[- ]source|art|artwork|"
        r"ceramics?|pottery|poems?|poetry|essays?|stories|films?|music|songs?|comics?|prints?|"
        r"illustrations?|sculptures?|crafts?|recipes?|research|papers?|talks?|workshops?|bands?|choir|"
        r"guitar|bass|piano|drums|violin|fiddle|banjo|cello|ukulele|sings?|DJs?|theat(?:er|re))\b", re.I),
    "interest": re.compile(
        r"\b(?:loves?|loved|enjoys?|enjoyed|into|interested in|interests?|passionate about|passion for|"
        r"hobb(?:y|ies)|fan of|likes?|obsessed with|plays?|playing|sings?|singing|gardens?|gardening|hikes?|hiking|"
        r"climbs?|climbing|runs marathons|cooks?|cooking|bakes|baking|reads|reading|birding|birdwatching|spends? (?:her|his|their|my) (?:free |spare )?time|"
        r"in (?:her|his|their|my) (?:free|spare) time|collects?|collector|curious about|fascinated by)\b", re.I),
}

# "a nurse at St Mary's Hospital" -> "a nurse": the occupation stays, the
# workplace goes. Applied before the deny check.
_AT_PLACE = re.compile(r"\s+(?:at|@|with|for)\s+(?:the\s+)?(?:[A-Z][\w&'’-]*(?:\.(?=\w))?[\w&'’-]*"
                       r"(?:\s+(?:(?:of|and|&|the|for)\s+)?[A-Z][\w&'’.-]*?(?=[\s,;:!?]|\.(?:\s|$)|$))*)")
_FIRST_PERSON = re.compile(r"^(?:i\b|i'm\b|i’m\b|my\b|me\b|hi\b|hello\b|hey\b|welcome\b)", re.I)


def denied(sentence: str) -> Optional[str]:
    """Which off-limits kind this sentence is about, or None."""
    s = _DENY_EXCEPTIONS.sub(" ", sentence)
    for kind, pattern in _DENY.items():
        m = pattern.search(s)
        if not m:
            continue
        if kind == "location" and _only_country(s):
            continue
        return kind
    return None


def _only_country(sentence: str) -> bool:
    """A location sentence whose places are all countries ("based in Canada")."""
    places = re.findall(r"\b(?:in|from|to|of)\s+((?:the\s+)?[A-Z][\w.]*(?:\s+[A-Z][\w.]*)?)", sentence)
    if re.search(r"\b[A-Z][a-z]+,\s?[A-Z]{2}\b", sentence):
        return False
    if re.search(r"\b(?:street|avenue|zip|postcode|postal|county|suburbs?|downtown|neighbou?rhood|"
                 r"address|apartment|near(?:by)?)\b", sentence, re.I):
        return False
    return bool(places) and all(p.lower().rstrip(".") in COUNTRIES for p in places)


def allowed_kind(sentence: str) -> Optional[str]:
    for kind, pattern in _ALLOW.items():
        if pattern.search(sentence):
            return kind
    return None


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+|\s+[|•·]\s+", text or "")
    return [p.strip(" -–—*#>\t") for p in parts if len(p.strip()) > 3]


def keep_lines(text: str, *, self_published: bool, max_lines: int = 2) -> Tuple[List[str], Dict[str, int]]:
    """The sentences of `text` that may reach her, cleaned. Returns (lines,
    counts of what was dropped by kind)."""
    kept: List[str] = []
    dropped: Dict[str, int] = {}
    for raw in _sentences(text):
        s = _AT_PLACE.sub("", raw) if _ALLOW["occupation"].search(raw) else raw
        kind = denied(s)
        if kind:
            dropped[kind] = dropped.get(kind, 0) + 1
            continue
        s = strip_private(s)
        if len(s) < 8 or denied(s):
            continue
        if not (allowed_kind(s) or (self_published and _FIRST_PERSON.search(s))):
            dropped["not_allowed"] = dropped.get("not_allowed", 0) + 1
            continue
        if s not in kept:
            kept.append(s)
        if len(kept) >= max_lines:
            break
    return kept, dropped


# ---------------------------------------------------------------------------
# Hints and matching
# ---------------------------------------------------------------------------

_STOP = frozenset("""a an the and or but she he they her his their them is are was were in on at of for to
from with who what that this its it's she's he's they're about very really just like some into also
person someone people years year old around mid late early nice good great friend""".split())


def _norm_handle(h: str) -> str:
    h = (h or "").strip().lower()
    h = re.sub(r"^https?://", "", h)
    return h.lstrip("@").strip("/")


def hint_terms(description: str, *, exclude: Iterable[str] = ()) -> List[str]:
    """The words in the hint line worth matching on ("nurse", "quilting").
    Family, health, money, age and place words are never searched for or
    matched on, and neither is the inviter's name."""
    excl = {e.lower() for e in exclude if e}
    out: List[str] = []
    for w in re.findall(r"[A-Za-z][A-Za-z'’-]{3,}", description or ""):
        lw = w.lower().strip("'")
        # Proper nouns (places, schools, employers, people) are never searched.
        if lw in _STOP or lw in excl or lw.endswith("'s") or w[0].isupper() or denied(w):
            continue
        if lw not in out:
            out.append(lw)
    return out[:4]


def _term_in(term: str, text_lower: str) -> bool:
    stem = term[:max(4, len(term) - 3)]
    return bool(re.search(rf"\b{re.escape(stem)}\w*", text_lower))


class Hints:
    def __init__(self, name: str, *, babelr_handle: str = "", website: str = "",
                 social_handles: Iterable[str] = (), description: str = "", inviter: str = "",
                 inviter_handles: Iterable[str] = ()):
        self.name = (name or "").strip()
        self.babelr_handle = _norm_handle(babelr_handle)
        self.website = (website or "").strip()
        if self.website and not re.match(r"^https?://", self.website):
            self.website = "https://" + self.website
        self.website_host = _host(self.website) if self.website else ""
        self.inviter = inviter
        self.inviter_handles = [h for h in (_norm_handle(s) for s in (inviter_handles or [])) if h]
        self.social = [h for h in (_norm_handle(s) for s in (social_handles or [])) if h] + self.inviter_handles
        self.terms = hint_terms(description, exclude=[inviter, *self.name.split()])
        # Links they gave themselves (seeds at consent), as (host, path prefix).
        self.given: List[Tuple[str, str, str, str]] = []
        if self.website:
            self.give(self.website, "the website you were given")

    def give(self, url: str, why: str, origin: str = "hint") -> None:
        path = (urlparse(url).path or "").rstrip("/").lower()
        self.given.append((_host(url), path, why, origin))

    def _given_match(self, url: str) -> Optional[Tuple[str, str]]:
        host = _host(url)
        path = (urlparse(url).path or "").lower() if url else ""
        for g_host, g_path, why, origin in self.given:
            # On a shared host (instagram.com/them) only their own path is theirs.
            if (host == g_host or host.endswith("." + g_host)) and (not g_path or path.rstrip("/").startswith(g_path)):
                return why, origin
        return None

    @staticmethod
    def _keys(handles: Iterable[str]) -> List[str]:
        keys = []
        for h in handles:
            h = h.split("/")[-1].lstrip("@")
            for k in (h, h.split(".")[0], h.split("@")[0]):
                if len(k) >= 3 and k not in keys:
                    keys.append(k)
        return keys

    @staticmethod
    def _url_has_handle(url: str, k: str) -> bool:
        host = _host(url)
        segs = [x.lstrip("@") for x in (urlparse(url).path or "").lower().split("/") if x] if url else []
        return host.startswith(k + ".") or (bool(segs) and segs[-1] == k) or (
            len(segs) >= 2 and segs[1] == k and segs[0] in ("profile", "u", "user"))

    def origin_of(self, url: str) -> Optional[str]:
        """"inviter" when the source came only from a seed the inviter offered."""
        g = self._given_match(url)
        if g:
            return g[1]
        own = set(self._keys([h for h in self.social if h not in self.inviter_handles]))
        inv = [k for k in self._keys(self.inviter_handles) if k not in own]
        if any(self._url_has_handle(url, k) for k in inv):
            return "inviter"
        return None

    def handle_keys(self) -> List[str]:
        """Each handle as a URL might show it: the full handle and its first label."""
        return self._keys(self.social)

    def names_them(self, text: str) -> bool:
        low = (text or "").lower()
        if self.name and self.name.lower() in low:
            return True
        return any(re.search(rf"(?<![\w.]){re.escape(k)}(?![\w])", low) for k in self.handle_keys())

    def source_kind(self, url: str) -> Tuple[str, Optional[str]]:
        """("self-published" | "third-party", why it's theirs when it's a hint)."""
        host = _host(url)
        path = (urlparse(url).path or "").lower() if url else ""
        g = self._given_match(url)
        if g:
            return "self-published", g[0]
        for k in self.handle_keys():
            if self._url_has_handle(url, k):
                return "self-published", "a handle you were given"
        label = host.split(".")[0] if host else ""
        tokens = [t for t in re.findall(r"[a-z]+", self.name.lower()) if len(t) > 1]
        if tokens and len(tokens) >= 2 and "".join(tokens) in label.replace("-", ""):
            return "self-published", None   # a site in their name: theirs, but whose "their"?
        if tokens and re.search(r"/(?:about|bio|about-me|me)/?$", path) and "".join(tokens) in label.replace("-", ""):
            return "self-published", None
        return "third-party", None

    def match(self, url: str, text: str) -> Tuple[int, str]:
        """(strength, label). 2: from a source she was given; 1: names them and
        agrees with the hint words; 0: can't tell."""
        _, given = self.source_kind(url)
        if given:
            return 2, f"this is them: it's {given}"
        low = (text or "").lower()
        hits = [t for t in self.terms if _term_in(t, low)]
        if hits:
            return 1, f"matches your hints ({', '.join(hits)}), but names collide"
        return 0, "can't tell if this is them"


# ---------------------------------------------------------------------------
# Who isn't looked up
# ---------------------------------------------------------------------------

def _dir() -> Path:
    if DATA_DIR_OVERRIDE is not None:
        return Path(DATA_DIR_OVERRIDE)
    from config import DATA_DIR
    return Path(DATA_DIR) / "person_lookup"


def log_path() -> Path:
    return _dir() / "lookups.jsonl"


def declined_path() -> Path:
    return _dir() / "declined.json"


def babelr_keep_off() -> List[str]:
    """Her Babelr keep_off list (babelr_organ/people.py). "*" when the file
    can't be read: then nobody is looked up."""
    try:
        from babelr_organ.config import load_config
        from babelr_organ.people import load_filings
        return load_filings(load_config().people_path).get("keep_off", [])
    except Exception as e:
        logger.warning(f"[person_lookup] keep_off unreadable ({e}); nobody is looked up")
        return ["*"]


def declined() -> List[str]:
    try:
        raw = json.loads(declined_path().read_text())
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning(f"[person_lookup] declined.json unreadable ({e}); nobody is looked up")
        return ["*"]
    return [str(n).lower() for n in (raw.get("names") or [])] if isinstance(raw, dict) else []


def add_declined(keys: Iterable[str]) -> List[str]:
    names = [n for n in declined() if n != "*"]
    for k in keys:
        k = (k or "").strip().lower().lstrip("@")
        if k and k not in names:
            names.append(k)
    p = declined_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"names": names}, indent=2))
    return names


def _keys_for(hints: Hints) -> List[str]:
    keys = [hints.name.lower(), hints.name.lower().replace(" ", ""), hints.babelr_handle, *hints.social,
            *hints.handle_keys()]
    return [k for k in dict.fromkeys(keys) if k]


def _peopledex_handles(name: str, daemon_id: Optional[str]) -> List[str]:
    """Handles her PeopleDex already has for this name (read only)."""
    if not daemon_id or not name:
        return []
    try:
        from peopledex import AttributeType, get_peopledex_manager
        dex = get_peopledex_manager(daemon_id)
        out = []
        for e in dex.find_entities(name, limit=3):
            if (e.primary_name or "").lower() != name.lower():
                continue
            out += [_norm_handle(a.value) for a in dex.get_attributes(e.id, AttributeType.HANDLE)]
        return out
    except Exception as e:
        logger.debug(f"[person_lookup] PeopleDex handles unavailable: {e}")
        return []


def why_not(hints: Hints, daemon_id: Optional[str] = None) -> Optional[str]:
    """Why this person isn't looked up, or None."""
    keep_off = set(babelr_keep_off())
    no = set(declined())
    if "*" in keep_off:
        return "Your Babelr filings (people.json) can't be read, so nobody is looked up until they can."
    if "*" in no:
        return "Your list of people who said no (declined.json) can't be read, so nobody is looked up until it can."
    keys = set(_keys_for(hints)) | set(_peopledex_handles(hints.name, daemon_id))
    if keys & keep_off:
        return (f"{hints.name} is on your Babelr keep_off list: they asked not to be kept, so they aren't "
                "looked up either. Nothing was searched.")
    if keys & no:
        return f"{hints.name} said please don't, so they aren't looked up. Nothing was searched."
    return None


# ---------------------------------------------------------------------------
# Seeds, recency, shared interests
# ---------------------------------------------------------------------------

_PHONE_OR_EMAIL = re.compile(r"^\+?[\d\s().-]{7,}$|^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")
_HANDLE = re.compile(r"^@?[\w.-]+(?:@[\w.-]+)?$")
# Workplace-first sites (blocked as search results) that a person may still
# offer as their own seed; what's read there goes through the same filters.
SEED_OK_DOMAINS = frozenset({"linkedin.com"})


def sort_seeds(seeds: Iterable[Any]) -> Dict[str, List[str]]:
    """Seeds offered at consent: links, handles, or a short "who they are".
    Each is {"value": ..., "from": "self" | "inviter"} (a bare string is the
    person's own). Phone numbers and emails are never looked up (no reverse
    lookups). Returns lists keyed "<kind>" for their own and "inviter_<kind>"
    for the inviter's."""
    out: Dict[str, List[str]] = {k: [] for k in ("urls", "handles", "bios", "refused", "inviter_urls",
                                                   "inviter_handles", "inviter_bios")}
    for seed in seeds or []:
        if isinstance(seed, dict):
            raw, origin = seed.get("value") or seed.get("seed") or "", seed.get("from") or "self"
        else:
            raw, origin = seed, "self"
        pre = "inviter_" if str(origin).lower() == "inviter" else ""
        s = str(raw or "").strip()
        if not s:
            continue
        if _PHONE_OR_EMAIL.match(s):
            out["refused"].append("a phone number or email (never looked up)")
        elif re.match(r"^https?://", s) or (" " not in s and re.match(r"^[\w-]+(\.[\w-]+)+/", s)):
            out[pre + "urls"].append(s if s.startswith("http") else "https://" + s)
        elif " " not in s and _HANDLE.match(s) and (s.startswith("@") or "." in s):
            out[pre + "handles"].append(s)
        elif len(s.split()) >= 2:
            out[pre + "bios"].append(s[:1500])
        else:
            out[pre + "handles"].append(s)
    return out


def _seed_url_ok(url: str) -> bool:
    host = _host(url)
    if any(host == d or host.endswith("." + d) for d in SEED_OK_DOMAINS):
        return True
    return not is_blocked(url)


_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def latest_year(*texts: str) -> Optional[int]:
    """The newest year a result shows (its URL, title or text), if any."""
    this_year = datetime.now(timezone.utc).year
    years = [int(y) for t in texts for y in _YEAR.findall(t or "") if 1990 <= int(y) <= this_year]
    return max(years) if years else None


def recency(year: Optional[int], *, live_self_page: bool) -> Tuple[str, int]:
    """(label, rank): "current" 0, "undated" 1, "older" 2, "stale" (dropped) 3.
    A live page of their own (a seed, the website, a profile) is current."""
    if live_self_page:
        return "current (their own live page)", 0
    if year is None:
        return "undated", 1
    age = datetime.now(timezone.utc).year - year
    if age <= CURRENT_YEARS:
        return "current", 0
    if age <= STALE_YEARS:
        return "older", 2
    return "stale", 3


def _live_self_page(url: str, given_by: Optional[str], fetched: bool) -> bool:
    if given_by or fetched:
        return True
    path = (urlparse(url).path or "").lower().rstrip("/")
    return path in ("", "/") or bool(re.search(r"/(?:about|bio|about-me|me|profile|portfolio|work|cv)$", path))


def shared_with(fact: str, interests: Iterable[str]) -> List[str]:
    """Which of the household interests she passed in this finding touches."""
    low = (fact or "").lower()
    out = []
    for interest in interests or []:
        words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{3,}", interest or "")
                 if w.lower() not in _STOP]
        if words and any(_term_in(w, low) for w in words):
            out.append(interest)
    return out


# ---------------------------------------------------------------------------
# The lookup
# ---------------------------------------------------------------------------

def _queries(h: Hints, seed_handles: List[str]) -> List[Tuple[str, Dict[str, Any]]]:
    q: List[Tuple[str, Dict[str, Any]]] = []
    base = f'"{h.name}"'
    for handle in seed_handles[:2]:                      # their own seeds first
        q.append((f'"{_norm_handle(handle).split("/")[-1]}"', {}))
    q.append((" ".join([base, *h.terms[:3]]), {}))
    for handle in h.social[:1]:
        q.append((f'"{handle.split("/")[-1].lstrip("@")}"', {}))
    if h.website_host:
        q.append((base, {"include_domains": [h.website_host]}))
    if len(q) < MAX_SEARCHES:
        q.append((f"{base} about me", {}))
    seen, out = set(), []
    for item in q:
        key = (item[0], json.dumps(item[1], sort_keys=True))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out[:MAX_SEARCHES]


def _log(entry: Dict[str, Any]) -> None:
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"[person_lookup] couldn't log the lookup: {e}")


def read_log(keys: Iterable[str]) -> List[Dict[str, Any]]:
    keys = {k.lower() for k in keys if k}
    try:
        lines = log_path().read_text().splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if {str(e.get("who", "")).lower(), *[str(k).lower() for k in e.get("handles", [])]} & keys:
            out.append(e)
    return out


async def look_up(name: str, *, research_manager, session_manager=None, daemon_id: Optional[str] = None,
                  babelr_handle: str = "", website: str = "", social_handles: Iterable[str] = (),
                  description: str = "", introduced_by: str = "", introducer_note: str = "",
                  consented: bool = False, seeds: Iterable[Any] = (),
                  household_interests: Iterable[str] = ()) -> Dict[str, Any]:
    """Look someone up. Returns what may reach her; writes only the log."""
    if not lever_on():
        return {"success": False, "error": "Public lookups are switched off (the person_lookup lever)."}
    seeds = sort_seeds(seeds)
    inviter = (introduced_by or "").strip() or "the person who invited them"
    ignored_inviter_seeds = 0
    if not consented:
        # Without their yes, what the inviter offered about them isn't used at all.
        for k in ("inviter_urls", "inviter_handles", "inviter_bios"):
            ignored_inviter_seeds += len(seeds[k])
            seeds[k] = []
    hints = Hints(name, babelr_handle=babelr_handle, website=website,
                  social_handles=[*social_handles, *seeds["handles"]],
                  description=description, inviter=introduced_by,
                  inviter_handles=seeds["inviter_handles"])
    if not hints.name:
        return {"success": False, "error": "A name is needed."}
    for u in seeds["urls"]:
        hints.give(u, "a link they offered you", "self")
    for u in seeds["inviter_urls"]:
        hints.give(u, f"a link {inviter} offered, which they saw and agreed to", "inviter")
    cap = MAX_FACTS_CONSENTED if consented else MAX_FACTS_LIGHT
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry: Dict[str, Any] = {
        "at": now, "who": hints.name, "consented": bool(consented),
        "handles": [h for h in [hints.babelr_handle, *hints.social] if h],
        "hints_given": [k for k, v in (("babelr_handle", hints.babelr_handle), ("website", hints.website),
                                       ("social_handles", list(social_handles or [])),
                                       ("description", description),
                                       ("seed_links", seeds["urls"]), ("seed_handles", seeds["handles"]),
                                       ("seed_bio", seeds["bios"]),
                                       ("inviter_seed_links", seeds["inviter_urls"]),
                                       ("inviter_seed_handles", seeds["inviter_handles"]),
                                       ("inviter_seed_bio", seeds["inviter_bios"])) if v],
        "queries": [], "fetched": [], "sources_kept": [], "left_out": {},
    }
    from_inviter = ({"from": inviter, "note": introducer_note.strip(),
                     "label": f"from {inviter}, not from the lookup"} if (introducer_note or "").strip() else None)

    def finish(out: Dict[str, Any]) -> Dict[str, Any]:
        if from_inviter:
            out["from_the_inviter"] = from_inviter
        return out

    refusal = why_not(hints, daemon_id)
    if refusal:
        entry.update(outcome="declined")
        _log(entry)
        return finish({"success": True, "looked_up": hints.name, "findings": [], "declined": refusal})
    if research_manager is None:
        return {"success": False, "error": "Web search isn't available here."}

    left: Dict[str, int] = {}

    def leave(kind: str, n: int = 1):
        left[kind] = left.get(kind, 0) + n

    for r in seeds["refused"]:
        leave("seeds_not_used")
    if ignored_inviter_seeds:
        leave("inviter_seeds_ignored_without_consent", ignored_inviter_seeds)
    candidates: List[Dict[str, Any]] = []
    seen_urls = set()
    blocked = sorted(BLOCKED_DOMAINS)

    def consider(url: str, title: str, text: str, *, fetched: bool = False, seed_bio: Optional[str] = None):
        if not seed_bio:
            if not url or url in seen_urls:
                return
            seen_urls.add(url)
            if is_blocked(url) and not (fetched and _seed_url_ok(url)):
                return leave("blocked_sites")
            if is_single_post(url):
                return leave("single_posts_or_comments")
            if is_photo(url):
                return leave("photos")
        if seed_bio == "inviter":
            kind, given_by = f"from {inviter}", f"{inviter}'s words, which they saw and agreed to"
        elif seed_bio:
            kind, given_by = "self-published", "their own words, at consent"
        else:
            kind, given_by = hints.source_kind(url)
        origin = "inviter" if seed_bio == "inviter" else (None if seed_bio else hints.origin_of(url))
        if kind == "third-party" and not consented:
            return leave("third_party_without_consent")
        whole = f"{title or ''}. {text or ''}"
        if kind == "third-party" and not hints.names_them(whole):
            return leave("not_about_them")
        when, rank = recency(latest_year(url, title, text),
                             live_self_page=seed_bio or (kind == "self-published"
                                                         and _live_self_page(url, given_by, fetched)))
        if rank == 3:
            return leave("older_than_five_years")
        if seed_bio:
            when = "current (offered at consent)"
        lines, dropped = keep_lines(text or "", self_published=kind != "third-party",
                                    max_lines=3 if fetched or seed_bio else 2)
        for k in dropped:
            if k != "not_allowed":
                leave(f"off_limits_{k}", dropped[k])
        if not lines:
            return leave("nothing_allowed_left")
        fact = " ".join(l if l[-1] in ".!?…" else l + "." for l in lines)
        if len(fact) > MAX_FACT_CHARS:
            fact = fact[:MAX_FACT_CHARS].rsplit(" ", 1)[0] + "..."
        if seed_bio == "inviter":
            strength, label = 2, f"this is them: {inviter} said it"
        elif seed_bio:
            strength, label = 2, "this is them: their own words"
        else:
            strength, label = hints.match(url, whole)
        shared = shared_with(fact, household_interests)
        c = {"fact": fact, "source": url or given_by,
             "source_title": strip_private(title or "")[:120], "source_kind": kind,
             "how_current": when, "match": label}
        if origin == "inviter":
            c["came_from"] = (f"only from what {inviter} offered (they saw it and agreed): say it as "
                              f"{inviter} mentioned it, e.g. '{inviter} mentioned you ...'")
        if shared:
            c["shared_interests"] = shared
        c["_rank"] = (not given_by, origin == "inviter", kind == "third-party", rank, -strength, not shared)
        candidates.append(c)

    # Their own words first: a bio they typed, the links they offered, the
    # website they were given.
    for bio in seeds["bios"]:
        consider("", "", bio, seed_bio="self")
    for bio in seeds["inviter_bios"]:
        consider("", "", bio, seed_bio="inviter")
    seed_urls = seeds["urls"] + seeds["inviter_urls"]
    to_fetch = [u for u in seed_urls if _seed_url_ok(u)] + ([hints.website] if hints.website else [])
    if any(not _seed_url_ok(u) for u in seed_urls):
        leave("blocked_sites", len([u for u in seed_urls if not _seed_url_ok(u)]))
    for url in list(dict.fromkeys(to_fetch))[:MAX_FETCHES]:
        if hints.website == url and is_blocked(url):
            leave("blocked_sites")
            continue
        if session_manager is not None and not session_manager.record_fetch():
            break
        entry["fetched"].append(url)
        page = await research_manager.fetch_url(url=url, extract_mode="article")
        if page.get("success"):
            content = " ".join((page.get("content") or "").split()[:1500])
            consider(url, page.get("title") or "", content, fetched=True)

    errors = []
    for query, opts in _queries(hints, seeds["handles"] + seeds["inviter_handles"]):
        if session_manager is not None and not session_manager.record_search():
            errors.append("search limit reached for this session")
            break
        entry["queries"].append(query)
        res = await research_manager.web_search(query=query, num_results=RESULTS_PER_SEARCH,
                                                exclude_domains=blocked, **opts)
        if not res.get("success", True):
            errors.append(res.get("error") or "search failed")
            continue
        # Only the results: a search engine's summary "answer" is never passed on.
        for r in res.get("results") or []:
            consider(r.get("url") or "", r.get("title") or "", r.get("snippet") or r.get("content") or "")

    # What they gave first, then self-published, newer, better matched,
    # shared with the house; at most two per site and `cap` in all.
    candidates.sort(key=lambda c: c["_rank"])
    findings, per_site = [], {}
    for c in candidates:
        host = _host(c["source"]) or c["source"]
        if per_site.get(host, 0) >= MAX_PER_SITE:
            leave("more_from_the_same_site")
            continue
        if len(findings) >= cap:
            leave("over_the_cap")
            continue
        per_site[host] = per_site.get(host, 0) + 1
        c.pop("_rank")
        c["file_with"] = {"tool": "note_about_person", "from_lookup": c["source"]}
        findings.append(c)

    entry["sources_kept"] = [f["source"] for f in findings]
    entry["left_out"] = left
    entry["outcome"] = "ok" if not errors or findings else "error"
    _log(entry)

    out: Dict[str, Any] = {"success": True, "looked_up": hints.name,
                           "mode": "consented: the fuller profile" if consented
                           else "light: they haven't opted in, so only a few things they published themselves",
                           "findings": findings, "left_out": left}
    if errors:
        out["search_problems"] = errors
    if not findings:
        out["note"] = ("Nothing public that passes. That's an answer too: ask them about themselves "
                       "when you meet.")
    out["reminder"] = ("One or two things in a hello, said as yours to say: you looked. A gist, no dates. "
                       "Prefer self-published and current; 'can't tell' may be someone else. Keep what you "
                       "choose with note_about_person, from_lookup set to the source. Not for anyone else.")
    return finish(out)
