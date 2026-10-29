
## RL-pilot window run — 2026-10-20 13:09:16 (dry-run=1, gpu-train-device=cpu, HEAD b18b58b, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect smoke smoke 2 14 0.1429 rc=0 cpu x2 sample+rl-collect |
| audit smoke smoke - - - GREEN off-policy discriminator |
| FAIL train/rld_smoke - - - - rc=1 chain stopped |

## RL-pilot window run — 2026-10-20 13:16:32 (dry-run=1, gpu-train-device=cpu, HEAD f2d693f, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect smoke smoke 2 8 0.2500 rc=0 cpu x2 sample+rl-collect |
| audit smoke smoke - - - GREEN off-policy discriminator |
| train rld_smoke rld_smoke - - - rc=0 device=cpu 1 update |
| collect calib calib 2 22 0.0909 rc=0 cpu x2 sample+rl-collect |
| audit calib calib - - - GREEN off-policy discriminator |
| train rld_cal rld_cal - - - rc=0 device=cpu 1 update |
| probe p1 p1 2 - - rc=0 mirror,teacher -> dry_probe_p1.json |
| calib phase1-wall total 2 164 - done budget input for phase 2 |
| collect iter1 iter1 2 32 0.0625 rc=0 cpu x2 sample+rl-collect |
| audit iter1 iter1 - - - GREEN off-policy discriminator |
| train rld_i1 rld_i1 - - - rc=0 device=cpu 1 update |
| probe p2 p2 2 - - rc=0 mirror,teacher -> dry_probe_p2.json |
| window | summary | rc_phases=0 | - | - | - | phases_rc=0 | artifacts=/tmp/opencode/rld_n1 |


## RL-pilot window run — 2026-10-26 05:54:40 (dry-run=1, gpu-train-device=cpu, HEAD b308cf5, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|

## RL-pilot window run — 2026-10-26 05:56:36 (dry-run=1, gpu-train-device=cpu, HEAD b308cf5, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect|smoke|smoke|2|6|0.3333|rc=0|cpu x2 sample+rl-collect |
| audit|smoke|smoke|-|-|-|GREEN|off-policy discriminator |
| train|rld_smoke|rld_smoke|-|-|-|rc=0|device=cpu 1 update |
| collect|calib|calib|2|21|0.0952|rc=0|cpu x2 sample+rl-collect |
| audit|calib|calib|-|-|-|GREEN|off-policy discriminator |
| train|rld_cal|rld_cal|-|-|-|rc=0|device=cpu 1 update |
| probe|p1|p1|2|-|-|rc=0|mirror,teacher -> dry_probe_p1.json |
| calib|phase1-wall|total|2|118|-|done|budget input for phase 2 |
| budget|phase2-skip|iter1|2|-|-|SKIPPED|have=3644s need=4824s |
| window | summary | rc_phases=0 | - | - | - | phases_rc=0 | artifacts=/tmp/opencode/rld_n1 |


## RL-pilot window run — 2026-10-26 06:00:05 (dry-run=1, gpu-train-device=cpu, HEAD b308cf5, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect|smoke|smoke|2|7|0.2857|rc=0|cpu x2 sample+rl-collect |
| audit|smoke|smoke|-|-|-|GREEN|off-policy discriminator |
| train|rld_smoke|rld_smoke|-|-|-|rc=0|device=cpu 1 update |
| collect|calib|calib|2|21|0.0952|rc=0|cpu x2 sample+rl-collect |
| audit|calib|calib|-|-|-|GREEN|off-policy discriminator |
| train|rld_cal|rld_cal|-|-|-|rc=0|device=cpu 1 update |
| probe|p1|p1|2|-|-|rc=0|mirror,teacher -> dry_probe_p1.json |
| calib|phase1-wall|total|2|114|-|done|budget input for phase 2 |
| budget|phase2-skip|iter1|2|-|-|SKIPPED|have=3444s need=4752s |
| window | summary | rc_phases=0 | - | - | - | phases_rc=0 | artifacts=/tmp/opencode/rld_n1 |


