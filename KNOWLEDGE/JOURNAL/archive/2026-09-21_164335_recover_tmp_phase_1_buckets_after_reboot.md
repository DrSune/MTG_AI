# Micro-Checkpoint: Recover /tmp Phase-1 Buckets After Reboot
- **Timestamp**: 2026-09-21 16:43:35
- **Scope**: `tools/gen_buckets`
- **Outcome**: FAILED
- **Tags**: environment-trap, test-prereq

## Attempted
Running pytest after machine reboot.

## What Worked
Running 'python tools/gen_buckets.py' regenerates all 8 JSON files in /tmp/opencode/phase1_buckets/.

## What Failed & Root Cause
- **Failure**: 39 test errors / FileNotFoundError because /tmp is wiped on system reboot.
- **Root Cause**: /tmp is backed by volatile tmpfs.

## Actionable Invariant (Rule for Future Prompts)
> **Rule**: When test suite fails with missing /tmp/opencode bucket files, run 'python tools/gen_buckets.py' to regenerate all 8 buckets.
