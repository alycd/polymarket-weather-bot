---
name: followups-tracker
description: "When the user asks \"what do we need to follow up on\", read docs/plans/FOLLOWUPS.md — the living tracker of dated forward-test reviews, canary steps, and trigger-based items"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6afd0c7b-28ef-4b19-9599-d29e9e92743b
---

The user maintains follow-ups in `docs/plans/FOLLOWUPS.md` (created 2026-06-12, commit d2898ce): a dated table of forward-test reviews (T+1 std gate ~06-16; accuracy guards + low-price relaxation ~06-23; exit-liquidity phase 2 ~06-26), blocked rollout steps (live micro-canary awaiting ~$50-100 deposit; held_to_resolution watch = canary + 2 weeks), and trigger-based items (WU/ASOS boundary analysis, Warsaw city watch).

**Why:** review dates were previously scattered across memory notes and plan docs; the user wants one place they can ask about ("what do we need to follow up on?") and that survives in the repo.

**How to apply:** when asked about follow-ups, Read `docs/plans/FOLLOWUPS.md`, compare due dates against today's date, and report overdue + upcoming items with their actions and source docs. Keep it current: when a forward test or canary step ships, ADD a row; when an item is completed, MOVE it to the Done section with outcome + commit ref (never delete), update the "Last updated" date, and commit. Related: [[tplus1-leadtime-regime-split]], [[exit-liquidity-sizing-phase1]], [[live-execution-integrity-spec]], [[payoff-asymmetry-levers-exhausted]].
