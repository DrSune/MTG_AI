# Micro-Checkpoint: Triage step 3 in ability_tree/MOVE_ZONE
- **Timestamp**: 2026-09-21 16:44:40
- **Scope**: `ability_tree/MOVE_ZONE`
- **Outcome**: FAILED
- **Tags**: grammar-trap, ast-schema

## Attempted
Implemented ability_tree/MOVE_ZONE using naive syntax.

## What Worked
Identified the correct grammar type definition in ability_tree.py.

## What Failed & Root Cause
- **Failure**: Verb.MOVE_ZONE requires roles 'cards' and 'destination', not 'target'.
- **Root Cause**: LLM prior assumed conventional object structure instead of strict AST schema.

## Actionable Invariant (Rule for Future Prompts)
> **Rule**: Verb.MOVE_ZONE takes roles ('cards', <selector>) and ('destination', <zone>).
