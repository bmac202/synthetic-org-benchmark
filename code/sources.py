"""Registry of the public datasets for the Hives-to-Hierarchies project.

Nothing here is hard-coded to a filename. Zenodo and Dryad records are resolved
through their APIs at download time, so if a depositor adds or renames a file
we pick it up instead of silently missing it.

TIERS
  core   ~750 MB  small, task-labelled, immediately usable
                  (~150 MB of data + a 580 MB btools source clone; `--no-git`
                   skips the clone and brings core down to ~150 MB)
  main    ~18 GB  core + BeesBook 2018 + the mid-size ant sets   <-- default
  full   ~220 GB  everything, including BeesBook 2019 (141 GB)

KINDS
  zenodo / dryad / direct   downloadable now
  git                       cloned with git
  pending                   we know exactly what we want and where it will live,
                            but it is not publicly available yet. The fetcher
                            writes a REQUEST.txt saying who to ask and counts it
                            separately from both "complete" and "failed", because
                            it is neither.
"""

SOURCES = [
    # ------------------------------------------------------------------ core
    dict(
        key="gernat_trophallaxis",
        tier="core",
        kind="zenodo",
        record="5582780",
        concept_doi="10.5281/zenodo.5582779",
        title="Gernat et al. — directed trophallaxis events, ~1000 barcoded bees/colony",
        cite="Gernat, T., Jagla, T., Jones, B. M., Middendorf, M., & Robinson, G. E. (2023). Scientific Reports, 13, 1541.",
        license="CC-BY-NC-4.0",
        approx_bytes=15_000_000,
        why="Directed sender->receiver interaction log. Feeds the structure-recovery instrument unchanged.",
    ),
    dict(
        key="illinois_portal",
        tier="core",
        kind="direct",
        urls=[f"https://beemonitoring.igb.illinois.edu/trial{i}.zip" for i in range(1, 6)],
        title="Robinson lab bee-monitoring portal — five temporal interaction networks",
        cite="Gernat, T., et al. (2018). PNAS, 115(7), 1433-1438.",
        license="see portal",
        approx_bytes=40_000_000,
        # Was described here as "independent trials for replication". They cannot
        # replicate anything directional: the header is trial,id1,id2,begin,end
        # with no direction column, so these five trials replicate STRUCTURE and
        # not flow. What they add that the Zenodo deposit lacks is begin/end --
        # an interval per interaction, i.e. contact DURATION. Read as
        # duration-weighted undirected edges that is an asset; read as a
        # timestamp by bolting `begin` onto the time-candidate list, every event
        # lands in bin 0 and the temporal analysis quietly evaporates.
        why="Undirected companion networks to the PNAS 2018 paper: structural replication only. "
            "Each row carries an interaction interval (begin/end), so contact duration is "
            "available here and not in the Zenodo deposit.",
    ),
    dict(
        key="mersch_keller_2013",
        tier="core",
        kind="dryad",
        doi="10.5061/dryad.8d8h7",
        title="Mersch, Crespi & Keller — 6 ant colonies, 805 tagged workers, 41 days",
        cite="Mersch, D. P., Crespi, A., & Keller, L. (2013). Science, 340(6136), 1090-1093.",
        license="CC0-1.0",
        approx_bytes=37_000_000,
        # Three corrections, the third one to a correction. The worker count was
        # 985 here and is 805 in behavior.csv. The labels are not one static
        # assignment: they are four, stored WIDE as group_period1..4.
        #
        # And the change figure written here first -- 596 of 805, 74% -- was
        # wrong, on the same missing-value mistake it was meant to guard against.
        # 807 cells across those four columns are blank, and a blank counts as a
        # distinct "value": an ant present in periods 1-2 and gone by 3 has two
        # of them and changed nothing. Restricted to the 392 ants labelled in
        # every period, 183 change group -- 47%, not 74%. Quote 183/392, and
        # quote the denominator with it, because those 392 are the ants that were
        # scoreable throughout and are therefore not a random half of the colony.
        #
        # The deposit also ships 246 daily network matrices (6 colonies x 41
        # days, square, symmetric, verified) and a nested tracking_data.zip
        # inside the Dryad bundle. Its two colony vocabularies do not match:
        # behavior.csv says 4/18/21/29/58/78, the matrix filenames say col1..6,
        # and the correspondence is stated nowhere in the deposit or the paper.
        #
        # RESOLVED, from the deposit itself. Strip the `Ant` prefix from the
        # matrix headers and both files name ants with the same integers. For
        # each behavioural colony exactly one matrix column contains ALL of its
        # ants, each column claimed exactly once, the runner-up missing 26 to 49:
        #   4 -> col1, 18 -> col2, 21 -> col3, 29 -> col4, 58 -> col5, 78 -> col6
        # This mattered more than a naming nuisance because 218 of the 222 tag
        # ids occur in more than one colony, so a wrong pairing relabels animals
        # instead of failing. loaders/mersch_map.py re-derives it on every load
        # and raises if it does not reproduce; the constant is a tripwire.
        #
        # The first attempt at this comparison matched the ids as printed --
        # "Ant4" against "4" -- and returned an overlap of exactly 0.0 on all 36
        # colony pairs. A join that matches nothing is a disguised failure, and
        # that zero was a fact about the comparison, not about the deposit.
        #
        # Two things travel with the mapping. Seventeen tracked ants (2-3 per
        # colony: 599, 614, 621, 647, 650, 663, 665, 673, 929, 954) appear in the
        # matrices and have no row in behavior.csv, so they have no task label
        # and must be excluded from any task cross-tab rather than carried into
        # it as a fifth category. And the censuses do not match the paper: it
        # states 122-192 workers per colony, while TWO of six matrix node counts
        # and two of six behavioural censuses fall below that floor
        # (behaviour: 99, 110, 128, 149, 157, 162 including one queen each, so
        # 98-161 workers; matrices: 102, 113, 131, 152, 160, 164). An earlier
        # version of this comment said four of six, which was a miscount.
        # The mismatch is a downward shift at both ends rather than a floor
        # problem -- the largest colony here has 161 workers against a published
        # ceiling of 192. The SI's edge-filtering explanation is ruled out: it
        # predicts matrices smaller than the census (they are three larger), and
        # the networks measure raw anyway (density 70.0% vs the SI's 72+/-5.3%
        # raw and 24.6+/-5.8% filtered; isolates <=3 per colony-day against the
        # 17-48 filtering is said to strand). Unexplained, best candidate dead --
        # do not report a Mersch colony size without that caveat.
        #
        # behavior.csv has CR-only line endings. Anything splitting on "\n"
        # reads all 805 rows as one line; open with newline=None.
        #
        # ONE CORRUPT AGE. In 'age(days)' a single nurse row carries 39155,
        # which is 107 years and cannot be an ant. Read as an Excel date serial
        # on the 1899-12-30 epoch it is 2007-03-14, so the likely story is an
        # eclosion DATE that leaked into an age column. It is one cell out of
        # 805 and it is not harmless: it lifts the nurse mean age from 66.0 to
        # 182.7 days on its own, which is enough to inverse the published
        # nurse -> cleaner -> forager age ordering and make the deposit look
        # like it contradicts the paper. It does not. On medians the ordering
        # is nurses 50, cleaners 78, foragers 102 -- the paper's trajectory,
        # intact. Filter ages above ~2000 days for workers before aggregating.
        #
        # More generally every count column here is heavily right-skewed and
        # the means are not where the mass is. visits_to_rubbishpile has a
        # cleaner mean of 14.9 against a cleaner MEDIAN of 2. Report medians
        # and quartiles for these columns, or report a mean only next to the
        # median that shows what the tail is doing to it.
        why="The canonical dataset WITH per-individual task labels (nurse/cleaner/forager/queen), "
            "assessed FOUR times across the 41 days in wide group_period1..4 columns. Division of "
            "labour ground truth, and — because 183 of the 392 fully-labelled ants (47%) change "
            "group — a calibration set for task re-allocation without a manipulation.",
    ),
    # ------------------------------------------------- human comparison leg
    # Added 13 August 2026. These are the HUMAN cell of the four-substrate
    # comparison, and they were chosen for licence as much as for content:
    # both InVS deposits are CC0, so a public artifact repository can ship
    # loaders AND derived measures without a share-alike clause propagating.
    # The SocioPatterns hospital-ward dataset has richer role labels (nurse /
    # physician / administrative / patient) but is CC BY-NC-SA 3.0, which would
    # infect anything we redistribute; if it is ever added, fetch it, never
    # vendor it.
    dict(
        key="sociopatterns_workplace_2013",
        tier="core",
        kind="direct",
        urls=["https://sociopatterns.org/assets/data/workplace_InVS_tij.dat.zip",
              "https://sociopatterns.org/assets/data/workplace_InVS_metadata.txt"],
        title="SocioPatterns InVS 2013 — face-to-face contacts in an office building",
        cite="Genois, M., et al. (2015). Network Science, 3, 326.",
        license="CC0",
        approx_bytes=160_000,
        # Neither SocioPatterns deposit publishes checksums, so adoption can
        # verify size only. That is weaker than the Dryad path and should be
        # said wherever these files are described.
        # Same data TYPE as the ant contact logs: timestamped dyadic contacts
        # between individually identified members, at 20-second resolution, over
        # ten days (24 June - 3 July 2013). The metadata file is one line per
        # person giving department affiliation, which is the functional-unit
        # label the division-of-labour measure needs. That the instrument can
        # run unchanged on this and on Richardson's ant contacts is the whole
        # reason the human leg is affordable.
        #
        # THE TIMESTAMPS ARE RELATIVE, NOT UNIX -- true of both InVS deposits.
        # Column 1 is seconds from an arbitrary origin near zero: this file runs
        # 20 to 986,440, the 2015 one to 993,580. Anything that formats them as
        # epoch seconds prints 1970 and dates every contact to the first fortnight
        # of it. The calendar window above (24 June - 3 July 2013) comes from the
        # PAPER and cannot be recovered from the deposit, so a loader that needs
        # wall-clock dates has to carry the offset as an external constant rather
        # than read it. Same class of error as `begin` in illinois_portal: the
        # column is a real time and the arithmetic on it silently means something
        # else. What IS recoverable, and verified: every timestamp is a multiple
        # of 20 s, and the records fall on 10 distinct days in both years.
        #
        # Verified 14 August against the downloaded files: 9,827 contact records,
        # 92 people, 5 departments (DISQ, DMCT, DSE, SFLE, SRH). Unlike 2015,
        # all 92 labelled people also appear in the contact file, so the two
        # candidate denominators coincide here and a per-person rate is
        # unambiguous. Do not carry the 2015 denominator caveat over to this one.
        why="Human contact network with per-individual department labels, CC0. "
            "The human cell of the four-substrate comparison.",
    ),
    dict(
        key="sociopatterns_workplace_2015",
        tier="main",
        kind="direct",
        urls=["https://sociopatterns.org/assets/data/workplace_InVS15_tij.dat.gz",
              "https://sociopatterns.org/assets/data/workplace_InVS15_metadata.txt"],
        title="SocioPatterns InVS 2015 — office building, second deployment",
        cite="Genois, M., & Barrat, A. (2018). EPJ Data Science, 7, 11.",
        license="CC0",
        approx_bytes=240_000,
        # CORRECTED 13 August after reading the files. This is NOT a clean
        # replication of the 2013 deployment and must not be described as one.
        # Same building, but a substantially larger and partly different
        # population: 232 people in 12 departments against 92 in 5, and 78,249
        # contact records against 9,827. Five departments appear in both
        # (DSE, DMCT, DISQ, SRH, SFLE); DMI, DST, DCAR, SSI, SCOM, SDOC and DG
        # are new in 2015. So it gives a second human observation under partly
        # overlapping conditions, which is weaker than a noise floor and still
        # worth having.
        # Note also: 232 people carry a department label but only 217 ever
        # appear in the contact file. Any per-person rate must state which of
        # those two is its denominator. This is a 2015 problem SPECIFICALLY --
        # in 2013 all 92 labelled people are observed in contact, so the gap is
        # not a property of the instrument or of the building. The gap is also
        # one-directional: no id appears in either contact file without a
        # metadata row, so every observed contact is labelled and it is only the
        # roster that overshoots.
        #
        # Timestamps here are relative too, not unix -- see the 2013 entry for
        # what that breaks. This file also arrives GZIPPED where the 2013 one is
        # a zip the fetcher unpacks to a plain .dat, so a loader must open the
        # two differently.
        #
        # Verified 14 August against the downloaded files: 78,249 contact
        # records, 232 labelled people, 217 observed, 12 departments, 10 distinct
        # days, 20 s resolution.
        why="Second, larger deployment in the same building. A second human "
            "observation under overlapping but not identical conditions.",
    ),
    dict(
        key="charbonneau_dornhaus_2017",
        tier="core",
        kind="dryad",
        doi="10.5061/dryad.77110",
        title="Charbonneau & Dornhaus — worker-removal experiment, Temnothorax rugatulus",
        cite="Charbonneau, D., Poff, C., et al. / Charbonneau, D. & Dornhaus, A. (2017). Behavioral Ecology and Sociobiology.",
        license="CC0",
        approx_bytes=200_000,
        why="The ONLY open dataset that is literally a re-allocation experiment: an exogenous workforce shock with per-individual task data on both sides. This is the flexibility measure with real ground truth.",
    ),
    dict(
        key="george_frank_2026_code",
        tier="core",
        kind="pending",
        url="https://github.com/EbiAG/wound-care-interaction-networks",
        doi="10.1073/pnas.2614400123",
        preprint="10.1101/2025.10.08.681151",
        contact="Ebi Antony George / Erik T. Frank (Univ. Würzburg)",
        title="George, Motes-Rodrigo, Keller & Frank — wound-care interaction networks (perturbation + task labels)",
        cite="George, E. A., Motes-Rodrigo, A., Keller, L., & Frank, E. T. (2026). "
             "Social and spatial affinity drive wound care by ants. PNAS. doi:10.1073/pnas.2614400123",
        license="unspecified — check before redistributing",
        approx_bytes=0,
        blocked=(
            "The repository URL is correct — it is the one named in the paper's data "
            "availability statement — but GitHub serves it as 404 to unauthenticated "
            "clients, which is what it does for a PRIVATE repository. git then falls "
            "back to asking for a username, which is the error you saw. This is NOT a "
            "problem with your GitHub credentials: no personal account can clone a repo "
            "it has not been granted access to. The fix is an email to the authors "
            "asking them to make the deposit public (or to share it directly), not "
            "`gh auth login`. Re-run this script after they respond."
        ),
        why="Amputation/infection shock WITH nurse/forager/transitioning labels. Functionally the open substitute for the restricted Stroeymeyt 2018 data. The paper's own finding — wound care performed by a non-specialized subset whose behaviour sits between nurse and forager, allocated by prior spatial and social proximity to the injured — is directly on the proposal's 'role differentiation without role assignment' thread.",
    ),
    dict(
        key="btools",
        tier="core",
        kind="git",
        url="https://github.com/gernat/btools",
        title="bCode barcode tracking toolchain (Gernat)",
        cite="Gernat et al.",
        license="AGPL-3.0",
        # Measured, not estimated: 582 MB on disk after --depth 1. The working
        # tree carries large res/ assets, so shallow history does not help much.
        approx_bytes=610_000_000,
        why="Reference implementation for how the trophallaxis events were derived. Read the detector logic before trusting the events.",
    ),

    # ------------------------------------------------------------------ main
    dict(
        key="beesbook_2018",
        tier="main",
        kind="zenodo",
        record="6045860",
        concept_doi="10.5281/zenodo.6045860",
        title="BeesBook — honey bee lifetime tracking 2018: 4,242 bees, 85 days",
        cite="Smith, M. L., Davidson, J. D., Wild, B., Dormagen, D. M., Landgraf, T., & Couzin, I. D. (2022). iScience, 25(9), 104842.",
        license="CC-BY-4.0",
        approx_bytes=11_700_000_000,
        why="The honey bee dataset at the scale the specialization x flexibility bench needs. Positions, headings, age, lifespan; roles derived from spatial zone or network age.",
    ),
    dict(
        key="alciatore_2021",
        tier="main",
        kind="dryad",
        doi="10.5061/dryad.wwpzgmshb",
        title="Alciatore et al. — immune challenge in clonal raider ants, individual behaviour",
        # The deposit's own title, read off the Dryad API on 31 July. Recorded
        # because it is not what our `title` above says, and the difference
        # matters: the authors' stated outcome is a change in *network
        # centrality*, which is our other axis. Whatever this deposit turns out
        # to support, it is not only a flexibility instrument. `title` is what we
        # want from it; `deposit_title` is what its authors say it is.
        deposit_title="Immune challenges increase network centrality in a queenless ant",
        cite="Alciatore, G., Ugelvig, L. V., Frank, E., et al. (2021). Immune challenges increase network centrality in a queenless ant. Proceedings of the Royal Society B. doi:10.1098/rspb.2021.1456",  # journal corrected 16 Oct from the deposit readme
        license="CC0",
        # 4,894,312,027 (AlciatoreEtAl_2021.zip) + 31,322 (README.pdf), Dryad version 144593
        approx_bytes=4_894_343_349,
        why="Perturbation (Zymosan vs PBS vs naive) plus individual behaviour and manually coded grooming. Independent replication of shock-and-recover.",
    ),
    dict(
        key="kay_2024",
        tier="main",
        kind="dryad",
        doi="10.5061/dryad.dfn2z358r",
        title="Kay et al. — five ant species, per-individual forage/nest assignment",
        cite="Kay, T., Alciatore, G., Keller, L., et al. (2024). Proceedings of the Royal Society B.",
        license="CC0",
        approx_bytes=1_040_000_000,
        why="Cross-species comparison with per-individual task assignment. Tests whether the instrument travels between species, not just between colonies.",
    ),
    dict(
        key="richardson_2021",
        tier="main",
        kind="dryad",
        doi="10.5061/dryad.15dv41nv0",
        title="Richardson et al. — 3 colonies, >500 tagged ants, >100 days, continuous social maturity",
        # As above: the deposit's own title, Dryad API, 31 July, version 112697.
        # "behavioral maturation" and "two fundamental states" both bear directly
        # on the nurse -- cleaner -- forager result, and the second one is a
        # claim we would otherwise be testing without knowing the authors had
        # already made it. Read their README before assuming our three labels are
        # cuts through their continuum.
        deposit_title="Ant behavioral maturation is mediated by a stochastic transition between two fundamental states",
        cite="Richardson, T. O., Kay, T., Braunschweig, R., et al. (2021). Current Biology, 31(12), 2720-2727.",
        license="CC0",
        approx_bytes=390_749_381,   # exact, Dryad version 112697
        why="Long-duration continuous role state (nurse<->forager). The best open test of whether specialization is stable or drifting.",
    ),

    # ------------------------------------------------------------------ full
    dict(
        key="beesbook_2019",
        tier="full",
        kind="zenodo",
        record="7298798",
        concept_doi="10.5281/zenodo.7298798",
        title="BeesBook — honey bee lifetime tracking 2019: 9,135 bees, 115 days",
        cite="Wild, B., Dormagen, D. M., et al. (2021). Nature Communications, 12, 1110.",
        license="CC-BY-4.0",
        approx_bytes=141_000_000_000,
        why="The full lifetime record. Only needed once the pipeline works on 2018.",
    ),
    dict(
        key="richardson_2022",
        tier="full",
        kind="dryad",
        doi="10.5061/dryad.9w0vt4bjb",
        title="Richardson & Keller 2022 — spatial modules, 21.6 GB",
        cite="Richardson, T. O., et al. (2022).",
        license="CC0",
        approx_bytes=21_600_000_000,
        why="Fine-grained spatial data; use only if zone-based task definition needs refinement.",
    ),
    dict(
        key="antrax_benchmark",
        tier="full",
        kind="zenodo",
        record="3740547",
        concept_doi="10.5281/zenodo.3740547",
        title="anTraX benchmark — 7 ant tracking sets (IDs + trajectories, no task labels)",
        cite="Gal, A., Saragosti, J., & Kronauer, D. J. C. (2020). eLife, 9, e58145.",
        license="CC-BY",
        approx_bytes=44_800_000_000,
        why="Method benchmark only. No behavioural annotation, so of limited use to us.",
    ),
]

TIER_ORDER = {"core": 0, "main": 1, "full": 2}


def select(tier: str):
    """Return every source at or below the requested tier."""
    if tier not in TIER_ORDER:
        raise SystemExit(f"unknown tier {tier!r}; choose from {list(TIER_ORDER)}")
    ceiling = TIER_ORDER[tier]
    return [s for s in SOURCES if TIER_ORDER[s["tier"]] <= ceiling]
