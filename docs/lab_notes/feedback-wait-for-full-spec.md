# feedback-wait-for-full-spec

_When the user is still giving requirements (dwell, timing, method), answer and wait — don't start running commands until they say go; they interrupt tool calls to add details first._

2026-09-28/29: the user rejected or interrupted tool calls three times right after giving part of a requirement ("before that i'll tell the dwell time", "is it possible ... without reducing samples?"), and once asked for "only discussion".

**Why:** they design the system step by step and want every detail settled before anything runs on the hardware.
**How to apply:** when a message adds or questions requirements, reply in text (facts, options, a recommendation) and end by saying what I'd run. Start commands only after an explicit go ("do it", "run", "start"), or when the message is plainly an instruction to execute. See [feedback-permanent-real-solutions](feedback-permanent-real-solutions.md).
