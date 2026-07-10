# Debate & Publish (launch → wait → ship to the AI library)

End-to-end prompts: run a debate **and** file it into the
AI-Automation-Library archive (bundle + cover image + git push) in one ask.
Launching alone never publishes — [`start-debate`](../../../skills/start-debate/SKILL.md)
and [`publish-debate`](../../../skills/publish-debate/SKILL.md) are separate
skills by design (the archive is the curation gate). These prompts chain them.

> How the wait works: `debate.ps1` returns as soon as the CLIs are spawned, so
> the assistant polls `inspect_conversations.py list` until the conversation is
> `status='complete'`, then runs the publish workflow (bundle → cover →
> `--push`). Existing category buckets: `Technology` · `Space-&-Science` ·
> `Society-&-Culture` (dynamic — reuse the best fit; confirm brand-new bucket
> names first).

## 1. Head-to-head, published when it ends

```text
Use the start-debate skill to start a head-to-head debate between claude-code and
codex, where claude-code = Steve Irwin and codex = Rick Sanchez. Topic: "Is human
extinction something we should actually worry about?" Then wait for the debate to
complete (poll inspect_conversations.py every minute or so), and when it does, use
the publish-debate skill to publish it to the AI library: pick the best-fitting
category bucket, generate the cover image, and push.
```

## 2. Surprise me, then ship it

```text
Use the start-debate skill to run an auto-debate — random topic, random cast,
surprise me. When the conversation completes, use the publish-debate skill to
file it into the AI library under whichever existing category bucket fits best,
generate the cover image from the master cover prompt, and push the commit.
```

## 3. Publish the debate that just finished

```text
Use the publish-debate skill to publish the most recent completed conversation
to the AI library. Confirm which conversation id that is first, pick the
best-fitting category bucket, generate the cover image, and push.
```

## 4. Publish a specific debate, but let me approve the cover

```text
Use the publish-debate skill to publish conversation #<id> to the AI library
under <Category>. Write the bundle and generate the cover image, then show me
the cover for approval BEFORE running the --push step.
```

## 5. Backfill everything unpublished

```text
Compare completed conversations in chat.db against the Agent-Debates archive in
the AI-Automation-Library and list any completed debates that were never
published. For each one worth keeping, use the publish-debate skill: bundle,
cover image, push. Ask me before creating any new category bucket.
```
