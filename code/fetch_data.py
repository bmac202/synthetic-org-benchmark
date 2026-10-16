#!/usr/bin/env python3
"""Download the public social-insect datasets onto an external drive.

Usage
-----
    python3 fetch_data.py                          # auto-detect drive, tier "main"
    python3 fetch_data.py --dest /Volumes/OWC      # explicit drive
    python3 fetch_data.py --tier core              # small sets only
    python3 fetch_data.py --dry-run                # show the plan, download nothing
    python3 fetch_data.py --only mersch_keller_2013 beesbook_2018

Design notes
------------
*  Resumable *when the source serves a static object*. Interrupted transfers
   continue where they stopped (curl -C -). This is true of Zenodo files and of
   Dryad's per-file endpoint. The version-level `/download` bundle is not a
   static object and, for a deposit the size of `alciatore_2021`, is not served
   at all: Dryad answers 405 with *"The dataset is too large for zip file
   generation. Please download each file individually."* This file gave two
   wrong explanations for that before reading it; both are set out and withdrawn
   in `dryad_files`, which is the entry to read.
*  Authenticated, for Dryad. Since some date before 31 July 2026 every Dryad
   per-file download answers 401 `{"error":"Unauthorized, must have current
   bearer token"}` without an OAuth token. `dryad_token()` exchanges client
   credentials *you* create for a bearer token; the script never has a way to
   create the account and never writes the secret to a log, a manifest, or a
   command line. Files already on disk at the published size and sha-256 are
   adopted without any token at all, so a browser download is a complete
   substitute.
*  Verified. Zenodo publishes an MD5 per file and Dryad publishes a SHA-256 per
   file; both are checked against the bytes on disk, with one re-download on
   mismatch. `direct` downloads get a size check only, and say so.
*  Idempotent. Anything already present and verified is skipped — and a file
   that is on disk with the right size and checksum is adopted without being
   re-fetched, even when the manifest has no record of it.
*  Honest. Every completed file is recorded in MANIFEST.json with its source
   URL, size, checksum and timestamp, so the provenance of the analysis is
   reconstructable months from now.

Only the Python standard library is required.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import select  # noqa: E402

VERSION = "2.17"          # printed on every run, so you can tell at a glance
                         # which copy of this file actually executed
UA = f"beeorg-fetch/{VERSION} (academic research)"
PROJECT = "BeeOrg"


# --------------------------------------------------------------------------- io
def say(msg: str = "") -> None:
    print(msg, flush=True)


def human(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} PB"


def get_json(url: str, tries: int = 4) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"could not read {url}: {last}")


# --------------------------------------------------------------------- drive
def candidate_drives() -> list[Path]:
    vols = Path("/Volumes")
    if not vols.is_dir():
        return []
    out = []
    for v in sorted(vols.iterdir()):
        try:
            if not v.is_dir() or v.is_symlink():
                continue
            # skip the boot volume and its data sibling
            if os.path.realpath(v) == "/" or v.name in {"Macintosh HD", "Macintosh HD - Data"}:
                continue
            out.append(v)
        except OSError:
            continue
    return out


def resolve_dest(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_dir():
            raise SystemExit(f"destination {p} does not exist or is not a directory")
        return p
    drives = candidate_drives()
    owc = [d for d in drives if "owc" in d.name.lower()]
    if len(owc) == 1:
        say(f"Auto-detected OWC drive: {owc[0]}")
        return owc[0]
    if len(drives) == 1:
        say(f"Using the only external volume found: {drives[0]}")
        return drives[0]
    say("Could not decide which drive to use. Mounted volumes:")
    for d in drives:
        try:
            free = shutil.disk_usage(d).free
        except OSError:
            free = None
        say(f"    {d}    ({human(free)} free)")
    raise SystemExit("\nRe-run with:  python3 fetch_data.py --dest '/Volumes/<your drive>'")


def make_tree(root: Path) -> Path:
    base = root / PROJECT
    for sub in ("data/raw", "data/interim", "data/processed", "code", "logs", "notes"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def install_code(base: Path) -> None:
    """Copy this script's directory into <project>/code so the drive is self-contained.

    A year from now the drive should still explain itself: the data, the code
    that fetched it, and the manifest saying where every byte came from, all in
    one place.
    """
    src = Path(__file__).resolve().parent
    dst = base / "code"
    if src == dst.resolve():
        return
    for item in src.iterdir():
        if item.name in {"__pycache__", ".git", ".DS_Store"} or item.name.endswith(".pyc"):
            continue
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, target)
    say(f"Code installed to {dst}")


# ----------------------------------------------------------------- downloading
# HASHERS: whichever algorithms the repositories actually publish.
#
# Zenodo publishes "md5:<hex>". Dryad publishes a `digest` with a separate
# `digestType`, and for both deposits we care about that type is **sha-256**,
# not md5 -- which the previous version of this file could not have checked,
# because its only verification path was hashlib.md5. An unknown algorithm
# returns None from `digest_of` rather than a wrong answer, and the caller must
# then say out loud that the file went unverified. Silently hashing with the
# wrong function would report a mismatch on a perfectly good file, which is the
# more expensive error: it triggers a re-download of several gigabytes and then
# fails again for the same reason.
HASHERS = {
    "md5": hashlib.md5,
    "sha-1": hashlib.sha1, "sha1": hashlib.sha1,
    "sha-256": hashlib.sha256, "sha256": hashlib.sha256,
    "sha-384": hashlib.sha384, "sha384": hashlib.sha384,
    "sha-512": hashlib.sha512, "sha512": hashlib.sha512,
}


def digest_of(path: Path, algo: str | None, chunk: int = 1 << 20) -> str | None:
    """Hex digest of `path` under `algo`, or None if we cannot compute that algo.

    None means "not checked", never "checked and fine". Callers must treat the
    two differently.
    """
    fn = HASHERS.get((algo or "").strip().lower())
    if fn is None:
        return None
    h = fn()
    with path.open("rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def md5_of(path: Path, chunk: int = 1 << 20) -> str:
    """Kept for callers that know they want md5. Prefer `digest_of`."""
    return digest_of(path, "md5", chunk)  # type: ignore[return-value]


HAVE_CURL = shutil.which("curl") is not None


def _curl_supports(flag: str) -> bool:
    """Older macOS ships curl without --retry-all-errors; check before using it."""
    if not HAVE_CURL:
        return False
    try:
        out = subprocess.run(["curl", "--help", "all"], capture_output=True,
                             text=True, timeout=10).stdout
        return flag in out
    except Exception:  # noqa: BLE001
        return False


RETRY_ALL = _curl_supports("--retry-all-errors")


# ------------------------------------------------------- dryad authentication
DRYAD_TOKEN_URL = "https://datadryad.org/oauth/token"

# Two places, in this order. The environment wins because it is the easy thing
# to do for a single run; the file is what survives a reboot.
DRYAD_CRED_ENV = ("DRYAD_CLIENT_ID", "DRYAD_CLIENT_SECRET")
DRYAD_CRED_FILES = ("~/.config/dryad/credentials.json", "~/.dryad_api.json")

# In-process only. Nothing about a token is written to disk: it is short-lived,
# it grants whatever the account grants, and a cached copy on the external drive
# would outlive both the run and anyone's memory of having put it there.
_DRYAD_TOKEN: dict = {"value": None, "expires_at": 0.0}

DRYAD_NO_CREDENTIALS = """\
Dryad requires an OAuth bearer token for every file download. Without one the
API answers 401 {"error":"Unauthorized, must have current bearer token"}, which
is what the 31 July run hit six times per file.

