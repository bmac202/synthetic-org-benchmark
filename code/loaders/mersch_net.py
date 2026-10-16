"""Mersch, Crespi & Keller (2013) daily interaction matrices -> canonical log.

Dryad 10.5061/dryad.8d8h7, CC0. The deposit ships 246 files named
`network_col{N}_day{M}.txt`: six colonies, forty-one days each. Each file is a
comma-separated header of tag ids followed by that many rows of that many
values, and `validate_mersch.py` has confirmed on the real deposit that all 246
are square, that every one satisfies M == M^T exactly (largest deviation 0), and
that the colony-day grid is complete with no interior gaps.

`loaders/mersch.py` reads the *labels*. This file reads the *graph*. They are
deliberately separate modules and they do NOT currently join, for a reason given
below that is worth reading before anyone tries.

HOW THIS JOINS TO behavior.csv (RESOLVED -- see loaders/mersch_map.py)
----------------------------------------------------------------------
The two files name their colonies from different vocabularies. `behavior.csv`
says 4, 18, 21, 29, 58 and 78. These filenames say col1 .. col6. The deposit
states the correspondence nowhere, and the paper gives colony sizes only as the
range "122 to 192 per colony", so it could not be read off either.

That is not a formatting nuisance, because a guess about which colony is which
is a guess about which ants are which: tag ids are reused across colonies (218
of the 222 ids occur in more than one), so pairing the wrong `col` with the
wrong colony does not fail, it silently relabels the animals. The validator
originally reported two confident numbers built on exactly such a pairing -- the
two vocabularies happen to share the single label "4", by coincidence of
numbering, and a check that only fired on an empty intersection let it through.
Those numbers are withdrawn.

The correspondence was then established from the deposit itself, by set
containment on the ant ids after normalizing `Ant4` and `4` to the same integer:
for each behavioural colony exactly one matrix column contains ALL of its ants,
each column is claimed exactly once, and the runner-up leaves 26 to 49 ants
outside. `mersch_map.resolve()` re-derives this on every load and raises if it
does not reproduce -- the mapping in that file is a tripwire, not an authority.

So structure CROSSED WITH TASK is now computable. Two things travel with it.
Seventeen tracked ants (two or three per colony) appear in the matrices and not
in behavior.csv; they have no task label and are reported in
`meta["unlabelled_nodes"]` rather than carried into a cross-tab, where an
unlabelled node becomes a fifth task. And node keys change meaning with
`--node-namespace`: `behavior` (the default now that the mapping holds) emits
`{colony}:{tag}` in behavior.csv's namespace so the join is a lookup, while
`matrix` emits the older `col{N}:{ant}` and cannot be joined to anything.

THREE DECISIONS THIS FILE MAKES OUT LOUD
-----------------------------------------
1.  **Self-loops are dropped by default.** 15 of the 246 matrices carry a
    non-zero diagonal. Self-interaction is not a thing an ant does to itself, and
    a diagonal entry inflates that individual's degree by an amount that differs
    per individual -- so it does not cancel, it re-ranks. `--self-loops keep`
    retains them; either way the count is reported rather than absorbed.

2.  **Colonies are not pooled unless you ask.** Six colonies in one graph is six
    disconnected components, and Freeman centralization on that is a number about
    the union and not about any colony: the denominator (n-1)(n-2) grows with the
    pooled n while the largest degree does not. `--colony col1` is the normal
    call. `--pool` is available and prints a warning that stays in the metadata.

3.  **A weight of w becomes one edge, not w edges.** The matrices are weighted.
    In-degree over repeated records would then be an interaction count; over
    single records it is a *partner count*. Both are legitimate and they answer
    different questions, so the choice is explicit (`--weight binary|repeat`) and
    the answer is recorded in `edge_semantics`. Binary is the default because
    hub stability is a question about who you interact WITH.

AND ONE IT REFUSES TO MAKE
--------------------------
Every colony ends the record with fewer ants than it started with. Any per-capita
quantity therefore has a moving denominator across the 41 days, and a trend
computed against a fixed n is partly just the dying. `meta["census"]` carries the
per-day node count so the denominator is always available to whatever consumes
this, and `netstats.structure_report` reads it.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from . import mersch_map
from .common import find_files, to_float

NET_RE = re.compile(r"network_col(\d+)_day(\d+)", re.I)


def is_apple_double(p: Path) -> bool:
    """macOS resource-fork shadows, named exactly like the real matrices."""
    return p.name.startswith("._") or "__MACOSX" in p.parts


def matrix_files(raw_dir: Path) -> list[Path]:
    return [p for p in find_files(raw_dir, ["network_col*_day*.txt"])
            if not is_apple_double(p)]


def read_matrix(path: Path) -> tuple[list[str], list[list[float | None]]]:
    """Return (ids, M). Header line is the ids; the next len(ids) lines are rows.

    Raises ValueError rather than returning a partial matrix. A matrix short by
    one row is the signature of a header eaten as data (or the reverse), and the
    two failures need different fixes -- neither is served by quietly reading
    whatever was there.
    """
    raw = path.read_bytes().decode("utf-8", errors="replace")
    lines = [ln for ln in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
             if ln.strip()]
    if not lines:
        raise ValueError(f"{path.name} is empty")
    ids = [x.strip().strip('"') for x in lines[0].split(",")]
    body = [ln.split(",") for ln in lines[1:]]
    if len(ids) != len(set(ids)):
        raise ValueError(
            f"{path.name} repeats a tag id in its header. Two columns for one ant "
            f"splits that ant's edges across both and its degree is wrong in each")
    if len(body) != len(ids) or any(len(r) != len(ids) for r in body):
        extra = (" -- short by exactly one row, the signature of a data row eaten "
                 "as a header or a header that is really data"
                 if len(body) == len(ids) - 1 else "")
        raise ValueError(
            f"{path.name} is not square: {len(ids)} header ids against "
            f"{len(body)} rows{extra}")
    return ids, [[to_float(x) for x in r] for r in body]


def load(raw_dir: Path, colony: str | None = None, pool: bool = False,
         self_loops: str = "drop", weight: str = "binary",
         min_weight: float = 0.0, max_files: int | None = None,
         node_namespace: str = "behavior"):
    """Return (log, meta) where log is a list of {"sender","recipient","mtype","tbin"}.

    `node_namespace="behavior"` re-derives the colony correspondence from the
    deposit and emits `{colony}:{tag}` keys that join to behavior.csv. It raises
    if the correspondence does not reproduce, because the failure mode here is a
    silent relabelling rather than a missing result. `"matrix"` emits the older
    `col{N}:{ant}` keys, which are safe precisely because they join to nothing.
    """
    files = matrix_files(raw_dir)
    if not files:
        raise SystemExit(
            f"no network_col*_day*.txt under {raw_dir}. The Dryad bundle nests a "
            "tracking_data.zip inside it -- fetch_data.py v2.2+ expands both, but "
            "an older run stopped at one level. Re-run fetch_data.py.")

    # The correspondence is re-derived from the files, not read from a constant.
    # It also gives us the behavioural colony label for each matrix column and
    # the list of tracked ants that carry no task label.
    mapping: dict[str, str] = {}
    map_report: dict | None = None
    if node_namespace == "behavior":
        map_report = mersch_map.resolve(raw_dir, strict=True)
        mapping = map_report["mapping"]
    col_to_behavior = {v.replace("col", ""): k for k, v in mapping.items()}

    # `--colony` accepts either vocabulary: col1..col6 or 4/18/21/29/58/78.
    # Accepting both is not a convenience -- it is how a caller who thinks in
    # behavioural colonies stops silently getting a different animal's graph.
    wanted = None
    if colony is not None:
        raw_arg = str(colony).strip().lower()
        digits = raw_arg.replace("colony", "").replace("col", "").strip()
        prefixed = raw_arg.startswith("col")        # "col4" / "colony4"
        matrix_labels = {"1", "2", "3", "4", "5", "6"}
        if prefixed:
            if digits not in matrix_labels:
                raise SystemExit(f"--colony {colony!r}: matrix labels are col1..col6")
            wanted = digits
        elif digits in mapping:                     # a behaviour-table label
            # "4" is ALSO a valid matrix label, and behaviour colony 4 is col1 --
            # a different colony. This single shared label is what let the
            # withdrawn figures through, so it is refused rather than resolved
            # by precedence.
            if digits in matrix_labels:
                raise SystemExit(
                    f"--colony {colony!r} is ambiguous: '{digits}' names a colony in "
                    f"behavior.csv and also names col{digits}, and they are not the "
                    f"same colony (behaviour {digits} is {mapping[digits]}). Write "
                    f"'col{digits}' for the matrix or 'behavior:{digits}' for the "
                    f"behaviour table -- this is the collision the withdrawn "
                    f"figures came from.")
            wanted = mapping[digits].replace("col", "")
        elif raw_arg.startswith("behavior:") and raw_arg.split(":", 1)[1] in mapping:
            wanted = mapping[raw_arg.split(":", 1)[1]].replace("col", "")
        else:
            known = ", ".join(sorted(mapping, key=int)) or "4/18/21/29/58/78"
            raise SystemExit(
                f"--colony {colony!r} is neither a matrix label (col1..col6) nor a "
                f"behaviour-table label ({known})")

    by_key: dict[tuple[str, int], Path] = {}
    for p in files:
        m = NET_RE.search(p.name)
        if not m:
            continue
        col, day = m.group(1), int(m.group(2))
        if wanted is not None and col != wanted:
            continue
        by_key[(col, day)] = p

    if not by_key:
        seen = sorted({NET_RE.search(p.name).group(1) for p in files
                       if NET_RE.search(p.name)})
        raise SystemExit(f"no matrices for colony {colony!r}; available: "
                         f"{['col' + c for c in seen]}")

    colonies = sorted({c for c, _ in by_key})
    if len(colonies) > 1 and not pool:
        raise SystemExit(
            f"this would pool {len(colonies)} colonies ({['col' + c for c in colonies]}) "
            "into one graph, which is that many disconnected components. Freeman "
            "centralization on a disconnected union is a number about the union: "
            "the (n-1)(n-2) denominator grows with the pooled node count while the "
            "largest degree does not, so the score moves for a reason that has "
            "nothing to do with how any colony is organized.\n"
            "  -> pass --colony col1 (the normal call), or --pool if you have a "
            "reason to want the union and will say so in the caption.")

    order = sorted(by_key)
    if max_files is not None:
        order = order[:max_files]
        print(f"  NOTE: reading {len(order)} of {len(by_key)} matrices "
              f"(--max-files). The rest were NOT read.")

    days = sorted({d for _, d in order})
    day_ix = {d: i for i, d in enumerate(days)}

    log: list[dict] = []
    # `census` is a LIST of records, not a dict keyed by day, and that is
    # deliberate. This metadata is written to meta.json, and JSON has no integer
    # keys -- a dict keyed by day comes back with keys "1", "10", "2", so
    # `sorted(census)` after a round-trip orders the record lexicographically and
    # `census[0]` raises KeyError. The failure is quiet in the worst way: day 10
    # sorts before day 2, so "first day" and "last day" silently become the wrong
    # days and the shrinkage figure computed from them is wrong rather than
    # missing. A list carries its own order through serialization.
    census: list[dict] = []
    census_by_colony: dict[str, list[dict]] = defaultdict(list)
    n_self, self_files, unreadable = 0, [], []
    n_edges = 0
    present: dict[int, set[str]] = defaultdict(set)

    for (col, day) in order:
        p = by_key[(col, day)]
        try:
            ids, M = read_matrix(p)
        except ValueError as exc:
            unreadable.append(str(exc))
            continue
        n = len(ids)
        if node_namespace == "behavior":
            # `Ant4` and behavior.csv's `4` are the same ant; the integer is the
            # only rendering both files agree on.
            beh = col_to_behavior[col]
            nodes = [f"{beh}:{mersch_map.tag_int(i)}" for i in ids]
        else:
            nodes = [f"col{col}:{i}" for i in ids]
        present[day_ix[day]].update(nodes)
        census_by_colony[col].append({"day": day, "n": n})

        had_self = False
        for i in range(n):
            di = M[i][i]
            if di is not None and di > min_weight:
                had_self = True
                n_self += 1
                if self_loops == "keep":
                    reps = _reps(di, weight)
                    for _ in range(reps):
                        log.append({"sender": nodes[i], "recipient": nodes[i],
                                    "mtype": "report", "tbin": day_ix[day]})
            for j in range(i + 1, n):
                w = M[i][j]
                if w is None or w <= min_weight:
                    continue
                n_edges += 1
                reps = _reps(w, weight)
                for _ in range(reps):
                    # Symmetric matrix: emit both directions so the undirected
                    # contact is visible to an instrument that reads direction.
                    log.append({"sender": nodes[i], "recipient": nodes[j],
                                "mtype": "report", "tbin": day_ix[day]})
                    log.append({"sender": nodes[j], "recipient": nodes[i],
                                "mtype": "report", "tbin": day_ix[day]})
        if had_self:
            self_files.append(p.name)

    ix_day = {i: d for d, i in day_ix.items()}
    for t in sorted(present):
        census.append({"tbin": t, "day": ix_day[t], "n": len(present[t])})

    if unreadable:
        print(f"  {len(unreadable)} matrix(es) could not be read and were SKIPPED:")
        for msg in unreadable[:5]:
            print(f"    {msg}")

    sizes = [c["n"] for c in census]
    shrink = None
    if len(sizes) >= 2 and sizes[0]:
        shrink = round((sizes[0] - sizes[-1]) / sizes[0], 4)

    meta = dict(
        source="Mersch, Crespi & Keller (2013), Dryad 10.5061/dryad.8d8h7, CC0",
        citation="Mersch, D. P., Crespi, A., & Keller, L. (2013). Science, 340(6136), 1090-1093.",
        colonies=["col" + c for c in colonies],
        pooled=bool(len(colonies) > 1),
        n_matrices=len(order),
        n_matrices_unreadable=len(unreadable),
        n_messages=len(log),
        n_edges_undirected=n_edges,
        n_timebins=len(days),
        day_range=[min(days), max(days)] if days else None,
        node_key=("{behavior_colony}:{tag_id}" if node_namespace == "behavior"
                  else "col{N}:{tag_id}"),
        node_namespace=node_namespace,
        directed=False,
        edge_semantics=("binary: one record per contacting pair per day, so in-degree "
                        "is a count of PARTNERS"
                        if weight == "binary" else
                        "repeat: the matrix weight is emitted as that many records, so "
                        "in-degree is a count of INTERACTIONS"),
        self_loops=self_loops,
        n_self_loops=n_self,
        self_loop_files=self_files[:10] or None,
        census=census,
        census_schema="list of {tbin, day, n} in day order; a list, not a day-keyed "
                      "dict, because JSON keys are strings and '10' sorts before '2'",
        census_by_colony={("col" + c): sorted(v, key=lambda r: r["day"])
                          for c, v in census_by_colony.items()},
        population_shrinkage=shrink,
        joinable_to_behavior_csv=(node_namespace == "behavior"),
        colony_map=mapping or None,
        colony_map_method=(map_report["method"] if map_report else None),
        colony_map_evidence=(map_report["rows"] if map_report else None),
        colony_map_note=(
            "the deposit states no correspondence between behavior.csv's "
            "4/18/21/29/58/78 and the filenames' col1..col6, and the paper gives "
            "sizes only as '122 to 192 per colony'. It was derived by set "
            "containment on integer-normalized tag ids -- exactly one matrix "
            "column contains ALL of each colony's ants, each column claimed once, "
            "runner-up missing 26 to 49 ants -- and mersch_map.resolve() "
            "re-derives it on every load rather than trusting the constant."
            if node_namespace == "behavior" else
            "node_namespace='matrix': these keys are deliberately unjoinable. "
            "Tag ids are reused across colonies, so pairing the wrong col with "
            "the wrong colony relabels the animals instead of failing."),
        unlabelled_nodes=(map_report["unlabelled_nodes"] if map_report else None),
        n_unlabelled_nodes=(map_report["n_unlabelled_nodes"] if map_report else None),
        unlabelled_nodes_note=(
            "tracked ants present in the matrices and absent from behavior.csv. "
            "They are kept in the graph -- they are real contacts and dropping "
            "them would change the structure being measured -- but they carry no "
            "task label, so any cross-tab on task must exclude them explicitly. "
            "An unlabelled node silently admitted to a task table becomes a fifth "
            "task, which is the shape of the withdrawn 596-of-805 figure."
            if map_report else None),
        census_vs_published_band=(
            "the paper states 122 to 192 workers per colony; four of the six "
            "matrix node counts and four of the six behavioural censuses fall "
            "below that floor. Unexplained. Do not report a Mersch colony size "
            "as the colony's size without this caveat."),
        interpretation=("Undirected daily contact networks. 'mtype' is 'report' only so "
                        "the existing instrument accepts the log unchanged -- these are "
                        "ants in contact, not reporting lines, and a LOW centralization "
                        "is the biologically expected result."),
    )
    if shrink and shrink > 0.05:
        meta["denominator_warning"] = (
            f"the node count falls {shrink:.1%} across the record "
            f"({sizes[0]} -> {sizes[-1]}). Any per-capita quantity has a moving "
            f"denominator, and any across-day trend computed against a fixed n is "
            f"partly measuring attrition. meta['census'] is the per-day count.")
    return log, meta


def _reps(w: float, mode: str) -> int:
    if mode == "binary":
        return 1
    r = int(round(w))
    return max(1, min(r, 1000))          # a weight is data; 1000 copies is a bug


def write_log(log: list[dict], meta: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "interaction_log.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sender", "recipient", "mtype", "tbin"])
        for m in log:
            w.writerow([m["sender"], m["recipient"], m["mtype"], m.get("tbin", 0)])
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--colony", default=None,
                    help="col1..col6 (matrix labels) or behavior:4 / 18 / 21 / "
                         "29 / 58 / 78 (behaviour-table labels). A bare '4' is "
                         "refused as ambiguous: behaviour colony 4 is col1.")
    ap.add_argument("--node-namespace", choices=("behavior", "matrix"),
                    default="behavior",
                    help="behavior (default): emit {colony}:{tag} keys that join "
                         "to behavior.csv, after re-deriving the correspondence "
                         "from the deposit. matrix: emit col{N}:{ant}, which "
                         "joins to nothing and cannot mislabel anything.")
    ap.add_argument("--pool", action="store_true",
                    help="allow several colonies in one graph -- see the error "
                         "message you get without it")
    ap.add_argument("--self-loops", choices=("drop", "keep"), default="drop")
    ap.add_argument("--weight", choices=("binary", "repeat"), default="binary")
    ap.add_argument("--min-weight", type=float, default=0.0)
    ap.add_argument("--max-files", type=int, default=None)
    a = ap.parse_args()

    log, meta = load(Path(a.raw), a.colony, a.pool, a.self_loops, a.weight,
                     a.min_weight, a.max_files, a.node_namespace)
    write_log(log, meta, Path(a.out))
    print(f"\n  mersch networks: {meta['colonies']}")
    print(f"    matrices    : {meta['n_matrices']}"
          + (f"  ({meta['n_matrices_unreadable']} unreadable)"
             if meta["n_matrices_unreadable"] else ""))
    print(f"    days        : {meta['n_timebins']}  {meta['day_range']}")
    print(f"    edges       : {meta['n_edges_undirected']} undirected "
          f"-> {meta['n_messages']} records")
    print(f"    self-loops  : {meta['n_self_loops']} ({meta['self_loops']})")
    cen = meta["census"]
    if cen:
        print(f"    census      : {cen[0]['n']} on day {cen[0]['day']} "
              f"-> {cen[-1]['n']} on day {cen[-1]['day']}")
    if meta.get("denominator_warning"):
        print(f"    NOTE: {meta['denominator_warning']}")
    if meta["joinable_to_behavior_csv"]:
        print(f"    colony map  : {meta['colony_map']} (re-derived from the files "
              f"this run, not read from a constant)")
        print(f"    unlabelled  : {meta['n_unlabelled_nodes']} tracked ants have no "
              f"row in behavior.csv -- kept in the graph, excluded from any task "
              f"cross-tab: {meta['unlabelled_nodes']}")
    else:
        print(f"    NOT joinable to behavior.csv: {meta['colony_map_note'][:70]}...")
    print(f"    CAVEAT      : {meta['census_vs_published_band']}")
    print(f"  written: {Path(a.out) / 'interaction_log.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
