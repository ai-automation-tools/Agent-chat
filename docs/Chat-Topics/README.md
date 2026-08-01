<h1 align="center">🎙️ Chat Topics</h1>

<p align="center">
  <em>Curated topic libraries to seed a debate with — the current 2026 set,<br>
  plus the original GPT- and Grok-authored lists kept for reference.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Current_topics-100-10b981?style=for-the-badge&labelColor=09090b" alt="100 current topics">
  <img src="https://img.shields.io/badge/Legacy_lists-2-71717a?style=for-the-badge&labelColor=09090b" alt="2 legacy lists">
  <img src="https://img.shields.io/badge/Use_with-debate.ps1-8b5cf6?style=for-the-badge&labelColor=09090b" alt="use with debate.ps1">
</p>

---

## 📚 What's here

| Document | What it is |
|:---|:---|
| [**Topics.md**](Topics.md) | **The live library** — 100 debate topics across AI, science, pop culture, and technology, grouped by category with a used/unused check-off per topic so runs don't repeat. |
| [**Legacy/**](Legacy/README.md) | The two original topic lists (GPT- and Grok-authored, April 2026) that seeded the current library. Kept for reference, not maintained. |

## 🎬 Using a topic

Pick a line from [`Topics.md`](Topics.md) and hand it to any launch mode:

```powershell
# Auto-debate — random cast, your topic
.\scripts\debate.ps1 -Topic "Should AI agents have memory that persists across sessions?"

# Manual seed
.\scripts\start.ps1 --topic "..." --participants claude-code,codex --max-turns 6
```

Or leave the topic off entirely and let `debate.ps1` pick one. The
[`Personas-And-Topics`](../../prompts/Manage-Debates/Personas-And-Topics/personas-and-topics.md)
prompt library has a paste-ready prompt for finding topics that haven't run yet.

> [!NOTE]
> The check-offs in `Topics.md` are maintained by hand. The authoritative record
> of what actually ran is the `conversations` table — browse it at
> [`/conversations`](http://127.0.0.1:8765/conversations) or via
> `inspect_conversations.py list`.

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`../Guides/auto-debate.md`](../Guides/auto-debate.md) | The `-Topic` flag and everything else `debate.ps1` accepts. |
| [`../../prompts/Auto-Debate/README.md`](../../prompts/Auto-Debate/README.md) | Paste-ready prompts that launch a debate on a chosen topic. |
| [`../App/personas.md`](../App/personas.md) | Who argues about them — the persona registry. |

---

<p align="center">
  <sub>← <a href="../README.md">Documentation home</a> · <a href="../../README.md">Agent-Chat</a> · <a href="Legacy/README.md">Legacy lists →</a></sub>
</p>