Creating the account is your action, not this script's — it needs an ORCID
login and this script has no business holding one:

  1. Sign in to https://datadryad.org with your ORCID at least once, so Dryad
     creates a user record. The API account cannot be made before that.
  2. On the "My account" page, create an API account. Dryad shows a client id
     and a client secret. The secret is shown once.
  3. Give them to this script, readable only by you — one line, either form.
     Replace the two bracketed words with the real values before running it;
     pasted unedited, both forms are refused by name rather than sent to Dryad.

     export DRYAD_CLIENT_ID='<CLIENT_ID>'; export DRYAD_CLIENT_SECRET='<CLIENT_SECRET>'

     mkdir -p ~/.config/dryad && printf '{"client_id":"<CLIENT_ID>","client_secret":"<CLIENT_SECRET>"}' > ~/.config/dryad/credentials.json && chmod 600 ~/.config/dryad/credentials.json

The secret is never logged, never written to MANIFEST.json, and never passed on
a command line (see `download`). If a Dryad response ever echoes it back inside
an error, it is redacted before that error is printed.

You do not have to do any of this. Files already on disk at the published size
and sha-256 are adopted and recorded without a token — so downloading a deposit
in a browser and dropping it in data/raw/<key>/ is a complete substitute. The
listing API that publishes those checksums needs no token either."""


# The example in DRYAD_NO_CREDENTIALS is a one-liner, and a one-liner is a thing
# people paste. On 31 July it was pasted unedited and ~/.config/dryad/credentials.json
# ended up holding the literal strings from the example. Without this guard that
# file is found, both exchange styles are tried, and Dryad's rejection is reported
# as "Dryad refused the client credentials" — which is true and useless, because it
# reads as a bad account rather than as an unedited example. The values below are
# every form this file has ever printed plus the obvious neighbours.
DRYAD_PLACEHOLDERS = frozenset({
    "id", "secret", "client_id", "client_secret", "clientid", "clientsecret",
    "your_client_id", "your_client_secret", "your-client-id",
    "your-client-secret", "changeme", "xxx", "...", "todo",
})


def _is_placeholder(value: str) -> bool:
    """True if `value` is example text rather than a credential.

    Two shapes: a known literal, case-insensitively, and anything wrapped in
    angle brackets, which is how this file writes its placeholders now. Real
    Dryad client ids and secrets are long opaque strings, so neither shape can
    collide with one — which matters, because a guard that rejects a working
    credential is worse than the problem it solves.
    """
    v = value.strip()
    return v.lower() in DRYAD_PLACEHOLDERS or (
        len(v) >= 2 and v.startswith("<") and v.endswith(">"))


def _reject_placeholders(cid: str, sec: str, where: str) -> None:
    """Raise if either credential is example text, naming which one and where."""
    bad = [n for n, v in (("client_id", cid), ("client_secret", sec))
           if _is_placeholder(v)]
    if not bad:
        return
    raise RuntimeError(
        f"{where} holds the placeholder text from this script's own example, "
        f"not a credential: {' and '.join(bad)}. Nothing was sent to Dryad — a "
        f"placeholder would come back as 'invalid client', which reads like a "
        f"broken account rather than an unedited copy-paste.\n\n"
        f"{DRYAD_NO_CREDENTIALS}")


def _redact(text: str, *secrets: str | None) -> str:
    """Remove credential material from anything about to be printed.

    Error paths are where secrets leak: a server that rejects a credential often
    quotes it back, and that string then travels into an exception message, a
    failure summary, and whatever the user pastes into a chat window. Redacting
    at the boundary is cheaper than auditing every f-string downstream.
    """
    for s in secrets:
        if s and len(s) >= 6:
            text = text.replace(s, "<redacted>")
    return text


def dryad_credentials() -> tuple[str, str, str] | None:
    """Find a Dryad client id/secret. Returns (id, secret, where) or None.

    Refuses a credentials file that is readable by anyone but its owner. That is
    a real refusal rather than a warning because the alternative is a warning
    scrolling past in the middle of a 4.9 GB transfer, and because the fix is one
    command that the message states.
    """
    cid, sec = (os.environ.get(k, "").strip() for k in DRYAD_CRED_ENV)
    if cid and sec:
        where = f"${DRYAD_CRED_ENV[0]}/${DRYAD_CRED_ENV[1]}"
        _reject_placeholders(cid, sec, where)
        return cid, sec, where

    for raw in DRYAD_CRED_FILES:
        p = Path(raw).expanduser()
        if not p.is_file():
            continue
        mode = p.stat().st_mode & 0o777
        if mode & 0o077:
            raise RuntimeError(
                f"{p} holds a Dryad client secret and is mode {mode:04o} — "
                f"readable by someone other than you. Refusing to read it. "
                f"Fix with: chmod 600 {p}")
        try:
            blob = json.loads(p.read_text())
        except Exception as exc:  # noqa: BLE001
            # Deliberately does not echo the file's contents: a malformed
            # credentials file is still a credentials file.
            raise RuntimeError(
                f"{p} is not readable as JSON ({type(exc).__name__}). Expected "
                f'{{"client_id": "...", "client_secret": "..."}}') from exc
        cid = str(blob.get("client_id") or "").strip()
        sec = str(blob.get("client_secret") or "").strip()
        if cid and sec:
            _reject_placeholders(cid, sec, str(p))
            return cid, sec, str(p)
        raise RuntimeError(
            f"{p} parsed but is missing "
            f"{'client_id' if not cid else 'client_secret'}.")
    return None


def _token_exchange(client_id: str, secret: str, basic: bool) -> dict:
    """POST client credentials to Dryad's token endpoint. Body, never the URL.

    Credentials in a query string end up in server logs, in proxy logs, and in
    the browser history of whoever pastes the URL later. They go in the request
    body, and under Basic they go in a header.
    """
    data = {"grant_type": "client_credentials"}
    headers = {"User-Agent": UA, "Accept": "application/json",
               "Content-Type": "application/x-www-form-urlencoded"}
    if basic:
        raw = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
        headers["Authorization"] = f"Basic {raw}"
    else:
        data["client_id"] = client_id
        data["client_secret"] = secret
    req = urllib.request.Request(
        DRYAD_TOKEN_URL, data=urllib.parse.urlencode(data).encode(),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def dryad_token(exchange=None, now=None, required: bool = True) -> str | None:
    """Return a bearer token for Dryad, or raise saying exactly how to get one.

    Cached in-process against `expires_in`, with a minute of slack, because a
    deposit is many files and a token exchange per file would be both slow and
    rude. `exchange` and `now` are injectable so the fixtures can exercise
    expiry, both credential forms and both failure shapes without a network.

    Dryad's own documentation shows the credentials in the form body. Some
    OAuth2 servers want them under HTTP Basic instead, and which one Dryad
    accepts has not been observed here, so a 400/401 on the documented form is
    retried under Basic. If both fail, the error names both attempts rather than
    reporting only the second — otherwise a wrong client id would read as an
    unsupported auth style.
    """
    exchange = exchange or _token_exchange
    clock = now or time.time

    if _DRYAD_TOKEN["value"] and clock() < _DRYAD_TOKEN["expires_at"]:
        return _DRYAD_TOKEN["value"]  # type: ignore[return-value]

    creds = dryad_credentials()
    if creds is None:
        if not required:
            return None
        raise RuntimeError(DRYAD_NO_CREDENTIALS)
    cid, sec, where = creds

    attempts: list[str] = []
    payload = None
    for basic in (False, True):
        style = "HTTP Basic" if basic else "form body (as documented)"
        try:
            payload = exchange(cid, sec, basic)
            break
        except Exception as exc:  # noqa: BLE001
            detail = _redact(f"{type(exc).__name__}: {exc}", sec, cid)
            attempts.append(f"{style} -> {detail}")
    if payload is None:
        raise RuntimeError(
            "Dryad refused the client credentials from " + where + ". Both "
            "supported forms were tried:\n  " + "\n  ".join(attempts) +
            "\nIf the id and secret are right, the account may not be active "
            "yet — Dryad requires one ORCID sign-in before the API account "
            "works.")

    tok = str(payload.get("access_token") or "").strip()
    if not tok:
        # A 200 with no token is the shape that would otherwise become
        # `Authorization: Bearer None` and come back as the same 401 we are
        # here to fix, one layer further from the cause.
        raise RuntimeError(
            f"Dryad's token endpoint answered without an access_token "
            f"(keys: {sorted(payload.keys())}). Nothing to send.")
    try:
        ttl = float(payload.get("expires_in") or 0)
    except (TypeError, ValueError):
        ttl = 0.0
    _DRYAD_TOKEN["value"] = tok
    _DRYAD_TOKEN["expires_at"] = clock() + max(ttl - 60.0, 0.0)
    return tok


def download(url: str, dest: Path, expect_bytes: int | None = None,
             token: str | None = None) -> None:
    """Fetch url -> dest with resume. Raises on failure.

    `token`, when given, is sent as an `Authorization: Bearer` header. It is
    passed to curl through a `-K` config file rather than on the command line,
    because argv is world-readable on a shared machine: anyone running `ps` while
    a 4.9 GB transfer is in progress would otherwise be able to read the
    credential. The file is created 0600 and removed in a `finally`.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    if HAVE_CURL:
        base = ["curl", "-L", "--fail", "--retry", "5", "--retry-delay", "3",
                "--connect-timeout", "30"]
        if RETRY_ALL:
            base.append("--retry-all-errors")
        cfg: Path | None = None
        try:
            if token:
                fd_, name = tempfile.mkstemp(prefix="dryad-auth-", suffix=".conf")
                cfg = Path(name)
                os.fchmod(fd_, 0o600)
                with os.fdopen(fd_, "w") as fh:
                    fh.write(f'header = "Authorization: Bearer {token}"\n')
                base += ["-K", str(cfg)]
            tail = ["-A", UA, "-o", str(part), url]
            rc = subprocess.call(base + ["-C", "-"] + tail)
            # curl exits 33 when the server refuses range requests; restart clean
            if rc == 33:
                part.unlink(missing_ok=True)
                rc = subprocess.call(base + tail)
        finally:
            if cfg is not None:
                cfg.unlink(missing_ok=True)
        if rc != 0:
            raise RuntimeError(f"curl exited {rc} for {url}")
    else:
        headers = {"User-Agent": UA}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as r, part.open("wb") as fh:
            shutil.copyfileobj(r, fh, 1 << 20)

    if expect_bytes and part.stat().st_size != expect_bytes:
        raise RuntimeError(
            f"size mismatch for {dest.name}: got {part.stat().st_size:,}, expected {expect_bytes:,}"
        )
    part.replace(dest)


