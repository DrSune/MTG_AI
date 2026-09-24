# Micro-Checkpoint: Triage step 3 in ability_tree/PtDelta
- **Timestamp**: 2026-09-21 16:44:14
- **Scope**: `ability_tree/PtDelta`
- **Outcome**: FAILED
- **Tags**: grammar-trap, ast-schema

## Attempted
Implemented ability_tree/PtDelta using naive syntax.

## What Worked
Identified the correct grammar type definition in ability_tree.py.

## What Failed & Root Cause
- **Failure**: PtDelta defines (direction: PtDirection, magnitude: Quantity); 'amount' is invalid.
- **Root Cause**: LLM prior assumed conventional object structure instead of strict AST schema.

## Actionable Invariant (Rule for Future Prompts)
> **Rule**: PtDelta uses field 'magnitude', not 'amount'.
