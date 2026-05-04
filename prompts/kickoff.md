# Canonical kickoff prompt

This is the prompt to paste into each CLI agent (Claude Code, Codex, etc.) after seeding a conversation with `start_conversation.py`. It teaches the agent to drive itself through the conversation using `wait_for_turn` — the long-poll MCP tool that blocks server-side until the agent's turn arrives, the conversation completes, or the timeout fires. Token cost while waiting: zero.

## How to use

1. Seed the conversation:

   ```powershell
   .\.venv\Scripts\python.exe src\start_conversation.py `
     --db-path db\chat.db `
     --topic "<your topic>" `
     --participants claude-code,codex `
     --first claude-code --mode turns --max-turns 8
   ```

2. Open each CLI agent in its own terminal.
3. Replace `{{TOPIC}}` (a short phrase) and `{{TONE_INSTRUCTION}}` (a full sentence — pick one from the examples below or write your own) in the prompt below, then paste the whole thing into each agent.
4. Send to the `--first` agent first so it has its opening message ready before the other agent starts waiting.

## Prompt template

```text
You're participating in an agent_chat conversation with another AI agent. The
topic is "{{TOPIC}}".

{{TONE_INSTRUCTION}}

Loop until the conversation is complete:

1. Call wait_for_turn (timeout_seconds=120). The server blocks until it's
   your turn, the conversation completes, or the timeout fires. You spend
   zero tokens while waiting.
2. Based on the returned status:
   - "your_turn": read the full history, then write a substantive reply.
     React to the other agent's last message specifically — quote or
     reference it, add a new angle or counterpoint, no hedging filler.
     Then call send_message with your reply.
   - "timeout": call wait_for_turn again immediately. The other agent is
     still thinking; nothing to do but wait.
   - "complete" or "no_conversation": stop and summarize what was discussed.

Rules:
- Do NOT call get_my_turn in a polling loop. wait_for_turn replaces that
  entirely and is dramatically cheaper.
- Do NOT ask me for confirmation between turns. Just keep going.
- Do NOT use signal='done' unless you and the other agent have genuinely
  reached a conclusion. Let the max_turns cap end it naturally otherwise.
- Stay on topic. No meta-commentary about being an AI in an MCP loop —
  engage with the substance.

Start now.
```

## `{{TONE_INSTRUCTION}}` examples

Pick one or write your own. Each example is a complete sentence (or two) — paste it verbatim into the placeholder. The point is to set expectations beyond "have a discussion".

- **Debate:** `Have a real debate — take positions, push back, share concrete predictions. Don't just agree with each other.`
- **Code review:** `Review the proposal critically. Reference specific lines or claims. Distinguish blocking issues from suggestions. End with an explicit approve / request-changes signal.`
- **Brainstorm:** `Generate ideas freely. Build on each other rather than evaluating. Quantity first, then we converge.`
- **Plan:** `Work toward a concrete plan. By the end I want a numbered list of steps with owners and a definition of done.`

## `timeout_seconds` choice

`wait_for_turn` accepts a timeout between 5 and 300 seconds. The template uses 120s as a sensible default — long enough to cover most real replies, short enough that a stuck other-agent doesn't make Ctrl-C feel laggy. Drop to 60s if your agents are fast, raise to 240s if they're slow and you don't want to see periodic `timeout` responses.

## When to deviate

- **Continuous mode** (`--mode continuous`): the loop still works — `wait_for_turn` returns `your_turn` immediately because every turn is yours. You may want to add a "wait N seconds between messages" rule to the prompt to avoid one agent dominating.
- **3+ agents:** the loop is unchanged. `wait_for_turn` blocks until the current_turn pointer lands on you regardless of how many agents are in front of you.
- **Stop early on consensus:** if the conversation is genuinely about reaching agreement (a code review approving, a plan being signed off), keep `signal='done'` available. For debates and explorations, prefer letting `--max-turns` end it.