MAX_UNZIP_DEPTH = 4
ARCHIVE_SUFFIXES = {".zip"}


def is_apple_double(p: Path) -> bool:
    """macOS resource-fork shadows: `__MACOSX/._behavior.csv` and friends.

    They are named exactly like the real files and are binary, so any rule that
    picks a file by name or by suffix will happily pick one of these instead.
    """
    return p.name.startswith("._") or "__MACOSX" in p.parts


def _within(child: Path, parent: Path) -> bool:
    """True if `child` is `parent` or lies underneath it.

    The previous test was `str(target).startswith(str(into.resolve()))`, which
    compares characters and not path components: `/data/raw/mersch_evil` starts
    with `/data/raw/mersch` and would have been accepted as inside it. Asking
    `relative_to` does the same check on components, where it belongs.
    """
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def archives_under(root: Path) -> list[Path]:
    """Every real zip in the tree, AppleDouble shadows excluded."""
    out = []
    for p in sorted(root.rglob("*")):
        try:
            if not p.is_file() or is_apple_double(p):
                continue
            if p.suffix.lower() in ARCHIVE_SUFFIXES and zipfile.is_zipfile(p):
                out.append(p)
        except OSError:
            continue
    return out


def unzipped_marker(arc: Path) -> Path:
    return arc.parent / (".unzipped_" + arc.name)


def _extract_one(arc: Path, dest: Path) -> str:
    """Extract one archive. Returns 'extracted', 'already', or 'notzip'."""
    if not zipfile.is_zipfile(arc):
        return "notzip"
    marker = unzipped_marker(arc)
    if marker.exists():
        return "already"
    say(f"    unpacking {arc.name} ...")
    root = dest.resolve()
    with zipfile.ZipFile(arc) as z:
        for member in z.namelist():
            # refuse absolute paths and traversal
            if not _within((dest / member).resolve(), root):
                raise RuntimeError(f"unsafe path in archive {arc.name}: {member}")
        z.extractall(dest)
    marker.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
    return "extracted"