## RL-pilot window run — 2026-10-27 05:54:44 (dry-run=1, gpu-train-device=cpu, HEAD e6e6797, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect|smoke|smoke|2|8|0.2500|rc=0|cpu x2 sample+rl-collect |
| audit|smoke|smoke|-|-|-|GREEN|off-policy discriminator |
| train|rld_smoke|rld_smoke|-|-|-|rc=0|device=cpu 1 update |
| collect|calib|calib|2|25|0.0800|rc=0|cpu x2 sample+rl-collect |
| audit|calib|calib|-|-|-|GREEN|off-policy discriminator |
| train|rld_cal|rld_cal|-|-|-|rc=0|device=cpu 1 update |
| probe|p1|p1|2|-|-|rc=0|mirror,teacher -> dry_probe_p1.json |
| calib|phase1-wall|total|2|153|-|done|budget input for phase 2 |
| budget|phase2-skip|iter1|2|-|-|SKIPPED|have=3710s need=5454s |
| window | summary | rc_phases=0 | - | - | - | phases_rc=0 | artifacts=/tmp/opencode/rld_n1 |


## RL-pilot window run — 2026-10-27 09:20:37 (dry-run=1, gpu-train-device=cpu, HEAD db4bdef, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect|smoke|smoke|2|7|0.2857|rc=0|cpu x2 sample+rl-collect |
| audit|smoke|smoke|-|-|-|GREEN|off-policy discriminator |
| train|rld_smoke|rld_smoke|-|-|-|rc=0|device=cpu 1 update |
| collect|calib|calib|2|21|0.0952|rc=0|cpu x2 sample+rl-collect |
| audit|calib|calib|-|-|-|GREEN|off-policy discriminator |
| train|rld_cal|rld_cal|-|-|-|rc=0|device=cpu 1 update |
| probe|p1|p1|2|-|-|rc=0|mirror,teacher -> dry_probe_p1.json |
| calib|phase1-wall|total|2|115|-|done|budget input for phase 2 |
| collect|iter1|iter1|2|26|0.0769|rc=0|cpu x2 sample+rl-collect |
| audit|iter1|iter1|-|-|-|GREEN|off-policy discriminator |
| train|rld_i1|rld_i1|-|-|-|rc=0|device=cpu 1 update |
| probe|p2|p2|2|-|-|rc=0|mirror,teacher -> dry_probe_p2.json |
| window | summary | rc_phases=0 | - | - | - | phases_rc=0 | artifacts=/tmp/opencode/rld_n1 |


## RL-pilot window run — 2026-10-27 13:30:37 (dry-run=1, gpu-train-device=cpu, HEAD 3a1e05b, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect|smoke|smoke|2|7|0.2857|rc=0|cpu x2 sample+rl-collect |
| audit|smoke|smoke|-|-|-|GREEN|off-policy discriminator |
| train|rld_smoke|rld_smoke|-|-|-|rc=0|device=cpu 1 update |
| collect|calib|calib|2|22|0.0909|rc=0|cpu x2 sample+rl-collect |
| audit|calib|calib|-|-|-|GREEN|off-policy discriminator |
| train|rld_cal|rld_cal|-|-|-|rc=0|device=cpu 1 update |
| probe|p1|p1|2|-|-|rc=0|mirror,teacher -> dry_probe_p1.json |
| calib|phase1-wall|total|2|116|-|done|budget input for phase 2 |
| collect|iter1|iter1|2|27|0.0741|rc=0|cpu x2 sample+rl-collect |
| audit|iter1|iter1|-|-|-|GREEN|off-policy discriminator |
| train|rld_i1|rld_i1|-|-|-|rc=0|device=cpu 1 update |
| probe|p2|p2|2|-|-|rc=0|mirror,teacher -> dry_probe_p2.json |
| window | summary | rc_phases=0 | - | - | - | phases_rc=0 | artifacts=/tmp/opencode/rld_n1 |


## RL-pilot window run — 2026-10-28 20:06:00 (dry-run=1, gpu-train-device=cpu, HEAD 77c7576, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect|smoke|smoke|2|7|0.2857|rc=0|cpu x2 sample+rl-collect |
| audit|smoke|smoke|-|-|-|GREEN|off-policy discriminator |
| FAIL|train/rld_smoke|-|-|-|-|rc=2|chain stopped |
| window | summary | rc_phases=8 | - | - | - | phases_rc=8 | artifacts=/tmp/opencode/rld_n1 |


