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
| Own loop | qwen3:8b (local) | 10 | ended on plain text, no `done` | no | 1 (summary, little critique) | $0 | 133 s |
| SDK via LiteLLM | qwen3:8b (local) | 6 | `done` | yes | 1 review | $0 | 99 s |
| Own loop | qwen3:14b (local) | 3 | ended on plain text, no `done` | no | 1 | $0 | 74 s |
| SDK via LiteLLM | qwen3:14b (local) | 9 | `done` | yes | 1 review covering both docs | $0 | 168 s |
| Own loop, with a nudge (up to 2) | qwen3:14b (local) | 9 | `done` | yes | 2 reviews | $0 | 171 s |

The local runs used Ollama's native chat API with `num_ctx` 32768 on both harnesses (LiteLLM's `ollama_chat` route for the SDK). ComfyUI and ACE-Step were stopped to free the GPU.

The SDK counts a step per message block, so its step counts aren't comparable with the own loop's; tool calls are. Each cell is one run, so the differences in behaviour are anecdotes, not measurements.

## Findings

1. **Both harnesses do agentic work with Claude.** Every Claude run read its agenda, did real work, wrote notes, updated its agenda and ended on its own `done`. The reviews made real points; for example, two runs noticed that C8 (a held reply) isn't in the Turn design yet and that the agenda isn't listed as a context provider.
2. **The own loop costs more only because it doesn't cache the prompt.** The SDK read about twice the tokens and still cost less. Prompt caching is a small change to the own loop's Anthropic adapter.
3. **Her tool set is the real design problem, in either harness.** Her router can run 283 tools; the 259 with definitions come to about 38k tokens. Chat copes by picking tools from keywords in the message, which is #110. Here, 30 core tools plus `find_tools` / `use_tool` for the other 229 worked in both harnesses. No run looked up a deferred tool, because the task didn't call for one. A task that needs them is the next test.
4. **On the SDK, Claude Code's own system prompt is the catch.** Keep its preset prompt, and her kernel sits under "You are Claude Code" and its coding-assistant framing. Replace it, as this spike does, and whatever that prompt supplied has to be supplied again. Example: the first SDK Sonnet run had no working directory, so it couldn't use its absolute-path file tools. Every Claude Code update can change what the preset carries, so "free updates" partly means updates to a prompt we've opted out of.
5. **Claude Code's harness runs non-Claude models.** Through LiteLLM, qwen3:8b and qwen3:14b each finished the whole task in the SDK: notes, agenda, `done`. So the SDK route doesn't lock research to Claude.
6. **Out of the box, the SDK carried weaker models further than the own loop did, and the gap was scaffolding.** Both qwen runs in the own loop ended early by saying what they'd do next in plain text instead of calling a tool, which the loop takes as the end. Adding a nudge closed the gap for qwen3:14b: if the model stops without `done`, remind it, at most twice (about ten lines of code). Claude Code's long, instructive tool descriptions probably also help; ours are one line. Neither is unique to the SDK.
7. **This spike tests the harness, not her.** She ran on the kernel with a generic identity line, no context sections (self-context, PeopleDex, recall, threads, working summary), stubbed tools, and an agenda Daedalus wrote. How *she* does in an agentic shape needs a second phase: a snapshot of her data in a scratch `DATA_DIR`, her assembled context, and her tools executing against the copy.
8. **Found on the way: her local models don't fit on the GPU.** ComfyUI (6.9 GB) and ACE-Step (4.8 GB) sit resident on the 16 GB card while idle, so llama3.1 8B (about 8.5 GB) runs partly on the CPU. That is the likely cause of her Ollama `ReadTimeout`s and of the self-observation extractions she has lost.

## Where this leaves the choice

Neither harness rules itself out. The SDK runs every model family through LiteLLM, and the own loop matches it once it has the same scaffolding. What separates them:
- **SDK:** prompt caching, tool descriptions and future improvements for free. In exchange, her harness is Anthropic's product, its preset prompt (identity and environment) has to be replaced and maintained by us, non-Claude models go through a translating proxy, and Claude Code updates change the harness between research runs unless the version is pinned.
- **Own loop:** we control and pin everything and talk to every provider natively. In exchange, we maintain the scaffolding (caching, tool descriptions, nudges, context compaction) and copy what Claude Code learns.

## Next

- Phase 2, her and not a stand-in: a snapshot of her data, her assembled context, her tools executing against the copy, her own agenda. Kohl's call, and arguably hers, since the run would write in her voice about her real memories outside her continuity.
- A task that needs deferred tools, such as "schedule this" or "draft an outreach", to test `find_tools` / `use_tool`.
- Several runs per cell. Every difference above is one run.
- GPT-4o when there are credits, for a third model family.
