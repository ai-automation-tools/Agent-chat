# Surprise-Me (let the script decide everything)

Minimal input — the script picks a random **unused** topic from the topic library
(`docs/Chat-Topics/Topics.md`), a random cast across all groups, and the debater
count from the topic's own marker. Good for a hands-off demo run.

## 1. Total random run

```text
Use the start-debate skill to start an auto-debate. Surprise me — pick the topic,
the personas, and the number of debaters all at random. Preview the cast first,
then launch.
```

## 2. Random topic, my CLIs

```text
Use the start-debate skill to start a random debate between claude-code and
codex. Pick the topic and both personas at random.
```

## 3. Random, but make it long

```text
Use the start-debate skill to start a fully random 3-agent debate and make it
12 turns. Pick the topic and the cast at random across all groups.
```

## 4. Random, hands-off

```text
Use the start-debate skill to start a random auto-debate and run it fully
hands-off (skip the tool-approval prompts). Pick everything at random.
```

## 5. Just dry-run a random one

```text
Use the start-debate skill to preview a random auto-debate only — show me the
topic, the persona-to-CLI cast, and the launch plan, but don't open any windows
or seed anything yet.
```
