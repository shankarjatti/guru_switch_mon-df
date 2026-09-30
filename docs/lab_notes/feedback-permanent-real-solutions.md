# feedback-permanent-real-solutions

_Defence project — the user wants permanent, root-cause solutions verified on real hardware, never quick fixes, fakes or assumed results, with step-by-step updates._

Rules the user stated (2026-09-28): "don't do any fake thing, it's for defence work, everything should be real"; "choose the good one... solution for permanent, not only for now"; "discuss every step with me, give every stage update".

**Why:** this is defence work; a number that looks right but wasn't measured, or a fix that only works on the bench, is worse than no result.
**How to apply:**
- When there is a quick option and a robust one, pick the robust one and say why (e.g. radio-clock scheduled hopping instead of trimming host sleeps).
- Every "achieved"/"fixed" claim needs a hardware measurement with pass criteria stated up front; report failures and odd data as they are, including my own test bugs.
- Report after every stage in simple English, then continue; ask before design decisions that carry into the final system.
- Take a backup before changing the working setup ([guru-known-good-sources](guru-known-good-sources.md)).
