# Review & Export (read back and save a finished debate)

Prompts for reviewing a completed debate, summarizing it, and exporting it as
Markdown. The web UI serves a single-file Markdown export and a multi-file `.zip`
bundle per conversation.

> Export endpoints (local web UI on port 8765):
> - `GET /api/conversations/<id>/export.md` — single Markdown file
> - `GET /api/conversations/<id>/export.zip` — bundle (`topic.md` + `transcript.md` + metadata)

## 1. Summarize who won

```text
Read the full transcript of conversation #<id> (inspect_conversations.py show <id>)
and give me a neutral recap: each persona's core argument, the strongest point
made, and where the debate landed.
```

## 2. Export one debate to Markdown

```text
Export conversation #<id> as Markdown. Give me the local download link
(http://127.0.0.1:8765/api/conversations/<id>/export.md) and confirm the web UI is
up so the link works.
```

## 3. Grab the full bundle

```text
Give me the .zip export link for conversation #<id>
(http://127.0.0.1:8765/api/conversations/<id>/export.zip) — the bundle with the
topic overview, transcript, and metadata.
```

## 4. Compare two debates on the same topic

```text
Conversations #<idA> and #<idB> covered similar topics. Show both transcripts and
compare how the different personas/CLIs handled the same question.
```

## 5. Pull a highlight reel

```text
From conversation #<id>, pull the 5 best quotes — the sharpest, funniest, or most
in-character lines — and attribute each to its persona.
```
