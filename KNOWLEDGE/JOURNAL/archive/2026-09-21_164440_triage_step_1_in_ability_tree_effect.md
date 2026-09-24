# Micro-Checkpoint: Triage step 1 in ability_tree/Effect
- **Timestamp**: 2026-09-21 16:44:40
- **Scope**: `ability_tree/Effect`
- **Outcome**: FAILED
- **Tags**: grammar-trap, ast-schema

## Attempted
Implemented ability_tree/Effect using naive syntax.

## What Worked
Identified the correct grammar type definition in ability_tree.py.

## What Failed & Root Cause
- **Failure**: Effect is a Union TypeAlias (Seq | Choose | Atom), not a callable class. Leaf is Atom(Verb.*, AtomArgs(...)).
- **Root Cause**: LLM prior assumed conventional object structure instead of strict AST schema.

## Actionable Invariant (Rule for Future Prompts)
> **Rule**: Leaf effects must be constructed as Atom(verb=Verb.*, args=AtomArgs(...)), never Effect(...).
