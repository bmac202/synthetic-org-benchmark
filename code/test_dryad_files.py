#!/usr/bin/env python3
"""Fixtures for the Dryad resolver in fetch_data.py, in both polarities.

The claim this file protects is that `dryad_files` enumerates a deposit's real
stored files and refuses when it cannot, rather than quietly handing back the
version-level generated bundle. That claim is only worth something if the
function can fail, so half the fixtures below are listings that must raise.

  parses        a well-formed listing -> two files, real URLs, sizes, sha-256
  paginates     three pages, followed via _links.next -> all five files
  truncated     one page claiming a total of five      -> RAISES
  page_loop     a `next` pointing at a page already read -> RAISES
  mid_listing   page one fine, page two errors          -> RAISES, no partial
  storage_ok    listed bytes == the deposit's storageSize
  storage_mismatch  consistent count, wrong byte total -> RAISES
  no_files      _embedded present, stash:files empty -> RAISES, names the flag
  no_embedded   _embedded absent entirely            -> RAISES
  listing_500   the listing endpoint itself errors   -> RAISES, quotes the error
  no_download   a file with no stash:download link   -> RAISES, does not skip it
  traversal     a file whose path is ../../etc/passwd -> RAISES
  bundle_opt_in the same empty listing with allow_bundle=True -> one bundle entry
  digest_algo   sha-256 is actually computed; an unknown algo returns None
  local_match   file_matches accepts a correct file and refuses every near-miss
  creds         env beats file; a 0644 secret file is refused; a malformed one
                is refused without echoing what it contains
  placeholder   the unedited example one-liner is refused by name, in both the
                file and the environment path, and a real credential is not
  token         form body first, HTTP Basic on retry, both failures named; the
                cache honours expires_in; a 200 with no access_token raises
  argv          the bearer token never reaches curl's command line, travels in
                a 0600 -K file, and that file is gone whether curl succeeds or
                fails
  withdrawal    the docstring still carries both wrong explanations, quotes the
                405 body verbatim rather than paraphrasing it, names the 56/56
                coincidence, and records the refusal as size-conditional

`paginates` and `truncated` are the pair that matters most, because the bug they
describe is silent. Twenty valid files with valid checksums out of forty-seven
download cleanly, verify cleanly, and produce a number. There is no failure to
notice; the only witness is the count the listing published about itself.

`argv` is the other one worth reading. Sending the token as `-H "Authorization:
Bearer ..."` works, downloads the deposit, and passes every functional check
here — while publishing the credential to every `ps` on the machine for the
several hours a 4.9 GB transfer takes. Nothing about the outcome would reveal
that, so the fixture asserts the mechanism instead: a config file, mode 0600,
removed on both the success and the failure path.

`placeholder` exists because of an actual incident rather than an imagined one.
The example command in `DRYAD_NO_CREDENTIALS` was pasted unedited on 31 July, so
`~/.config/dryad/credentials.json` came to hold the literal strings `ID` and
`SECRET` — a file that is well-formed JSON, mode 0600, and passes every other
guard here. The failure that follows is Dryad's rejection, which reads as a
broken account. The fixture asserts both polarities, because a guard that also
rejected a real opaque credential would be worse than the paste it was written
for and nothing else here would catch it.

`no_files` and `bundle_opt_in` are the other important pair. They are the same input
and differ only in whether the caller asked for the fallback. A resolver that
always fell back would satisfy nothing here except `parses`, and a resolver that
never fell back would leave us with no way to fetch a deposit whose listing is
broken. The distinction has to be the caller's, made explicitly.

The payloads are the real shapes returned by
https://datadryad.org/api/v2/versions/144593/files on 31 July 2026, trimmed. If
Dryad changes its key names these fixtures keep passing and the live fetch
starts failing -- which is the correct way round, because the live failure is
loud and this file cannot know what Dryad did.

Run:  python3 test_dryad_files.py
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_data as fd  # noqa: E402

FAILS: list[str] = []

DOI = "10.5061/dryad.wwpzgmshb"
VER = "/api/v2/versions/144593"

DATASET = {
    "title": "Immune challenges increase network centrality in a queenless ant",
    "license": "CC0-1.0",
    "_links": {"stash:version": {"href": VER}},
}

# The same deposit, with the byte count it actually publishes. Kept separate
# because most fixtures below hand back a file set that is deliberately not the
# real deposit, and they should be failing on the thing they are about rather
# than on a size cross-check they never meant to trigger.
DATASET_SIZED = dict(DATASET, storageSize=4894343349)  # 4894312027 + 31322

FILE_ZIP = {
    "path": "AlciatoreEtAl_2021.zip",
    "size": 4894312027,
    "mimeType": "application/zip",
    "status": "copied",
    "digest": "19dd012bc8ff5e3ce3ce84bab1e7192400d737c726bbfe85fa4910b74ffa8c04",
    "digestType": "sha-256",
    "_links": {"stash:download": {"href": "/api/v2/files/1094952/download"}},
}
FILE_PDF = {
    "path": "README.pdf",
    "size": 31322,
    "mimeType": "application/pdf",
    "status": "created",
    "digest": "b043f9bc5ed61b75bb5ba66a684dbe05c02a40510572d352d5eb61fe842c91bc",
    "digestType": "sha-256",
    "_links": {"stash:download": {"href": "/api/v2/files/1094954/download"}},
}


def faker(listing, dataset=None, listing_raises=None, page_raises=None):
    """A stand-in for get_json. No network, and it asserts the URLs we build.

    `listing` may be one page (a dict) or several (a list of dicts). When it is
    several, the pages are served in order and each is expected to be reached by
    following the previous page's `_links.next`, so a resolver that ignored
    pagination would see only the first one -- which is exactly the bug these
    fixtures exist to catch. `page_raises` maps a 1-based page number to an error
    message, so a mid-listing failure can be exercised.
    """
    pages = listing if isinstance(listing, list) else [listing]
    served: list[str] = []

    def fetch(url: str):
        if "/files" in url:
            served.append(url)
            n = len(served)
            if page_raises and n in page_raises:
                raise RuntimeError(page_raises[n])
            if listing_raises:
                raise RuntimeError(listing_raises)
            if n > len(pages):
                raise AssertionError(
                    f"resolver asked for page {n} but only {len(pages)} exist: {url}")
            return pages[n - 1]
        if "/datasets/" in url:
            return dataset if dataset is not None else DATASET
        raise AssertionError(f"resolver asked for an unexpected url: {url}")

    fetch.served = served  # type: ignore[attr-defined]
    return fetch


def page(entries, *, total, nxt=None):
    """One page of a Dryad file listing, shaped as the live service shapes it."""
    p = {"count": len(entries), "total": total,
         "_embedded": {"stash:files": entries},
         "_links": {"self": {"href": f"{VER}/files"}}}
    if nxt:
        p["_links"]["next"] = {"href": nxt}
    return p


def ok(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS  {name}")
    else:
        FAILS.append(name)
        print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))


def raises(name: str, fn, needles: tuple[str, ...]) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        missing = [n for n in needles if n not in msg]
        ok(name, not missing, f"message lacked {missing!r}; said: {msg}")
        return
    ok(name, False, "returned instead of raising")


def main() -> int:
    print("dryad_files fixtures\n")

    # ---------------------------------------------------------------- parses
    listing = {"count": 2, "total": 2,
               "_embedded": {"stash:files": [FILE_ZIP, FILE_PDF]}}
    files, meta = fd.dryad_files(DOI, fetch=faker(listing))
    ok("parses: two files, not one bundle", len(files) == 2, f"got {len(files)}")
    ok("parses: names come from `path`",
       [f["name"] for f in files] == ["AlciatoreEtAl_2021.zip", "README.pdf"])
    ok("parses: url is the absolute stash:download href",
       files[0]["url"] == "https://datadryad.org/api/v2/files/1094952/download",
       files[0]["url"])
    ok("parses: size is carried, so the arrival can be checked",
       files[0]["size"] == 4894312027)
    ok("parses: sha-256 is carried as digest + digest_type, not as md5",
       files[0]["digest_type"] == "sha-256"
       and files[0]["digest"] == FILE_ZIP["digest"]
       and "md5" not in files[0])
    ok("parses: no entry points at the generated /download bundle",
       not any(f["url"].endswith(f"{VER}/download") for f in files))
    ok("parses: meta keeps the deposit's own title",
       meta["title"] == DATASET["title"] and meta["license"] == "CC0-1.0")

    # ------------------------------------------------------------ pagination
    # The v2.13 defect, in both polarities. Dryad serves twenty entries a page;
    # richardson_2021 has 47 files and v2.13 came back with 20 of them, all
    # valid, summing to 115.3 MB of a 372.6 MB deposit. Nothing about that looks
    # like an error downstream, which is what makes it the expensive kind.
    def mkfile(name, size, fid):
        return {"path": name, "size": size, "status": "created",
                "digest": "a" * 64, "digestType": "sha-256",
                "_links": {"stash:download": {"href": f"/api/v2/files/{fid}/download"}}}

    five = [mkfile(f"week_{i}.txt.gz", 100 + i, 600 + i) for i in range(5)]
    paged = faker([page(five[:2], total=5, nxt=f"{VER}/files?page=2"),
                   page(five[2:4], total=5, nxt=f"{VER}/files?page=3"),
                   page(five[4:], total=5)])
    files_p, _ = fd.dryad_files(DOI, fetch=paged)
    ok("paginates: all three pages are read, not just the first",
       len(files_p) == 5, f"got {len(files_p)}")
    ok("paginates: order is preserved across the page boundary",
       [f["name"] for f in files_p] == [f["path"] for f in five])
    ok("paginates: page 2 and page 3 were reached by following _links.next",
       any("page=2" in u for u in paged.served)
       and any("page=3" in u for u in paged.served), str(paged.served))

    raises("truncated: 2 entries against a published total of 5 raises",
           lambda: fd.dryad_files(DOI, fetch=faker(page(five[:2], total=5))),
           ("enumerated 2", "says this version has 5", "partial deposit"))

    loop = page(five[:2], total=5, nxt=f"{VER}/files")
    raises("page_loop: a `next` that points back at a page already read raises",
           lambda: fd.dryad_files(DOI, fetch=faker([loop, loop])),
           ("points back at", "already been read"))

    raises("mid_listing_failure: failing on page 2 raises rather than "
           "returning page 1",
           lambda: fd.dryad_files(
               DOI, fetch=faker([page(five[:2], total=5, nxt=f"{VER}/files?page=2"),
                                 page(five[2:], total=5)],
                                page_raises={2: "502 from dryad"})),
           ("read 1 page(s)", "502 from dryad", "partial enumeration"))

    # ------------------------------------------------- the size cross-check
    real_two = page([FILE_ZIP, FILE_PDF], total=2)
    files_s, meta_s = fd.dryad_files(DOI, fetch=faker(real_two, dataset=DATASET_SIZED))
    ok("storage_ok: the listed bytes equal the deposit's own storageSize",
       len(files_s) == 2 and meta_s["resolved_bytes"] == 4894343349
       and meta_s["storage_size"] == 4894343349)

    # Gate one passes here -- count 1, total 1 -- so only the byte count can
    # catch it. This is the shape of a deposit whose listing is internally
    # consistent and still not the whole thing.
    raises("storage_mismatch: a consistent count with the wrong byte total raises",
           lambda: fd.dryad_files(
               DOI, fetch=faker(page([FILE_PDF], total=1), dataset=DATASET_SIZED)),
           ("31,322", "4,894,343,349", "Gate one passed"))

    # ------------------------------------------------- the refusing polarity
    # The needle here was "cannot be resumed" until v2.15. That was asserting a
    # mechanism nobody observed -- see the withdrawal in `dryad_files`. What the
    # refusal may claim is what the deposit document actually shows: the bundle
    # publishes no size and no sha-256, so a truncated arrival is undetectable.
    # v2.16 adds the one thing about this route that *was* measured: HTTP 405.
    raises("no_files: an empty stash:files raises and names --dryad-bundle",
           lambda: fd.dryad_files(DOI, fetch=faker({"_embedded": {"stash:files": []}})),
           ("could not enumerate", "--dryad-bundle",
            "publishes neither a size nor a checksum", "405"))

    raises("no_embedded: a listing with no _embedded at all raises",
           lambda: fd.dryad_files(DOI, fetch=faker({"count": 0, "total": 0})),
           ("could not enumerate", "top-level keys"))

    raises("listing_500: an error fetching the listing is quoted, not swallowed",
           lambda: fd.dryad_files(DOI, fetch=faker(None, listing_raises="503 from dryad")),
           ("503 from dryad",))

    # A file we cannot address is a hole in the deposit. Returning the other one
    # would present a partial download as a complete one.
    broken = dict(FILE_PDF, _links={"self": {"href": "/api/v2/files/1094954"}})
    raises("no_download: a file with no download link raises rather than being skipped",
           lambda: fd.dryad_files(
               DOI, fetch=faker({"_embedded": {"stash:files": [FILE_ZIP, broken]}})),
           ("README.pdf", "no stash:download", "'self'"))

    evil = dict(FILE_PDF, path="../../../etc/passwd")
    files_t, _ = fd.dryad_files(
        DOI, fetch=faker({"_embedded": {"stash:files": [evil]}}))
    ok("traversal: a path with .. is reduced to its basename, not joined as given",
       files_t[0]["name"] == "passwd", files_t[0]["name"])
    raises("traversal: a path that is nothing but .. is refused outright",
           lambda: fd.safe_member_name("../.."), ("unusable filename",))

    # ------------------------------------------------- the opt-in polarity
    files_b, _ = fd.dryad_files(DOI, allow_bundle=True,
                                fetch=faker({"_embedded": {"stash:files": []}}))
    ok("bundle_opt_in: same input, explicit flag, one bundle entry",
       len(files_b) == 1 and files_b[0]["url"].endswith(f"{VER}/download"))
    ok("bundle_opt_in: the bundle entry admits it has no size and no checksum",
       files_b[0]["size"] is None and files_b[0]["digest"] is None
       and files_b[0]["status"] == "generated-bundle")

    # A check that records a fact rather than asserting a hope. The flag still
    # builds the GET that Dryad refused on size for alciatore_2021, so the entry
    # it returns is a record of a route, not a working escape hatch. If someone
    # later makes the fallback do something else -- a POST, a poll -- this is
    # the check that should fail and force the docstring to be rewritten.
    ok("bundle_opt_in: the flag still constructs the GET Dryad refused on size",
       files_b[0]["url"].endswith("/download"),
       "measured 31 July 2026: GET /api/v2/versions/144593/download -> 405, no "
       "Allow: header, body exactly 89 bytes: 'The dataset is too large for zip "
       "file generation. Please download each file individually.'")
    ok("withdrawal: the docstring carries both wrong explanations, not just the last",
       "withdrawn" in fd.dryad_files.__doc__
       and "405" in fd.dryad_files.__doc__
       and "v2.13" in fd.dryad_files.__doc__ and "v2.15" in fd.dryad_files.__doc__,
       "a correction that replaces the previous correction silently is how the "
       "same inference gets made a third time")
    ok("withdrawal: the 56/56 coincidence is named where the evidence is written down",
       "coincidence" in fd.dryad_files.__doc__,
       "curl exit 56 and the 401 body's content-length 56 are unrelated and "
       "read like two facts agreeing")
    ok("withdrawal: the server's own sentence is quoted, not paraphrased",
       "too large for zip file generation" in fd.dryad_files.__doc__,
       "the whole failure mode was three rounds of paraphrasing a response "
       "nobody had read; the quote is the fix")
    # The over-generalisation this project keeps making is 'one observation ->
    # a property of the thing'. 405 on a 4.9 GB deposit says nothing about a
    # 390 MB one, and richardson_2021 has not been tested. This check exists to
    # make that limit survive the next edit.
    ok("withdrawal: the refusal is recorded as size-conditional, not as a dead route",
       "size-conditional" in fd.dryad_files.__doc__
       and "has not been tested" in fd.dryad_files.__doc__,
       "alciatore_2021 is 4,894,343,349 bytes and richardson_2021 is "
       "390,749,381; only the first was measured")

    # ------------------------------------------------------------- checksums
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "payload.bin"
        payload = b"hives and hierarchies" * 1000
        p.write_bytes(payload)
        want256 = hashlib.sha256(payload).hexdigest()

        ok("digest_algo: sha-256 is computed, which the pre-2.13 md5-only path could not",
           fd.digest_of(p, "sha-256") == want256)
        ok("digest_algo: md5 still works for Zenodo",
           fd.digest_of(p, "md5") == hashlib.md5(payload).hexdigest())
        ok("digest_algo: an algorithm we cannot compute returns None, not a wrong hex",
           fd.digest_of(p, "adler-32") is None and fd.digest_of(p, None) is None)

        good = dict(name="payload.bin", size=len(payload),
                    digest=want256, digest_type="sha-256")
        quiet = lambda *a, **k: None  # noqa: E731
        ok("local_match: a correct file on disk is adopted",
           fd.file_matches(p, good, quiet))
        ok("local_match: right size, wrong digest -> refused",
           not fd.file_matches(p, dict(good, digest="0" * 64), quiet))
        ok("local_match: right digest, wrong size -> refused",
           not fd.file_matches(p, dict(good, size=len(payload) + 1), quiet))
        ok("local_match: no published size -> refused, because nothing was checked",
           not fd.file_matches(p, dict(good, size=None), quiet))
        ok("local_match: no published digest -> refused, size alone is not a match",
           not fd.file_matches(p, dict(good, digest=None), quiet))
        ok("local_match: uncomputable algorithm -> refused rather than assumed fine",
           not fd.file_matches(p, dict(good, digest_type="adler-32"), quiet))
        ok("local_match: a file that is not there -> refused",
           not fd.file_matches(p.with_name("absent.bin"), good, quiet))

    # ------------------------------------------------------ dryad credentials
    # Everything below runs with the real environment removed, so a developer
    # who happens to have DRYAD_CLIENT_ID exported does not silently get a
    # different test run from one who does not.
    import os as _os

    def clean_env():
        for k in fd.DRYAD_CRED_ENV:
            _os.environ.pop(k, None)

    saved_env = {k: _os.environ.get(k) for k in fd.DRYAD_CRED_ENV}
    saved_files = fd.DRYAD_CRED_FILES
    try:
        with tempfile.TemporaryDirectory() as td:
            cred = Path(td) / "credentials.json"
            fd.DRYAD_CRED_FILES = (str(cred),)

            clean_env()
            ok("creds: nothing set anywhere -> None, not an exception",
               fd.dryad_credentials() is None)

            _os.environ[fd.DRYAD_CRED_ENV[0]] = "env-id"
            _os.environ[fd.DRYAD_CRED_ENV[1]] = "env-secret"
            got = fd.dryad_credentials()
            ok("creds: the environment is read, and says where it came from",
               got is not None and got[0] == "env-id" and got[1] == "env-secret"
               and "DRYAD_CLIENT_ID" in got[2], str(got))

            # A file with a *different* secret, to prove which one wins rather
            # than that either one is present.
            cred.write_text('{"client_id":"file-id","client_secret":"file-secret"}')
            _os.chmod(cred, 0o600)
            got = fd.dryad_credentials()
            ok("creds: the environment wins over the file when both are present",
               got is not None and got[0] == "env-id", str(got))

            clean_env()
            got = fd.dryad_credentials()
            ok("creds: the file is read when the environment is empty",
               got is not None and got[0] == "file-id"
               and got[1] == "file-secret" and got[2] == str(cred), str(got))

            # The mode check is the one guard here that protects something other
            # than this script: a 0644 secret is readable by every account on the
            # machine, and a warning printed during a 4.9 GB transfer is a
            # warning nobody reads.
            _os.chmod(cred, 0o644)
            raises("creds: a group/world-readable secret file is refused, with the fix",
                   fd.dryad_credentials, ("0644", "chmod 600", str(cred)))
            _os.chmod(cred, 0o600)

            cred.write_text('{"client_id":"only-id"}')
            raises("creds: a file missing client_secret names which half is missing",
                   fd.dryad_credentials, ("client_secret",))

            # The malformed file still contains a secret. An error that echoed
            # the file to help the user debug it would put that secret into the
            # terminal, the scrollback, and whatever gets pasted into a chat.
            cred.write_text('{"client_id":"x","client_secret":"S3CR3T-not-json')
            try:
                fd.dryad_credentials()
                ok("creds: malformed JSON raises", False, "returned")
            except Exception as exc:  # noqa: BLE001
                m = str(exc)
                ok("creds: malformed JSON raises and names the expected shape",
                   "client_id" in m and "client_secret" in m, m)
                ok("creds: the malformed file's contents are not echoed into the error",
                   "S3CR3T" not in m, m)

            # ---------------------------------------------- placeholder guard
            # On 31 July the example one-liner in DRYAD_NO_CREDENTIALS was
            # pasted unedited, so the credentials file ended up holding the
            # literal strings ID and SECRET at mode 0600 -- a perfectly
            # well-formed file that no other guard here objects to. Without
            # this one the run reaches Dryad, is rejected, and reports "Dryad
            # refused the client credentials", which reads as a broken account
            # rather than as an unedited copy-paste.
            cred.write_text('{"client_id":"ID","client_secret":"SECRET"}')
            _os.chmod(cred, 0o600)
            raises("placeholder: the exact file the 31 July paste produced is refused",
                   fd.dryad_credentials,
                   ("placeholder", "client_id", "client_secret", str(cred)))

            cred.write_text('{"client_id":"<CLIENT_ID>",'
                            '"client_secret":"<CLIENT_SECRET>"}')
            raises("placeholder: the angle-bracket form this script now prints is refused",
                   fd.dryad_credentials, ("placeholder", str(cred)))

            # Only the half that is example text may be named. A message that
            # said both when one was real would send the user to re-copy a
            # credential that was fine.
            cred.write_text('{"client_id":"5f2c9ab41e7d4","client_secret":"SECRET"}')
            try:
                fd.dryad_credentials()
                ok("placeholder: a real id with a placeholder secret is refused",
                   False, "returned")
            except Exception as exc:  # noqa: BLE001
                m = str(exc)
                head = m.split("\n")[0]
                ok("placeholder: a real id with a placeholder secret is refused",
                   "placeholder" in head, head)
                ok("placeholder: only the half that is example text is named",
                   "client_secret" in head and "client_id and" not in head, head)

            # The opposite polarity. Real Dryad credentials are long opaque
            # strings; a guard that rejected one would be worse than the paste
            # it was written for, and nothing above would notice.
            cred.write_text('{"client_id":"5f2c9ab41e7d4c8b",'
                            '"client_secret":"kQ7x2mVnB4tZpL9wR1sD"}')
            got = fd.dryad_credentials()
            ok("placeholder: a credential that looks real is accepted unchanged",
               got is not None and got[0] == "5f2c9ab41e7d4c8b"
               and got[1] == "kQ7x2mVnB4tZpL9wR1sD", str(got))

            # The environment path is a separate return and needs its own guard;
            # the file path passing says nothing about it.
            cred.unlink()
            _os.environ[fd.DRYAD_CRED_ENV[0]] = "ID"
            _os.environ[fd.DRYAD_CRED_ENV[1]] = "SECRET"
            raises("placeholder: the environment path is guarded too, and says so",
                   fd.dryad_credentials, ("placeholder", "DRYAD_CLIENT_ID"))
            clean_env()

            ok("placeholder: the refusal repeats the account instructions",
               "ORCID" in fd.DRYAD_NO_CREDENTIALS
               and "My account" in fd.DRYAD_NO_CREDENTIALS)
            ok("placeholder: this script no longer prints ID/SECRET as its example",
               '"ID"' not in fd.DRYAD_NO_CREDENTIALS
               and '"SECRET"' not in fd.DRYAD_NO_CREDENTIALS,
               "the example is what got pasted; printing it again reopens this")

            clean_env()

            # -------------------------------------------------- token exchange
            fd._DRYAD_TOKEN.update(value=None, expires_at=0.0)
            raises("token: no credentials -> refuses, and names every step to fix it",
                   fd.dryad_token,
                   ("ORCID", "My account", "client secret", "chmod 600",
                    "adopted", "bearer token"))
            ok("token: required=False returns None instead of raising, so the "
               "adoption path can run without credentials",
               fd.dryad_token(required=False) is None)

            _os.environ[fd.DRYAD_CRED_ENV[0]] = "cid"
            _os.environ[fd.DRYAD_CRED_ENV[1]] = "sec-abcdef"

            calls: list[bool] = []

            def form_ok(cid, sec, basic):
                calls.append(basic)
                if basic:
                    raise AssertionError("Basic should not have been reached")
                return {"access_token": "TOK-1", "expires_in": 3600}

            fd._DRYAD_TOKEN.update(value=None, expires_at=0.0)
            ok("token: the documented form-body exchange is tried first and used",
               fd.dryad_token(exchange=form_ok, now=lambda: 1000.0) == "TOK-1"
               and calls == [False], str(calls))

            ok("token: a second call inside the lifetime does not re-exchange",
               fd.dryad_token(exchange=form_ok, now=lambda: 1000.0) == "TOK-1"
               and calls == [False], str(calls))

            # expires_in 3600 with a minute of slack -> valid until 4540.
            ok("token: past expiry-minus-slack it exchanges again",
               fd.dryad_token(exchange=form_ok, now=lambda: 4600.0) == "TOK-1"
               and calls == [False, False], str(calls))

            styles: list[bool] = []

            def basic_only(cid, sec, basic):
                styles.append(basic)
                if not basic:
                    raise RuntimeError("HTTP Error 401: Unauthorized")
                return {"access_token": "TOK-2", "expires_in": 100}

            fd._DRYAD_TOKEN.update(value=None, expires_at=0.0)
            ok("token: a server that wants HTTP Basic is still reached, on the retry",
               fd.dryad_token(exchange=basic_only, now=lambda: 0.0) == "TOK-2"
               and styles == [False, True], str(styles))

            fd._DRYAD_TOKEN.update(value=None, expires_at=0.0)

            def both_fail(cid, sec, basic):
                raise RuntimeError("HTTP Error 401: Unauthorized")

            raises("token: when both styles fail the error names both, so a bad id "
                   "does not read as an unsupported auth style",
                   lambda: fd.dryad_token(exchange=both_fail, now=lambda: 0.0),
                   ("form body", "HTTP Basic", "401", "ORCID sign-in"))

            def leaky(cid, sec, basic):
                raise RuntimeError(
                    f"400: client_secret={sec} was rejected for client_id={cid}")

            try:
                fd.dryad_token(exchange=leaky, now=lambda: 0.0)
                ok("token: a server echoing the secret back raises", False, "returned")
            except Exception as exc:  # noqa: BLE001
                m = str(exc)
                ok("token: a secret echoed back by the server is redacted from the error",
                   "sec-abcdef" not in m and "<redacted>" in m, m)

            def no_token(cid, sec, basic):
                return {"token_type": "Bearer", "expires_in": 7200}

            fd._DRYAD_TOKEN.update(value=None, expires_at=0.0)
            raises("token: a 200 carrying no access_token raises here rather than "
                   "becoming `Bearer None` and returning as the same 401",
                   lambda: fd.dryad_token(exchange=no_token, now=lambda: 0.0),
                   ("without an access_token", "expires_in"))
    finally:
        fd.DRYAD_CRED_FILES = saved_files
        for k, v in saved_env.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v
        fd._DRYAD_TOKEN.update(value=None, expires_at=0.0)

    # ------------------------------------------- the token never reaches argv
    # This is the check that matters most in this block and it is easy to get
    # wrong by writing it the obvious way: `-H "Authorization: Bearer ..."` works
    # perfectly, passes every functional test, and publishes the credential to
    # every `ps` on the machine for the duration of a multi-hour transfer. The
    # fixture asserts the mechanism (a 0600 config file, gone afterwards), not
    # just the absence of the string.
    SECRET = "TOK-do-not-log-me"
    with tempfile.TemporaryDirectory() as td:
        seen: list[list[str]] = []
        cfg_seen: list[tuple[str, str, int]] = []

        def fake_call(argv):
            seen.append(list(argv))
            if "-K" in argv:
                p = Path(argv[argv.index("-K") + 1])
                cfg_seen.append((str(p), p.read_text(),
                                 p.stat().st_mode & 0o777))
            Path(argv[argv.index("-o") + 1]).write_bytes(b"payload")
            return 0

        real_call, real_curl = fd.subprocess.call, fd.HAVE_CURL
        try:
            fd.subprocess.call = fake_call
            fd.HAVE_CURL = True
            dest = Path(td) / "f.bin"
            fd.download("https://example.invalid/f", dest, 7, token=SECRET)
            argv = seen[0]
            ok("argv: the token appears nowhere on curl's command line",
               not any(SECRET in a for a in argv), " ".join(argv))
            ok("argv: it is passed by -K config file instead",
               "-K" in argv and len(cfg_seen) == 1, " ".join(argv))
            ok("argv: the config file carries the Authorization header",
               cfg_seen and f"Bearer {SECRET}" in cfg_seen[0][1])
            ok("argv: the config file is mode 0600",
               cfg_seen and cfg_seen[0][2] == 0o600,
               oct(cfg_seen[0][2]) if cfg_seen else "no config file")
            ok("argv: the config file is removed once curl returns",
               cfg_seen and not Path(cfg_seen[0][0]).exists())
            ok("argv: the file still arrives", dest.read_bytes() == b"payload")

            seen.clear(); cfg_seen.clear()
            fd.download("https://example.invalid/g", Path(td) / "g.bin", 7)
            ok("argv: no token -> no -K, so the unauthenticated path is unchanged",
               "-K" not in seen[0], " ".join(seen[0]))

            # A failing transfer takes the `finally`, not the happy path. A
            # config file left behind after a failure is a credential on disk
            # that nothing will ever clean up.
            seen.clear(); cfg_seen.clear()

            def fail_call(argv):
                seen.append(list(argv))
                if "-K" in argv:
                    p = Path(argv[argv.index("-K") + 1])
                    cfg_seen.append((str(p), "", 0))
                return 22

            fd.subprocess.call = fail_call
            try:
                fd.download("https://example.invalid/h", Path(td) / "h.bin",
                            token=SECRET)
            except RuntimeError:
                pass
            ok("argv: a failed transfer still removes the config file",
               cfg_seen and not Path(cfg_seen[0][0]).exists())
        finally:
            fd.subprocess.call = real_call
            fd.HAVE_CURL = real_curl

    # ------------------------------------------------------------- manifest
    with tempfile.TemporaryDirectory() as td:
        mpath = Path(td) / "MANIFEST.json"
        man = fd.Manifest(mpath)
        target = Path(td) / "f.zip"
        target.write_bytes(b"x")
        man.record("k", "f.zip", "http://x", target, "abc", {}, digest_type="sha-256")
        ok("manifest: a recorded digest satisfies done()",
           man.done("k", "f.zip", 1, "abc"))
        ok("manifest: a different published digest does not",
           not man.done("k", "f.zip", 1, "def"))
        ok("manifest: no published digest falls back to `complete`",
           man.done("k", "f.zip", 1, None))
        # Pre-2.13 manifests wrote the field as `md5`. Those entries are real and
        # on the drive; refusing them would re-download deposits we already have.
        man.data["entries"]["k/legacy.zip"] = dict(complete=True, md5="abc")
        ok("manifest: a pre-2.13 entry keyed `md5` is still honoured",
           man.done("k", "legacy.zip", 1, "abc")
           and not man.done("k", "legacy.zip", 1, "def"))

    print()
    if FAILS:
        print(f"{len(FAILS)} fixture(s) failed: {', '.join(FAILS)}")
        return 1
    print("all fixtures pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
