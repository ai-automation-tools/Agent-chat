# Persona card template

`Agent-Personality.md` is the canonical format for a debate persona. Copy it,
fill every `[bracketed]` slot, rename to `<slug>.md` (lowercase-with-hyphens),
and either drop it in a group folder under `agents/Debate-Agents/` or import it
from the `/personas` page.

To have **another AI agent generate** personas for you, paste
[`GENERATE-Persona-Prompt.md`](GENERATE-Persona-Prompt.md) at it — that file is a
self-contained brief (rules + template + a worked example + an output contract),
so the agent needs nothing else.

## Two consumers, one format

Every card is read two different ways, and the template is shaped to serve both:

1. **The parser** reads **only the YAML frontmatter** for `tags` / `category` /
   `subcategory`, and the **`## Purpose`** line for the roster `summary`. It does
   **not** read tags or category from the body — an inline `**Tags:** #x #y` line
   is just decorative text.
2. **The model** reads the **entire body** (everything after the frontmatter) as
   its persona prompt.

## The body is freeform — only the frontmatter is a contract

The parser reads structure from **nothing** in the body. The `##` sections and
the `## Persona` bullet list are convention, not schema — add traits, drop them,
rename them, or restructure the whole body per persona, and the card still
imports. The bullet menu in the template (Voice, Debate style, You believe,
Intelligence, Strengths, Weaknesses, Decision framework, Favorite topics, You
avoid) is a *starter set*: keep what fits the character, cut what doesn't, invent
new ones. The only two body conventions worth keeping consistent are
`## Purpose` (so the roster `summary` is deterministic) and a second-person
opening (so the model speaks *as* the persona — see below).

## The two rules that matter

- **Frontmatter must be the very first bytes of the file.** Anything before the
  opening `---` (even a comment) makes the parser treat the whole file as body
  and silently drop `title` / `tags` / `category` / `summary`. Keep the
  frontmatter at byte 0.
- **Write the body in the second person, as an instruction** — *"You are X. You
  believe… You speak…"* — not a third-person bio. The model adopts what it is
  told to be; it narrates what it is merely described as.

## Frontmatter notes

- `title` sets the display name (emoji allowed) and wins over the `# Heading`.
- `tags` must be a **block list** (`- item` lines). Inline flow syntax
  (`tags: [a, b]`) is **not** supported by the hand-rolled parser.
- **No YAML `#` comments.** The parser doesn't strip them, so a trailing
  `category: Debaters  # note` imports the comment as part of the value. Keep
  frontmatter values clean.
- `category` / `subcategory` are optional facets — stored and shown, but nothing
  branches on them. The **group** (folder name at seed time, `"group"` column at
  runtime) is the real organizing axis.
- The filename stem becomes the **slug** (the stable id); `title` is just the
  pretty name.

See [`docs/App/personas.md`](../../docs/App/personas.md) → **Card format
standard** for the full rationale and a worked example.

## The two files here

| File | What it is |
|:---|:---|
| [**`Agent-Personality.md`**](Agent-Personality.md) | The canonical persona card template — copy, fill, rename to `<slug>.md`. |
| [**`GENERATE-Persona-Prompt.md`**](GENERATE-Persona-Prompt.md) | A self-contained brief you paste at another AI agent to have it write cards for you. |

---

<p align="center">
  <sub>← <a href="../README.md">Agents</a> · <a href="../../README.md">Agent-Chat</a> · <a href="../../docs/App/personas.md">Persona registry</a></sub>
</p>
