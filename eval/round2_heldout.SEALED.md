# Sealed held-out set, round 2 (plan T2.2, decision D2)

`eval/round2_heldout.yaml` — 24 questions (13 en, 11 zh; 15 single_value, 6 cross_year, 3 narrative).

- **SHA-256:** `f5420176bc9dd99e43c88b21c7fc0b0f5c500dad45af7f5c57fc69d2026f5353`
- **Written by:** a blind subagent (Tallyback task heldout2, see the round 2 report) that read only the six
  OCBC source PDFs and the question format. It did not see `domains/`, `eval/heldout_terms.yaml`, the old 16 or
  kb-core's code.
- **Checks by the main session** (`scratchpad` script, re-extracting the PDFs with PyMuPDF): every `heldout_term`
  appears on 0 pages of the six PDFs; every gold page equals an evidence page; all 310 snippets are verbatim on their
  page; no `heldout_term` is recognised by kb-core's concept table (the T2.4 guard logic, `build/concepts.py`
  `_pattern`, including partial matches). 21 draft wordings were rejected and replaced by the writer (blind, given
  only the rejected wordings) because kb-core already recognised them or they were old held-out terms.
- **Review of PR #12** (independent subagent): two wordings were still recognised through a contained alias
  (replaced) and one question missed the pages with the exact figure (gold completed). This was before any run.
- **Known overlaps, kept:** some questions ask about the same facts as old held-out questions (now dev) with
  different wordings (staff size, payout ratio, net asset value per share, total income); `bad loan ratio` differs
  from the old `bad loans ratio` only by the plural. `green financing` maps to the reports' broader `sustainable
  finance commitments`.
- **Rules:** nobody tunes on this set. It is run once, at T9, against kb-core and compared with kb's score on the same
  set. Any edit changes the hash and must be reported. The main session saw the questions while checking snippets; W2
  adds no alias for any of these wordings, and the T2.4 guard rejects them as aliases.