def unzip(path: Path, into: Path) -> list[Path]:
    """Extract `path` into `into` -- and then extract whatever that produced.

    This used to stop after one level, and that single missing level is the
    difference between the run's tally and the truth. The Dryad bundle for
    Mersch expands to a `tracking_data.zip` and nothing else usable; the folder
    was then non-empty, the manifest said complete, the summary line said "2/2
    datasets complete", and every one of those statements was about DOWNLOADING.
    A loader pointed at the folder days later found one binary file it could not
    open. "Complete" has to mean readable or it is not worth printing.

    Two details matter for re-runs. Recursion continues through an archive whose
    marker already exists ('already', not 'notzip'), because the outer zip having
    been expanded on a previous run says nothing about the inner one -- skipping
    there is exactly how a resumed run would inherit the original bug. And a
    resolved path is only visited once, so an archive that somehow contains
    itself cannot spin.

    Returns the archives that were expanded or found already expanded, so the
    caller can say how deep it actually went.
    """
    done: list[Path] = []
    queue: list[tuple[Path, Path, int]] = [(path, into, 0)]
    seen: set[Path] = set()
    while queue:
        arc, dest, depth = queue.pop(0)
        key = arc.resolve()
        if key in seen:
            continue
        seen.add(key)
        if _extract_one(arc, dest) == "notzip":
            continue
        done.append(arc)
        if depth + 1 > MAX_UNZIP_DEPTH:
            say(f"    NOTE: stopping at nesting depth {MAX_UNZIP_DEPTH}; archives "
                f"under {dest.name}/ are still packed. This is a guard against a "
                "pathological archive, not a normal outcome -- report it.")
            continue
        for nested in archives_under(dest):
            if nested.resolve() not in seen:
                queue.append((nested, nested.parent, depth + 1))
    if len(done) > 1:
        say(f"    expanded {len(done)} archives (nested): "
            + ", ".join(p.name for p in done))
    return done


# ------------------------------------------------------------------ resolvers
def zenodo_files(record: str) -> tuple[list[dict], dict]:
    """Return (files, meta) for a Zenodo record id or concept id."""
    rec = get_json(f"https://zenodo.org/api/records/{record}")

    # Zenodo has shipped three shapes of this field over the years: a list, a
    # dict with "entries", and a bare link to a separate files endpoint. Handle
    # all three rather than assuming whichever one is live today.
    raw_files = rec.get("files")
    if isinstance(raw_files, dict):
        entries = raw_files.get("entries")
        raw_files = list(entries.values()) if isinstance(entries, dict) else (entries or [])
    if not raw_files:
        try:
            raw_files = get_json(f"https://zenodo.org/api/records/{record}/files").get("entries", [])
        except Exception:  # noqa: BLE001
            raw_files = []

    files = []
    for f in raw_files or []:
        name = f.get("key") or f.get("filename")
        if not name:
            continue
        links = f.get("links") or {}
        link = (links.get("content") or links.get("self") or links.get("download")
                or f"https://zenodo.org/records/{record}/files/"
                   f"{urllib.parse.quote(name)}?download=1")
        # Zenodo writes this as "<algo>:<hex>", and the algo is md5 today but is
        # part of the string rather than an assumption we get to make.
        raw_sum = (f.get("checksum") or "").strip()
        algo, _, hexd = raw_sum.rpartition(":")
        files.append(dict(name=safe_member_name(name), url=link, size=f.get("size"),
                          digest=hexd or None, digest_type=(algo or "md5") if hexd else None))
    if not files:
        raise RuntimeError(
            f"Zenodo record {record} returned no downloadable files. Open "
            f"https://zenodo.org/records/{record} in a browser and check whether "
            "access is restricted.")
    meta = dict(
        title=(rec.get("metadata") or {}).get("title") or rec.get("title"),
        doi=rec.get("doi"),
        license=((rec.get("metadata") or {}).get("license") or {}).get("id"),
    )
    return files, meta


DRYAD = "https://datadryad.org"

# Twenty entries a page is what Dryad serves, so this allows a 4,000-file
# deposit. Nothing in `sources.py` is remotely that large; the constant exists to
# bound the paging loop, not to express an expectation.
MAX_LISTING_PAGES = 200


def dryad_slug(doi: str) -> str:
    return doi.split("/")[-1].replace(".", "_")


def safe_member_name(raw: str) -> str:
    """A repository-supplied filename, reduced to something safe to join.

    The name comes from a remote service and is about to become a path we write
    to. `Path(raw).name` strips any directory component, and the checks below
    refuse the three strings that survive that strip and are still not
    filenames. This raises rather than sanitising quietly, because a deposit
    whose file is called `../something` is a deposit we should look at by hand.
    """
    name = Path(str(raw)).name.strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise RuntimeError(f"unusable filename from repository: {raw!r}")
    return name


