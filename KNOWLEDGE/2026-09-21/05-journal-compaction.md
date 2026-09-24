# 2026-09-21 · 05 — Journal Compaction Synthesis (5 turns)

**Context:** Consolidated 5 micro-checkpoints from `KNOWLEDGE/JOURNAL/` into standing project knowledge.

## Standing Rules & Invariants Extracted
- **runtime/memory**: Never run standalone diffusion or large PyTorch scripts concurrently with vLLM unless available RAM > 40GB.
- **tools/gen_buckets**: When test suite fails with missing /tmp/opencode bucket files, run 'python tools/gen_buckets.py' to regenerate all 8 buckets.
- **ability_tree/Effect**: Leaf effects must be constructed as Atom(verb=Verb.*, args=AtomArgs(...)), never Effect(...).
- **test_templates/CostLoyalty**: Always use assertEqual for dataclasses (CostLoyalty, DurationEot); assertIs is only valid for Enum singletons.
- **ability_tree/MOVE_ZONE**: Verb.MOVE_ZONE takes roles ('cards', <selector>) and ('destination', <zone>).

## Empirical What Worked (Validated Solutions)
- **runtime/memory**: vLLM + gateway circuit breaker trips at RAM_available < 2.5GB.
- **tools/gen_buckets**: Running 'python tools/gen_buckets.py' regenerates all 8 JSON files in /tmp/opencode/phase1_buckets/.
- **ability_tree/Effect**: Identified the correct grammar type definition in ability_tree.py.
- **test_templates/CostLoyalty**: Identified the correct grammar type definition in ability_tree.py.
- **ability_tree/MOVE_ZONE**: Identified the correct grammar type definition in ability_tree.py.

## Empirical Failure Modes (Addressed & Prevented)
- **runtime/memory**: - **Failure**: Out-of-band PyTorch processes (qwen-image) bypass gateway and exhaust LPDDR5X unified RAM, causing kernel DMA starvation.
- **Root Cause**: Host RAM and GPU VRAM share the same physical 121GB memory bus on NVIDIA GB10.
- **tools/gen_buckets**: - **Failure**: 39 test errors / FileNotFoundError because /tmp is wiped on system reboot.
- **Root Cause**: /tmp is backed by volatile tmpfs.
- **ability_tree/Effect**: - **Failure**: Effect is a Union TypeAlias (Seq | Choose | Atom), not a callable class. Leaf is Atom(Verb.*, AtomArgs(...)).
- **Root Cause**: LLM prior assumed conventional object structure instead of strict AST schema.
- **test_templates/CostLoyalty**: - **Failure**: assertIs compares object identity. Frozen dataclasses mint new instances; use assertEqual.
- **Root Cause**: LLM prior assumed conventional object structure instead of strict AST schema.
- **ability_tree/MOVE_ZONE**: - **Failure**: Verb.MOVE_ZONE requires roles 'cards' and 'destination', not 'target'.
- **Root Cause**: LLM prior assumed conventional object structure instead of strict AST schema.

## Prompt Engineering Directives
Future subagent prompts in this project MUST incorporate the following synthesized directives:
```markdown
### Mandatory Project Invariants:
- Never run standalone diffusion or large PyTorch scripts concurrently with vLLM unless available RAM > 40GB.
- When test suite fails with missing /tmp/opencode bucket files, run 'python tools/gen_buckets.py' to regenerate all 8 buckets.
- Leaf effects must be constructed as Atom(verb=Verb.*, args=AtomArgs(...)), never Effect(...).
- Always use assertEqual for dataclasses (CostLoyalty, DurationEot); assertIs is only valid for Enum singletons.
- Verb.MOVE_ZONE takes roles ('cards', <selector>) and ('destination', <zone>).
```
