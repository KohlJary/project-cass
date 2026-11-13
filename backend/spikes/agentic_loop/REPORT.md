# Agentic-loop spike: first results (2026-11-13)

**The question:** should her own time run on the Claude Agent SDK (Claude Code as the harness, free updates) or on our own provider-neutral loop (keeps every model family, which matters for research)? See the 2026-11-13 discussion in `docs/design/agent-loop.md`.

**The setup:** one task, one workspace and one tool set for every run; only the harness and the model differ.
- **The task:** her own time, with an agenda of two threads (review the agent-loop design; understand the Thymos wiring) and source docs in a workspace.
- **Her identity:** the kernel with a generic identity line (no `daemon_id`, so no database reads), plus a "THIS MOMENT" block.
- **Tools:**
  - workspace file tools, fenced to the workspace;
  - `say`, `wake_me` and `done`;
  - her 30 always-on chat tools, directly;
  - the other 229 tools her router can run, through `find_tools` / `use_tool`.
- **Nothing is real:** every call to one of her tools is recorded but not executed. `say` is never delivered. `DATA_DIR` is a scratch directory.

Code: `common.py` (shared), `own_loop.py` (arm B), `sdk_arm.py` (arm A), `run.py`. Run outputs stay outside the repo.

## Runs

| Harness | Model | Tool calls | Ended | Agenda updated | Notes written | Cost | Time |
|---|---|---|---|---|---|---|---|
| Own loop | Haiku 4.5 | 10 | `done` | yes | 2 reviews | $0.24 | 106 s |
| SDK | Haiku 4.5 | 21 | `done` | yes | 5 (drifted into self-reflection) | $0.15 | 122 s |
| Own loop | Sonnet 4.6 | 11 | `done` | yes | 2 reviews, plus a `say` | $0.77 | 246 s |
| SDK | Sonnet 4.6 (first run) | 14 | `done` | no | 0. It couldn't find its workspace (see finding 4) and used `say` to report it | $0.21 | 85 s |
| SDK | Sonnet 4.6 (rerun) | 9 | `done` | yes | 2 reviews | $0.33 | 247 s |
| Own loop / SDK via LiteLLM | GPT-4o | | not run | | | | The OpenAI account has no credits |
| Own loop / SDK via LiteLLM | local (qwen3:14b) | | not run yet | | | | Waiting on Kohl: shares Ollama with her live background jobs |

The SDK counts a step per message block, so its step counts aren't comparable with the own loop's; tool calls are. Each cell is one run, so the differences in behaviour are anecdotes, not measurements.

## Findings

1. **Both harnesses do agentic work with Claude.** Every Claude run read its agenda, did real work, wrote notes, updated its agenda and ended on its own `done`. The reviews made real points; for example, two runs noticed that C8 (a held reply) isn't in the Turn design yet and that the agenda isn't listed as a context provider.
2. **The own loop costs more only because it doesn't cache the prompt.** The SDK read about twice the tokens and still cost less. Prompt caching is a small change to the own loop's Anthropic adapter.
3. **Her tool set is the real design problem, in either harness.** Her router can run 283 tools; the 259 with definitions come to about 38k tokens. Chat copes by picking tools from keywords in the message, which is #110. Here, 30 core tools plus `find_tools` / `use_tool` for the other 229 worked in both harnesses. No run looked up a deferred tool, because the task didn't call for one. A task that needs them is the next test.
4. **On the SDK, Claude Code's own system prompt is the catch.** Keep its preset prompt, and her kernel sits under "You are Claude Code" and its coding-assistant framing. Replace it, as this spike does, and whatever that prompt supplied has to be supplied again. Example: the first SDK Sonnet run had no working directory, so it couldn't use its absolute-path file tools. Every Claude Code update can change what the preset carries, so "free updates" partly means updates to a prompt we've opted out of.
5. **The proxy route works mechanically.** LiteLLM accepted an Anthropic Messages request and passed it to OpenAI (the request failed only for lack of credits). Whether a non-Claude model can work in Claude Code's harness is untested. That's the question that decides between the two harnesses.

## Next

- A non-Claude arm, the decisive one: qwen3:14b on both harnesses (needs a quiet time for Ollama), or GPT-4o once there are credits.
- A task that needs deferred tools, such as "schedule this" or "draft an outreach", to test `find_tools` / `use_tool`.
- Several runs per cell before reading anything into behavioural differences.