def dryad_files(doi: str, allow_bundle: bool = False,
                fetch=None) -> tuple[list[dict], dict]:
    """Resolve a Dryad DOI to its individual files.

    Two wrong explanations, both withdrawn, and then the measurement
    ----------------------------------------------------------------
    Until 31 July 2026 this function returned one entry pointing at
    `/api/v2/versions/{id}/download`. It failed on `alciatore_2021` leaving zero
    bytes, and two successive versions of this docstring explained why. Both
    explanations were wrong, and both were wrong the same way: inferred from an
    exit code and written down as though observed.

    **First (v2.13, withdrawn in v2.15):** *"it asks Dryad to build a zip of the
    entire deposit on the fly … it reset partway through (curl exit 56, 'failure
    receiving network data') … a generated archive has no stable byte offsets and
    does not honour range requests."* Never observed. The curl progress lines
    from that run were never read; only the exit code was.

    **Second (v2.15, withdrawn here in v2.16):** that a 401 accounts for it,
    because every per-file download on 31 July failed with `The requested URL
    returned error: 401`, transferring exactly 56 bytes — the length of
    `{"error":"Unauthorized, must have current bearer token"}` — and *"the bundle
    endpoint is a file download."* That last clause was the inference, and it is
    false.

    **What was actually measured, 31 July 2026, 17:38:06 GMT by Dryad's own
    `Date:` header — and the server simply says why:**

        GET https://datadryad.org/api/v2/versions/144593/download
        -> HTTP/2 405, content-type: text/plain; charset=utf-8,
           content-length: 89, server: Apache/2.4.68 (Amazon Linux)
           no Allow: header
        body, all 89 bytes of it, matching content-length exactly:
        "The dataset is too large for zip file generation. Please download each
         file individually."

    That closes it, and it is worth being exact about what it does and does not
    say about the two withdrawn explanations.

      * **The premise of the first was right and its mechanism was wrong.** Dryad
        does generate these zips on demand — "zip file generation" is Dryad's own
        phrase. It did not reset partway through; it declined to start. Nothing
        about stable byte offsets or range requests was ever in play, because no
        archive was ever built. Being right about the premise is not being right:
        the claim that shipped was the mechanism.
      * **The second is dead outright.** A 401 played no part. The bundle route is
        not gated on a bearer token; it is gated on deposit size.
      * **This is a size-conditional refusal, not a property of the route.** The
        405 carries no `Allow:` header, so it is Dryad reusing a status code for
        an application-level "no", not method semantics. `alciatore_2021` is
        4,894,343,349 bytes and is over whatever the threshold is;
        `richardson_2021` is 390,749,381 and **has not been tested**. Do not write
        down that the bundle endpoint never serves a GET — that would be the same
        over-generalisation from one observation, a fourth time.

    A coincidence worth naming, because it looks like corroboration:
    **curl's exit code 56 and the 401 body's `content-length: 56` are the same
    number and have nothing to do with each other.** Exit 56 is "failure receiving
    network data"; 56 bytes is the length of a JSON string. The v2.15 reasoning
    used the byte count, which was sound, but the pair of 56s reads like two
    independent facts agreeing, and it is one number twice.

    Why per-file rather than the version bundle
    -------------------------------------------
    The per-file case does not depend on any of the above and survives all of it.
    `/api/v2/versions/{id}/files` lists the deposit's real, stored files, each
    with a published byte size and a sha-256. Two properties follow that the
    bundle cannot have however it is generated: a partial transfer can be
    checked against a number the repository published rather than against hope,
    and a failure costs one file rather than the whole deposit. Those are
    reasons to prefer per-file that do not rest on anything unobserved.

    And the repository now says the same thing in its own words. "Please download
    each file individually" is the instruction returned by the endpoint this
    function stopped using in v2.13, arrived at there for different reasons. The
    per-file route is not a workaround; it is the supported one for a deposit this
    size.

    `--dryad-bundle` is therefore kept but cannot help with `alciatore_2021`
    (v2.16, refined v2.17): it builds `{version_href}/download` and issues the GET
    that Dryad refuses on size. For a deposit under the threshold it may still
    work, which is why the flag survives and why its message quotes Dryad's
    sentence rather than asserting that the route is dead.

    The listing is paginated (v2.14)
    -------------------------------
    Twenty entries a page. v2.13 read page one and treated it as the deposit,
    which for `richardson_2021` meant 20 files of 47 and 115.3 MB of 372.6 MB.
    That failure is quieter than the one it replaced: every file it found was
    genuine and would have passed its own checksum. Two gates now stand between
    a page and a claim of completeness — the `total` the listing publishes, and
    the `storageSize` the *dataset* document publishes, which is an independent
    number rather than a restatement.

    `fetch` is the JSON getter, injectable so the fixtures can exercise every
    branch of this function without a network. `allow_bundle` re-enables the old
    behaviour and is off by default: if the per-file listing is unusable we
    raise and name the flag, rather than falling back to a 4.9 GB stream the
    caller did not ask for.
    """
    fetch = fetch or get_json
    enc = urllib.parse.quote(f"doi:{doi}", safe="")
    ds = fetch(f"{DRYAD}/api/v2/datasets/{enc}")
    links = ds.get("_links", {}) or {}

    version_href = None
    for key in ("stash:version", "stash:versions", "self"):
        href = (links.get(key) or {}).get("href", "")
        if "/versions/" in href:
            version_href = href
            break
    if version_href is None:
        # fall back: list versions and take the last
        vs = fetch(f"{DRYAD}/api/v2/datasets/{enc}/versions")
        embedded = (vs.get("_embedded") or {}).get("stash:versions") or []
        if embedded:
            version_href = ((embedded[-1].get("_links") or {}).get("self") or {}).get("href")
    if version_href is None:
        raise RuntimeError(f"could not locate a version for Dryad {doi}")

    version_href = version_href.rstrip("/")
    meta = dict(title=ds.get("title"), doi=doi, license=ds.get("license"),
                version_href=version_href)

    # Dryad paginates this listing at twenty entries a page, and says so twice:
    # in the top-level `total`, and in `_links.next`. v2.13 read page one and
    # stopped. For `richardson_2021` that is 20 of 47 files -- 115.3 MB of a
    # 372.6 MB deposit -- and it did not look like an error, because those 20
    # files are real, carry real sha-256s, and would have downloaded and
    # verified cleanly. A deposit that arrives 40% present is worse than one
    # that fails outright, because the loaders will run on it and produce
    # numbers. The two gates below the loop are what make truncation loud:
    # `len(files) == total`, and the summed bytes against `storageSize`.
    listing: dict = {}
    listing_error: str | None = None
    pages: list[dict] = []
    reported_total: int | None = None
    seen_hrefs: set[str] = set()
    next_href: str | None = f"{version_href}/files"

    while next_href:
        if next_href in seen_hrefs:
            raise RuntimeError(
                f"Dryad {doi}: the listing's `next` link points back at "
                f"{next_href}, which has already been read. Refusing to loop.")
        if len(pages) >= MAX_LISTING_PAGES:
            raise RuntimeError(
                f"Dryad {doi}: the file listing still offers a `next` page after "
                f"{MAX_LISTING_PAGES} of them. That is past anything this project "
                f"expects of a deposit, so it is being read as a paging bug rather "
                f"than a large dataset. Raise MAX_LISTING_PAGES if it is real.")
        seen_hrefs.add(next_href)
        try:
            page = fetch(f"{DRYAD}{next_href}")
        except Exception as exc:  # noqa: BLE001
            # Page one failing leaves us with nothing, which the bundle branch
            # below can speak to. Page four failing leaves us with three pages of
            # a deposit -- the truncation case again, in a different hat -- so it
            # raises here rather than returning whatever arrived.
            detail = f"{type(exc).__name__}: {exc}"
            if pages:
                raise RuntimeError(
                    f"Dryad {doi}: read {len(pages)} page(s) of the file listing "
                    f"and then failed on {next_href} — {detail}. Refusing to "
                    f"return a partial enumeration.") from exc
            listing_error = detail
            break
        pages.append(page)
        if reported_total is None and isinstance(page.get("total"), int):
            reported_total = page["total"]
        next_href = ((page.get("_links") or {}).get("next") or {}).get("href") or None

    listing = pages[0] if pages else {}
    raw = [e for p in pages
           for e in ((p.get("_embedded") or {}).get("stash:files") or [])]
    files = []
    for entry in raw:
        name = safe_member_name(entry.get("path") or "")
        href = ((entry.get("_links") or {}).get("stash:download") or {}).get("href")
        if not href:
            # Not skippable. A file we cannot address is a hole in the deposit,
            # and returning the rest would look like a complete download.
            raise RuntimeError(
                f"Dryad {doi}: file {name!r} has no stash:download link. "
                f"Its _links were {sorted((entry.get('_links') or {}).keys())}.")
        algo = entry.get("digestType")
        digest = entry.get("digest")
        files.append(dict(
            name=name,
            url=href if href.startswith("http") else f"{DRYAD}{href}",
            size=entry.get("size"),
            digest=digest or None,
            digest_type=algo or None,
            status=entry.get("status"),
        ))

    # ---- gate one: the count the listing itself published --------------------
    # This is the cheapest possible check and it is exact: Dryad tells us how
    # many files the version has, in the same document that hands us some of
    # them. Comparing the two costs nothing and is the difference between "we
    # have the deposit" and "we have page one of the deposit".
    if reported_total is not None and files and len(files) != reported_total:
        raise RuntimeError(
            f"Dryad {doi}: enumerated {len(files)} file(s) across "
            f"{len(pages)} page(s), but the listing says this version has "
            f"{reported_total}. Refusing to hand back a partial deposit — "
            f"downloading it would succeed, verify, and be wrong.")

    # ---- gate two: an independent witness, the deposit's own byte count ------
    # `storageSize` comes from the dataset document, not the file listing, so it
    # is not a restatement of gate one — it can only agree by both being right.
    # On the two deposits where the answer is known it agrees to the byte
    # (alciatore 4,894,312,027 + 31,322 = 4,894,343,349). If it ever disagrees
    # while gate one passes, something we believe about Dryad is wrong, and that
    # is exactly the moment to stop rather than to widen a tolerance.
    storage = ds.get("storageSize")
    sizes = [f.get("size") for f in files]
    resolved = sum(s for s in sizes if isinstance(s, int))
    meta["storage_size"] = storage if isinstance(storage, int) else None
    meta["resolved_bytes"] = resolved
    if (files and isinstance(storage, int) and storage > 0
            and all(isinstance(s, int) for s in sizes) and resolved != storage):
        raise RuntimeError(
            f"Dryad {doi}: the {len(files)} file(s) listed sum to {resolved:,} "
            f"bytes but the deposit reports storageSize {storage:,} — a "
            f"difference of {abs(storage - resolved):,}. Gate one passed, so "
            f"this is not simple pagination. Look at the deposit by hand before "
            f"downloading it.")

    if files:
        return files, meta

    why = listing_error or (
        f"the listing parsed but carried no _embedded['stash:files'] "
        f"(top-level keys: {sorted(listing.keys())})")
    if not allow_bundle:
        raise RuntimeError(
            f"Dryad {doi}: could not enumerate the deposit's files — {why}. "
            f"Refusing to fall back to {version_href}/download. On 31 July 2026 a "
            f"GET on the 4.9 GB alciatore_2021 bundle answered HTTP 405 with "
            f"\"The dataset is too large for zip file generation. Please download "
            f"each file individually.\" — and even where it does serve, it "
            f"publishes neither a size nor a checksum, so a partial arrival could "
            f"not be detected. Pass --dryad-bundle to try it anyway.")

    say(f"    !! per-file listing unusable ({why})")
    say(f"    !! falling back to the generated bundle because --dryad-bundle "
        f"was passed. Dryad generates this zip on demand and refuses above some "
        f"size — 4.9 GB got HTTP 405, \"too large for zip file generation\". If "
        f"it does serve, it publishes no size and no checksum, so nothing here "
        f"can tell a complete arrival from a truncated one.")
    return ([dict(name=f"dryad_{dryad_slug(doi)}.zip",
                  url=f"{DRYAD}{version_href}/download",
                  size=None, digest=None, digest_type=None,
                  status="generated-bundle")], meta)


