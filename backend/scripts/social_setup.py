"""
Place Cass's Bluesky or Tumblr credentials (plan "Cass on Bluesky and
Tumblr"). Run by Kohl once she's chosen her handles and said yes; secrets are
typed at a hidden prompt, never on the command line, and written to
DATA_DIR/social/<platform>/credentials.json (mode 600). Nothing is sent
anywhere until the platform's lever is on (CASS_FEATURE_BLUESKY=1 /
CASS_FEATURE_TUMBLR=1).

    python scripts/social_setup.py bluesky     # handle + an app password (Settings > App passwords;
                                               # tick "allow access to direct messages" if DMs will be on)
    python scripts/social_setup.py tumblr      # an OAuth2 app at tumblr.com/oauth/apps, then sign in once

Tumblr: register the app with redirect URL http://localhost/ ; the script
prints a sign-in link, you approve it as her blog, and paste back the URL
the browser lands on (the page itself won't load; that's fine).
"""
import argparse
import getpass
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def bluesky(data_dir):
    from social.config import write_credentials
    handle = input("Her Bluesky handle (e.g. someone.bsky.social): ").strip().lstrip("@")
    password = getpass.getpass("App password (hidden): ").strip()
    service = input("PDS [https://bsky.social]: ").strip() or "https://bsky.social"
    path = write_credentials("bluesky", {"handle": handle, "app_password": password, "service": service},
                             data_dir)
    print(f"Saved to {path}")


def tumblr(data_dir):
    import httpx
    from social.config import write_credentials
    blog = input("Her blog name (the part before .tumblr.com): ").strip()
    client_id = input("OAuth consumer key: ").strip()
    client_secret = getpass.getpass("OAuth consumer secret (hidden): ").strip()
    redirect = "http://localhost/"
    state = secrets.token_urlsafe(16)
    print("\nOpen this, signed in as her blog, and approve:\n")
    print("https://www.tumblr.com/oauth2/authorize?" + urlencode({
        "client_id": client_id, "response_type": "code", "scope": "basic write offline_access",
        "state": state, "redirect_uri": redirect}))
    landed = input("\nPaste the URL the browser landed on: ").strip()
    q = parse_qs(urlparse(landed).query)
    if q.get("state", [""])[0] != state:
        sys.exit("That URL's state doesn't match; start again.")
    r = httpx.post("https://api.tumblr.com/v2/oauth2/token", data={
        "grant_type": "authorization_code", "code": q["code"][0], "client_id": client_id,
        "client_secret": client_secret, "redirect_uri": redirect}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Tumblr refused the code ({r.status_code}).")
    tok = r.json()
    path = write_credentials("tumblr", {"blog": blog, "client_id": client_id, "client_secret": client_secret,
                                        "access_token": tok["access_token"],
                                        "refresh_token": tok.get("refresh_token", "")}, data_dir)
    print(f"Saved to {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Place Cass's social credentials")
    ap.add_argument("platform", choices=["bluesky", "tumblr"])
    ap.add_argument("--data-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    (bluesky if a.platform == "bluesky" else tumblr)(a.data_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
