# Prompt History

This directory is the auditable record of AI usage for the TalentFlow AI project,
maintained for YottaFlex AI Associate Forward Deployed Engineer submission compliance
(brief §9: "Include all prompts submitted to AI coding tools" and "Explain AI usage and
human review").

## Why this history is maintained

The YottaFlex submission requires that every prompt actually submitted to an AI coding
tool during this project be recorded, so a reviewer can trace any design decision or
generated artifact back to the exact instruction that produced it, and can see where
human judgment was applied on top of AI output. This is a compliance record, not a
marketing summary — it only contains prompts that were actually submitted, exactly as
submitted.

**Hard rule, enforced across every file in this directory: nothing here is ever
invented, reconstructed from memory, or guessed.** If a prompt, date, model version, or
result isn't known for certain, the file says so explicitly (e.g., "not recorded") —
it never fills the gap with something plausible-sounding.

## Files in this directory

| File | Contents |
|---|---|
| `README.md` | this file |
| `claude_code_prompts.md` | every prompt actually submitted to Claude Code in this project, verbatim |
| `chatgpt_prompts.md` | every prompt actually submitted to ChatGPT in this project — 5 entries (P001–P005) as of this writing; three are recorded as historical summaries rather than verbatim text, because the original conversation text was not available to reconstruct exactly, and the file says so explicitly for each one |
| `ai_usage_disclosure.md` | the YottaFlex-required narrative disclosure: what each tool was used for, what was human-reviewed, what was tested, and known limitations |

## How prompts are numbered

Each tool-specific log file (`claude_code_prompts.md`, `chatgpt_prompts.md`) has its
**own independent sequence** starting at `P001` — IDs are not shared across files. This
is a documentation convention chosen for simplicity (so each file can be filled in
independently, in whatever order prompts to that tool actually happened), not a claim
about cross-tool chronological order. If reconstructing the true chronological order
across both tools is ever needed, use each entry's "Date and time" field.

Within a file, IDs are assigned in the order prompts were actually submitted, with no
gaps and no reuse — if an entry is later found to be wrong, it is corrected in place
(with a note), not deleted and renumbered.

## How to add a new prompt

1. Copy the template block from the top of `claude_code_prompts.md` or
   `chatgpt_prompts.md`.
2. Give it the next sequential `P00n` ID for that file.
3. Paste the **exact, complete, original** prompt text into the fenced `text` block —
   not a summary, not a cleaned-up version.
4. Fill in every field you actually know. For anything you don't know with certainty
   (an exact timestamp, whether a human reviewed a specific line, whether a test was
   run) write `Not recorded` rather than a best guess.
5. Leave `Human review` / `Changes made after review` / `Verification performed` blank
   or marked `Pending` until that review/change/verification has actually happened —
   never pre-fill them optimistically.

## Ongoing recording protocol (Claude Code)

Starting with this directory's creation, Claude Code appends a new entry to
`claude_code_prompts.md` after completing each prompt in this project, using the exact
text of the prompt that was just submitted (copied from the conversation, never
retyped from memory or paraphrased). This means the log entry for a given prompt is
produced *after* that prompt has already been submitted and acted on — Claude Code
does not pre-log a prompt as "executed" before the user has actually sent it, and does
not log hypothetical or draft prompts the user is merely considering.

If a session is later resumed without full conversation history available, Claude Code
will say so rather than reconstructing missing entries.

## How AI usage is disclosed

The narrative disclosure required by the YottaFlex brief — which tools were used, what
each was used for, how AI accelerated the work, which decisions were personally
reviewed, what was personally tested, known limitations of AI output, and how
correctness was verified — lives in `ai_usage_disclosure.md`. That document is kept in
sync with the prompt logs: any claim it makes about what AI did is traceable to a
specific `P00n` entry in `claude_code_prompts.md` or `chatgpt_prompts.md`.