## RL-pilot window run — 2026-10-28 20:18:00 (dry-run=1, gpu-train-device=cpu, HEAD 77c7576, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect|smoke|smoke|2|7|0.2857|rc=0|cpu x2 sample+rl-collect |
| audit|smoke|smoke|-|-|-|GREEN|off-policy discriminator |
| FAIL|train/rld_smoke|-|-|-|-|rc=2|chain stopped |
| window | summary | rc_phases=8 | - | - | - | phases_rc=8 | artifacts=/tmp/opencode/rld_n1 |


## RL-pilot window run — 2026-10-28 20:25:00 (dry-run=1, gpu-train-device=cpu, HEAD 77c7576, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect|smoke|smoke|2|6|0.3333|rc=0|cpu x2 sample+rl-collect |
| audit|smoke|smoke|-|-|-|GREEN|off-policy discriminator |
| train|rld_smoke|rld_smoke|-|-|-|rc=0|device=cpu 1 update(s) |
| collect|calib|calib|2|21|0.0952|rc=0|cpu x2 sample+rl-collect |
| audit|calib|calib|-|-|-|GREEN|off-policy discriminator |
| train|rld_cal|rld_cal|-|-|-|rc=0|device=cpu 1 update(s) |
| probe|p1|p1|2|-|-|rc=0|mirror,teacher -> dry_probe_p1.json |
| calib|phase1-wall|total|2|109|-|done|budget input for phase 2 |
| collect|iter1|iter1|2|27|0.0741|rc=0|cpu x2 sample+rl-collect |
| audit|iter1|iter1|-|-|-|GREEN|off-policy discriminator |
| train|rld_i1|rld_i1|-|-|-|rc=0|device=cpu 1 update(s) |
| train|rld_i2|rld_i2|-|-|-|rc=0|device=cpu 2 update(s) |
| probe|p2|p2|2|-|-|rc=0|mirror,teacher -> dry_probe_p2.json |
| window | summary | rc_phases=0 | - | - | - | phases_rc=0 | artifacts=/tmp/opencode/rld_n1 |


## RL-pilot window run — 2026-10-29 17:42:00 (dry-run=1, gpu-train-device=cpu, HEAD 5c18ad9, artifacts /tmp/opencode/rld_n1)

Commands (exact): phase driver /tmp/opencode/rl_n1_train_src/tools/ops/rl_pilot_phases.sh; per phase: -m tools.eval.gameplay_eval_v2 --policy-a <net> --matchups teacher --sample --rl-collect ...; -m tools.training.rl_logprob_audit --policy <collecting net>; -m tools.training.train_rl_v1 --policy tools/training/bsh_S3a_s1_best.pt --anchor tools/training/bsh_S3a_s1_best.pt; probes --matchups mirror,teacher --policy-b tools/training/bsh_S3a_s1_best.pt (frozen pre-RL anchor)

| kind | phase | tag | games | wall_s | rate_g_per_s | rc/result | extra |
|---|---|---|---|---|---|---|---|
| collect|smoke|smoke|2|7|0.2857|rc=0|cpu x2 sample+rl-collect |
| audit|smoke|smoke|-|-|-|GREEN|off-policy discriminator |
| train|rld_smoke|rld_smoke|-|-|-|rc=0|device=cpu 1 update(s) |
| collect|calib|calib|2|21|0.0952|rc=0|cpu x2 sample+rl-collect |
| audit|calib|calib|-|-|-|GREEN|off-policy discriminator |
| train|rld_cal|rld_cal|-|-|-|rc=0|device=cpu 1 update(s) |
| probe|p1|p1|2|-|-|rc=0|mirror,teacher -> dry_probe_p1.json |
| calib|phase1-wall|total|2|125|-|done|budget input for phase 2 |
| collect|iter1|iter1|2|27|0.0741|rc=0|cpu x2 sample+rl-collect |
| audit|iter1|iter1|-|-|-|GREEN|off-policy discriminator |
| train|rld_i1|rld_i1|-|-|-|rc=0|device=cpu 1 update(s) |
| train|rld_i2|rld_i2|-|-|-|rc=0|device=cpu 2 update(s) |
| train|rld_i3|rld_i3|-|-|-|rc=0|device=cpu 3 update(s) |
| probe|p2|p2|2|-|-|rc=0|mirror,teacher -> dry_probe_p2.json |
| window | summary | rc_phases=0 | - | - | - | phases_rc=0 | artifacts=/tmp/opencode/rld_n1 |

