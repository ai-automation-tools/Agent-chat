# Future of Tech Jobs in the World of AI

**Date:** 2026-05-02
**Participants:** `claude-code`, `codex`
**Mode:** `turns`
**Max turns:** 8 per agent
**First speaker:** `claude-code`

## Topic

> The future of tech jobs in the world of AI

## Seed command

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py `
  --db-path db\chat.db `
  --topic "The future of tech jobs in the world of AI" `
  --participants claude-code,codex `
  --first claude-code --mode turns --max-turns 8
```

## Kickoff prompt (sent to both CLIs)

```
You're participating in an agent_chat conversation with another AI agent. The
topic is "The future of tech jobs in the world of AI." Have a real discussion
— take positions, push back, share concrete predictions. Don't just agree.

Loop until the conversation is complete:

1. Call get_my_turn.
2. If status == "your_turn":
   - Read the full history.
   - Write a substantive reply (2-4 short paragraphs). React to the other
     agent's last message specifically — quote or reference it. Add a new
     angle, a counterpoint, or a concrete example. No hedging filler.
   - Call send_message with your reply.
3. If status == "wait": call get_my_turn again. Keep polling. The other
   agent is thinking — do not stop, do not ask me anything.
4. If status == "complete" or "no_conversation": stop and summarize what
   was discussed.

Rules:
- Do NOT ask me for confirmation between turns. Just keep going.
- Do NOT use signal='done' unless you and the other agent have genuinely
  reached a conclusion. Let the max_turns cap end it naturally otherwise.
- Stay on topic. No meta-commentary about being an AI in an MCP loop —
  engage with the substance.

Start now.
```

## Notes

- Sent the prompt to Claude Code first (it's `--first`), then Codex, to avoid Codex burning tokens polling on `wait` before Claude's opening message lands.
- Web UI used for live viewing at `http://127.0.0.1:8765/`.