def _git_env() -> dict:
    """Make git fail fast instead of blocking on a credential prompt.

    Without this, a private or missing repository stops the whole run at an
    interactive "Username for 'https://github.com':" prompt, and on a
    non-interactive terminal it produces the misleading "Device not configured".
    With these set, git exits non-zero immediately and we can report the truth:
    the repository is not publicly readable.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["SSH_ASKPASS"] = ""
    env["GCM_INTERACTIVE"] = "never"
    return env


def git_clone(url: str, into: Path) -> None:
    """Clone or update `url` into `into`. Raises RuntimeError on failure.

    Raising rather than returning False is deliberate: the caller counts
    exceptions, so a silent False was being tallied as a success.

    One asymmetry is intentional. A failed CLONE is a failure -- nothing arrived.
    A failed PULL on a repository that is already on disk is not: the content is
    there, only the refresh did not happen. Treating a stale copy as a missing
    one would be the same over-reporting bug in the opposite direction, and it
    would stop the manifest being repaired on a machine that happens to be
    offline.
    """
    if not shutil.which("git"):
        raise RuntimeError("git not found on PATH (install the Xcode command line tools: "
                           "xcode-select --install)")
    env = _git_env()
    if (into / ".git").exists():
        say("    already cloned; pulling")
        rc = subprocess.call(["git", "-C", str(into), "pull", "--ff-only"], env=env)
        if rc != 0:
            say(f"    (pull exited {rc}; keeping the copy already on disk)")
        return
    into.parent.mkdir(parents=True, exist_ok=True)
    # --single-branch --no-tags keeps the clone to one branch's tip. It does not
    # shrink a repo whose working tree is genuinely large (btools carries big
    # res/ assets), but it removes everything that is merely history.
    cmd = ["git", "clone", "--depth", "1", "--single-branch", "--no-tags", url, str(into)]
    rc = subprocess.call(cmd, env=env)
    if rc != 0:
        # leave no half-cloned directory behind to confuse the next run
        if into.exists() and not (into / ".git").exists():
            shutil.rmtree(into, ignore_errors=True)
        raise RuntimeError(
            f"git clone failed (exit {rc}) for {url} — the usual cause is that the "
            "repository is private or does not exist; GitHub returns 404 to "
            "unauthenticated clients in both cases")


# ------------------------------------------------------------------- pending
def wrap_note(text: str, width: int = 74) -> list[str]:
    import textwrap
    return textwrap.wrap(" ".join(text.split()), width) or [""]


def write_request(out: Path, s: dict) -> Path:
    """Leave a note in the dataset folder saying who to ask and for what.

    A dataset that has been identified, justified and located but is not yet
    public is not a failure and not a gap in the plan -- it is an outstanding
    request. Recording it as such means the folder is not silently empty six
    months from now.
    """
    out.mkdir(parents=True, exist_ok=True)
    p = out / "REQUEST.txt"
    lines = [
        s["title"], "=" * min(len(s["title"]), 74), "",
        "STATUS: not publicly available at the time of this run "
        f"({time.strftime('%Y-%m-%d')}).", "",
    ]
    if s.get("blocked"):
        lines += wrap_note(s["blocked"]) + [""]
    if s.get("url"):
        lines += [f"Expected location: {s['url']}"]
    if s.get("doi"):
        lines += [f"Paper DOI:         {s['doi']}"]
    if s.get("preprint"):
        lines += [f"Preprint:          https://doi.org/{s['preprint']}"]
    if s.get("contact"):
        lines += [f"Ask:               {s['contact']}"]
    lines += ["", "Citation: " + str(s.get("cite")), "",
              "Why we want it:"] + wrap_note(str(s.get("why", "")))
    lines += ["", "Re-run fetch_data.py once it is available; nothing else needs changing."]
    p.write_text("\n".join(lines) + "\n")
    return p


# ----------------------------------------------------------------- manifest
def dir_bytes(path: Path) -> tuple[int, int]:
    """Recursive (total bytes, file count) for a directory.

    `Path.stat().st_size` on a directory returns the inode size -- 320 bytes for
    a 582 MB clone -- which made the manifest under-report cloned repositories by
    six orders of magnitude. Symlinks are counted as links, not followed, so a
    cyclic tree cannot spin forever.
    """
    total = count = 0
    for p in path.rglob("*"):
        try:
            if p.is_symlink() or not p.is_file():
                continue
            total += p.stat().st_size
            count += 1
        except OSError:
            continue
    return total, count


def path_bytes(path: Path) -> int | None:
    if not path.exists():
        return None
    if path.is_dir():
        return dir_bytes(path)[0]
    return path.stat().st_size


def file_matches(target: Path, f: dict, log=say) -> bool:
    """Is the file already on disk the file the repository is offering?

    Returns False when we cannot tell, never True. A size that matches and a
    checksum we are unable to compute is not a match — it is an unchecked file,
    and the honest response is to fetch it, because the alternative is adopting
    a truncated download because it happened to stop at a plausible length.
    """
    if not target.is_file():
        return False
    size = f.get("size")
    if size is None or target.stat().st_size != size:
        return False
    want, algo = f.get("digest"), f.get("digest_type")
    if not want:
        return False
    got = digest_of(target, algo)
    if got is None:
        log(f"    {target.name} is on disk at the published size, but {algo!r} "
            f"is not computable here, so it counts as unverified.")
        return False
    return got == want


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {"entries": {}}

    def done(self, key: str, name: str, size: int | None, digest: str | None) -> bool:
        """True only if this file is recorded complete *and* the recorded digest
        matches the one the repository publishes now.

        `md5` is read as a synonym for `digest` so manifests written before
        v2.13 still satisfy this. An entry with no digest of any kind is
        accepted when the caller has nothing to compare against and refused when
        it does — in the latter case the file is not re-downloaded blindly, it
        is re-hashed on disk first. See the fetch loop.
        """
        e = self.data["entries"].get(f"{key}/{name}")
        if not (e and e.get("complete")):
            return False
        if digest is None:
            return True
        return (e.get("digest") or e.get("md5")) == digest

    def record(self, key: str, name: str, url: str, path: Path, digest: str | None,
               src: dict, status: str = "complete", note: str | None = None,
               digest_type: str | None = None) -> None:
        entry = dict(
            dataset=key, file=name, url=url,
            local_path=str(path), bytes=path_bytes(path),
            digest=digest, digest_type=digest_type,
            status=status, complete=(status == "complete"),
            citation=src.get("cite"), license=src.get("license"),
            why=src.get("why"),
            fetched=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        if path.exists() and path.is_dir():
            n_files = dir_bytes(path)[1]
            entry["kind"] = "directory"
            entry["n_files"] = n_files
            entry["bytes_note"] = f"recursive total over {n_files:,} files, not the directory inode"
        if note:
            entry["note"] = note
        self.data["entries"][f"{key}/{name}"] = entry
        self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2))


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", help="drive or directory to hold the project (default: auto-detect)")
    ap.add_argument("--tier", default="main", choices=["core", "main", "full"])
    ap.add_argument("--only", nargs="*", help="restrict to these dataset keys")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-unzip", action="store_true")
    ap.add_argument("--dryad-bundle", action="store_true",
                    help="if a Dryad deposit's per-file listing is unusable, fall back "
                         "to the version-level zip, which Dryad generates on demand. "
                         "Off by default. It cannot work for a large deposit — 4.9 GB "
                         "answered HTTP 405, 'too large for zip file generation, "
                         "please download each file individually' — and where it does "
                         "serve it publishes no size and no checksum, so a truncated "
                         "arrival is undetectable.")
    ap.add_argument("--no-install-code", action="store_true",
                    help="do not copy this code folder into <project>/code")
    ap.add_argument("--no-git", action="store_true",
                    help="skip git repositories (btools alone is ~580 MB of source)")
    args = ap.parse_args()

    say(f"fetch_data.py v{VERSION}  ({Path(__file__).resolve()})")
    dest = resolve_dest(args.dest)
    base = make_tree(dest)
    raw = base / "data" / "raw"
    say(f"\nProject root: {base}")
    if not args.no_install_code and not args.dry_run:
        try:
            install_code(base)
        except Exception as exc:  # noqa: BLE001
            say(f"(could not copy the code onto the drive: {exc})")

    chosen = select(args.tier)
    if args.only:
        chosen = [s for s in chosen if s["key"] in set(args.only)]
        if not chosen:
            raise SystemExit("--only matched nothing")

    planned = sum(s.get("approx_bytes") or 0 for s in chosen)
    try:
        free = shutil.disk_usage(base).free
    except OSError:
        free = None

    say(f"\nTier {args.tier!r}: {len(chosen)} datasets, roughly {human(planned)}")
    for s in chosen:
        say(f"  - {s['key']:28} {human(s.get('approx_bytes')):>10}   {s['title'][:70]}")
    if free is not None:
        say(f"\nFree space on destination: {human(free)}")
        if planned and free < planned * 1.25:
            say("WARNING: less than 125% of the planned volume is free. Downloads may fail part-way.")
            say("         (Re-running the script resumes, so this is recoverable.)")
    if args.dry_run:
        say("\nDry run - nothing downloaded.")
        return 0

    # Preflight, not a gate. Dryad downloads need a token, but the adoption path
    # does not, so a run with no credentials can still finish a deposit that was
    # fetched in a browser. Saying it here rather than only at the first download
    # means the user reads it before a long run instead of forty minutes in.
    if any(s["kind"] == "dryad" for s in chosen):
        try:
            has_creds = dryad_credentials() is not None
        except Exception as exc:  # noqa: BLE001
            has_creds = False
            say(f"\nWARNING: Dryad credentials present but unusable — {exc}")
        if not has_creds:
            n = sum(1 for s in chosen if s["kind"] == "dryad")
            say(f"\nNOTE: {n} of the {len(chosen)} selected dataset(s) "
                f"{'is' if n == 1 else 'are'} on Dryad, and no Dryad API "
                f"credentials were found.")
            say("      Anything already on disk at the published size and sha-256 "
                "will still be adopted and recorded.")
            say("      Anything that has to be fetched will stop with instructions.")

    man = Manifest(base / "MANIFEST.json")
    failures: list[str] = []
    pending: list[str] = []
    skipped: list[str] = []

    for s in chosen:
        key, kind = s["key"], s["kind"]
        say(f"\n=== {key} ===")
        say(f"    {s['title']}")
        out = raw / key
        out.mkdir(parents=True, exist_ok=True)
        (out / "SOURCE.txt").write_text(
            f"{s['title']}\n\nCitation: {s.get('cite')}\nLicense: {s.get('license')}\n"
            f"Why we want it: {s.get('why')}\n"
        )

        try:
            if kind == "pending":
                write_request(out, s)
                say("    NOT PUBLICLY AVAILABLE — see REQUEST.txt in this folder.")
                for line in wrap_note(s.get("blocked", "")):
                    say(f"    {line}")
                man.record(key, "REQUEST.txt", s.get("url", ""), out / "REQUEST.txt",
                           None, s, status="pending", note=s.get("blocked"))
                pending.append(f"{key}: {s.get('contact') or 'contact the authors'}")
                continue

            if kind == "git":
                if args.no_git:
                    say("    skipped (--no-git)")
                    skipped.append(f"{key}: --no-git")
                    continue
                repo = out / "repo"
                git_clone(s["url"], repo)
                nbytes, nfiles = dir_bytes(repo)
                say(f"    cloned: {human(nbytes)} across {nfiles:,} files")
                man.record(key, "repo", s["url"], repo, None, s)
                continue

            if kind == "zenodo":
                files, meta = zenodo_files(s["record"])
                say(f"    resolved {len(files)} file(s) from Zenodo {s['record']}")
            elif kind == "dryad":
                # A deposit fetched by the pre-2.13 bundle path is on disk under
                # a name this version no longer asks for. Re-fetching it per file
                # would download the same bytes a second time under new names, so
                # say what is there and leave it alone.
                legacy = out / f"dryad_{dryad_slug(s['doi'])}.zip"
                if legacy.exists() and legacy.stat().st_size > 0:
                    say(f"    a bundle from the pre-2.13 fetcher is already here: "
                        f"{legacy.name} ({human(legacy.stat().st_size)}).")
                    say(f"    Leaving it and skipping the per-file fetch. Delete it "
                        f"and re-run if you want the files fetched individually.")
                    if not args.no_unzip:
                        unzip(legacy, out)
                    continue
                files, meta = dryad_files(s["doi"], allow_bundle=args.dryad_bundle)
                total = sum(f["size"] for f in files if f.get("size"))
                say(f"    resolved {len(files)} file(s) from Dryad {s['doi']}"
                    + (f", {human(total)} in total" if total else ""))
            elif kind == "direct":
                files = [dict(name=safe_member_name(u.rsplit("/", 1)[-1]), url=u,
                              size=None, digest=None, digest_type=None)
                         for u in s["urls"]]
                meta = {}
            else:
                raise RuntimeError(f"unknown kind {kind}")

            (out / "RESOLVED.json").write_text(json.dumps({"meta": meta, "files": files}, indent=2))

            # Acquired at the first file that actually needs fetching, not at
            # the top of the dataset: a deposit whose files are all on disk is
            # completed without a token, and asking for one first would turn a
            # working offline path into a hard requirement.
            tok: str | None = None

            for f in files:
                target = out / f["name"]
                want, algo = f.get("digest"), f.get("digest_type")
                if man.done(key, f["name"], f.get("size"), want) and target.exists():
                    say(f"    [skip]  {f['name']}")
                elif target.exists() and file_matches(target, f, say):
                    # On disk, right size, right checksum, but the manifest does
                    # not say so -- an interrupted run, or a rename between
                    # versions. Adopt it rather than re-fetching gigabytes to
                    # confirm what we can confirm locally in seconds.
                    say(f"    [have]  {f['name']}  (on disk and verified; recording it)")
                    man.record(key, f["name"], f["url"], target, want, s,
                               digest_type=algo)
                else:
                    if kind == "dryad" and tok is None:
                        tok = dryad_token()
                    say(f"    [get ]  {f['name']}  ({human(f.get('size'))})")
                    download(f["url"], target, f.get("size"), token=tok)
                    if want:
                        got = digest_of(target, algo)
                        if got is None:
                            say(f"    !! {f['name']} arrived at the published size but "
                                f"went UNVERIFIED: repository publishes {algo!r}, which "
                                f"this Python cannot compute.")
                        elif got != want:
                            say(f"    checksum mismatch ({algo}), retrying once: {f['name']}")
                            target.unlink(missing_ok=True)
                            download(f["url"], target, f.get("size"), token=tok)
                            got = digest_of(target, algo)
                            if got != want:
                                raise RuntimeError(
                                    f"{algo} still wrong for {f['name']}: "
                                    f"got {got}, published {want}")
                    else:
                        say(f"    (no checksum published for {f['name']}; "
                            f"size is the only check that ran)")
                    man.record(key, f["name"], f["url"], target,
                               want if want else None, s, digest_type=algo)

                if not args.no_unzip and target.suffix.lower() == ".zip":
                    unzip(target, out)

        except Exception as exc:  # noqa: BLE001
            say(f"    !! FAILED: {exc}")
            failures.append(f"{key}: {exc}")

    say("\n" + "=" * 68)
    accounted = len(failures) + len(pending) + len(skipped)
    ok = len(chosen) - accounted
    say(f"Finished. {ok}/{len(chosen)} datasets complete.")
    if failures:
        # Not "downloads resume". They resume when a partial .part file exists,
        # which is a fact about the individual failure and not something this
        # line can assert. Saying it unconditionally once told the user that a
        # transfer which left zero bytes would pick up where it stopped.
        say(f"{len(failures)} FAILED (re-run to retry; a transfer that left a "
            f".part file continues from it, one that left nothing starts over):")
        for f in failures:
            say(f"  - {f}")
    if pending:
        say(f"{len(pending)} awaiting release — not a failure, but not on disk either:")
        for f in pending:
            say(f"  - {f}   (see data/raw/<key>/REQUEST.txt)")
    if skipped:
        say(f"{len(skipped)} skipped by request:")
        for f in skipped:
            say(f"  - {f}")

    # Independent check: believe the disk, not the counters. If a dataset folder
    # holds nothing but the notes we wrote ourselves, say so, however the run
    # thought it went.
    empties = []
    for s in chosen:
        d = raw / s["key"]
        if not d.exists():
            empties.append(s["key"])
            continue
        payload = [p for p in d.rglob("*")
                   if p.is_file() and p.name not in {"SOURCE.txt", "RESOLVED.json", "REQUEST.txt"}
                   and not p.name.startswith(".unzipped_")]
        if not payload:
            empties.append(s["key"])
    real = [k for k in empties if k not in {p.split(":")[0] for p in pending + skipped}]
    if real:
        say("\nWARNING: these folders contain no data despite the tally above — "
            "this check reads the disk, not the counters:")
        for k in real:
            say(f"  - {k}")

    # The emptiness check above cannot see this one. An archive that arrived but
    # was never expanded IS payload by that test -- the folder is not empty, it
    # just holds a file nothing downstream can open. That is how "2/2 datasets
    # complete" stayed true about downloading and false about readability for the
    # Mersch bundle, whose nested tracking_data.zip sat there unexpanded.
    packed = []
    if not args.no_unzip:
        for s in chosen:
            d = raw / s["key"]
            if not d.exists():
                continue
            for arc in archives_under(d):
                if not unzipped_marker(arc).exists():
                    packed.append(f"{s['key']}: {arc.relative_to(raw)}")
    if packed:
        say("\nWARNING: these archives are on disk but were never expanded, so the "
            "data inside them is not readable yet:")
        for p in packed:
            say(f"  - {p}")
        say("  Re-run this script; expansion is idempotent and resumes.")

    say(f"\nManifest: {base / 'MANIFEST.json'}")
    say(f"Next:     python3 {base / 'code' / 'inspect_data.py'}")
    return 1 if (failures or real or packed) else 0


if __name__ == "__main__":
    sys.exit(main())
