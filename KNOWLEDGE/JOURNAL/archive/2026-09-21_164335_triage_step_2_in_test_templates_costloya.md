# Micro-Checkpoint: Triage step 2 in test_templates/CostLoyalty
- **Timestamp**: 2026-09-21 16:43:35
- **Scope**: `test_templates/CostLoyalty`
- **Outcome**: FAILED
- **Tags**: grammar-trap, ast-schema

## Attempted
Implemented test_templates/CostLoyalty using naive syntax.

## What Worked
Identified the correct grammar type definition in ability_tree.py.

## What Failed & Root Cause
- **Failure**: assertIs compares object identity. Frozen dataclasses mint new instances; use assertEqual.
- **Root Cause**: LLM prior assumed conventional object structure instead of strict AST schema.

## Actionable Invariant (Rule for Future Prompts)
> **Rule**: Always use assertEqual for dataclasses (CostLoyalty, DurationEot); assertIs is only valid for Enum singletons.
