# Data sources and licences

None of the raw data below is stored in this repository. Scripts fetch each source from its
original deposit; `code/sources.py` records the exact files, sizes and DOIs.

| Group in Figure 1 | Source | Licence | How to get it |
|---|---|---|---|
| Clonal ants, no queen | Alciatore et al. (2021), *Proceedings of the Royal Society B*; Dryad doi:10.5061/dryad.wwpzgmshb | CC0 | `fetch_data.py --only alciatore_2021` (about 4.9 GB) |
| Ants with a queen | Mersch, Crespi & Keller (2013), *Science* | CC0 | `fetch_data.py --tier core` |
| Honey bees | Gernat et al. (2018), *PNAS* | CC BY-NC 4.0 | `fetch_data.py --tier core` |
| Office workers | Génois et al. (2015), *Network Science*; Génois & Barrat (2018), *EPJ Data Science*; SocioPatterns | CC0 | `fetch_data.py --only sociopatterns_workplace_2013 sociopatterns_workplace_2015` |
| Online game players | OpenDota match dump, March 2011 to March 2016 (Cui, Chung & Hanson-Holtry 2017) | CC BY-SA 4.0 | `data/dota_sample/get_dota_sample.py` |
| Lab economies | Kimbrough, Smith & Wilson (2008), *American Economic Review*; openICPSR 113239 | CC BY 4.0 | download the zip from openICPSR, then `get_kimbrough_data.py` |
| LLM agents with self-written memory | Takata et al. (2024), *Entropy* 26(12), 1092 | shared privately | from the original authors on request; not redistributed |

The stored synthetic runs in `code/diffenv_results/` were produced for this project and are
released under CC BY 4.0.
