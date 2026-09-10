import torch
from MTG_bot.strategic_brain.model import System2Transformer

def test_model_forward():
    print("Testing System2Transformer forward pass...")
    
    # Model parameters
    vocab_size = 1000
    embedding_dim = 128
    component_dim = 10
    nhead = 8
    num_layers = 2
    belief_dim = 64
    max_actions = 10
    
    # Create model
    model = System2Transformer(
        vocab_size, embedding_dim, component_dim, 
        nhead, num_layers, belief_dim, max_actions
    )
    
    # Mock data
    batch_size = 1
    num_entities = 20
    atomic_ids = torch.randint(0, vocab_size, (batch_size, num_entities))
    component_features = torch.randn(batch_size, num_entities, component_dim)
    # Mock legal descriptors: 5 actions, each with (component_dim * 2 + 1) features
    desc_dim = component_dim * 2 + 1
    legal_descriptors = torch.randn(batch_size, 5, desc_dim)
    
    # Forward pass 1 (initial state)
    output1 = model(atomic_ids, component_features, legal_descriptors, num_passes=3)
    
    print("Output shapes:")
    print(f"  Action Logits: {output1['action_logits'].shape}") 
    print(f"  Value: {output1['value'].shape}")              
    print(f"  RNN State (h): {output1['rnn_state'][0].shape}")
    
    assert output1['action_logits'].shape == (batch_size, 5) # 5 legal actions
    assert output1['value'].shape == (batch_size, 1)
    
    # Forward pass 2 (with recurrent state)
    output2 = model(atomic_ids, component_features, legal_descriptors, rnn_state=output1['rnn_state'], num_passes=3)
    
    print("\nRecurrent state handling successful!")
    print("Forward passes successful!")

def _all_outputs_loss(out):
    """A scalar that touches every differentiable output the model produces.

    Used so that "this parameter got no gradient" means the parameter is unreachable from
    the architecture, not merely absent from whatever loss the training code happens to use
    today. Those are different defects with different fixes and they were conflated once.
    """
    loss = out["action_logits"].logsumexp(-1).mean()
    loss = loss + out["value"].pow(2).mean()
    loss = loss + out["rethink_prob"].mean()
    for step in out["plan_sequence"]:
        for value in step.values():
            if torch.is_tensor(value) and value.is_floating_point() and value.requires_grad:
                loss = loss + value.logsumexp(-1).mean()
    return loss


def test_no_parameter_is_orphaned_from_the_architecture():
    """Every trainable parameter must be reachable from a loss over every model output.

    Two reasons this test exists.

    First, the repository had no backward-pass test at all, and that hid a real environment
    defect. On the DGX Spark, torch 2.14 routes some backward ops through Triton, Triton
    JIT-compiles a driver shim with gcc, and that compile needs CPython's development
    headers. Without python3.12-dev, the forward pass and test_model_forward both pass and
    the first gradient raises. See reports/SPARK_BRINGUP.md.

    Second, it pins down what the 54.4M ungradiented parameters in docs/ARCHITECTURE.md
    actually are. Measured at the real training shape (vocab 50000, d_model 1024, 16 layers),
    54.3M of 315.7M are orphaned even under a loss over EVERY output:

        51.20M  reasoning_head.action_memory_embedder.weight   declared model.py:56,
                                                               referenced nowhere else
         2.10M  reasoning_head.action_fusion.weight            declared :57, used :64, but
                                                               only when prev_plan_embeddings
                                                               is not None, i.e. only from
                                                               reasoning pass 2 onward
         1.05M  decoder.intent_proj.weight                     declared :152, referenced
                                                               nowhere else

    So 52.25M of it is two layers no code path touches, and 2.10M is gated behind the
    inert reasoning loop that test_reasoning_loop_can_actually_iterate covers. The plan
    sequence heads are NOT in that list: they receive gradient whenever the loss includes
    the plan steps. That matters for D3, which requires every plan step to be trained and
    which was argued on the premise that the decoder's parameters were untrained. The
    decoder is fine. Training every plan step is a change to the loss in student.py, not to
    the model.

    A do-nothing implementation cannot pass this (docs/METRICS.md section 17). A model that
    returns constants still yields a finite scalar and still survives loss.backward(); it
    cannot produce a non-None finite gradient on every parameter, because constants have no
    path back to the weights.

    Expected to fail until the unwired layers are either wired up or removed.
    """
    torch.manual_seed(0)
    vocab_size, embedding_dim, component_dim = 1000, 128, 10
    model = System2Transformer(
        vocab_size, embedding_dim, component_dim,
        nhead=8, num_layers=2, belief_dim=64, max_actions=10,
    )

    out = model(
        torch.randint(0, vocab_size, (1, 20)),
        torch.randn(1, 20, component_dim),
        torch.randn(1, 5, component_dim * 2 + 1),
        num_passes=3,
    )
    loss = _all_outputs_loss(out)
    assert torch.isfinite(loss), f"loss is not finite: {loss}"
    loss.backward()

    orphaned, nonfinite = {}, []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        if param.grad is None:
            orphaned[name] = param.numel()
        elif not torch.isfinite(param.grad).all():
            nonfinite.append(name)

    assert not nonfinite, f"non-finite gradient on: {nonfinite}"

    total = sum(p.numel() for p in model.parameters() if p.requires_grad)
    dead = sum(orphaned.values())
    assert not orphaned, (
        f"{len(orphaned)} parameter tensors are unreachable from the architecture: "
        f"{dead / 1e6:.3f}M of {total / 1e6:.1f}M ({100 * dead / total:.2f}%). "
        + ", ".join(f"{n} ({k / 1e6:.3f}M)" for n, k in
                    sorted(orphaned.items(), key=lambda kv: -kv[1]))
    )


def test_reasoning_loop_can_actually_iterate():
    """num_passes must be capable of producing more than one pass.

    Measured on the Spark: 50 of 50 random positions took exactly one pass with
    num_passes=8 requested. model.py breaks out of the loop unless
    argmax(plan_sequence[0]["type_logits"]) equals the literal action-type integer 9,
    which never happens at initialisation, so every multi-pass latency number taken of
    this model is really a one-pass number.

    The decoder computes rethink_prob and the forward pass returns it, but the loop does
    not gate on it, so there is no gradient path from the halting decision to the loss.
    D11 and docs/DESIGN_LATENCY.md section 3.3 both require halting to be learned and
    sampled, not decided by an argmax against a constant.

    Expected to fail today. It is the gate for D11, and it fails loudly with the measured
    number rather than letting a flat latency curve be read as efficiency.
    """
    torch.manual_seed(0)
    vocab_size, embedding_dim, component_dim = 1000, 128, 10
    model = System2Transformer(
        vocab_size, embedding_dim, component_dim,
        nhead=8, num_layers=2, belief_dim=64, max_actions=10,
    ).eval()

    requested = 8
    counts = []
    with torch.no_grad():
        for _ in range(20):
            out = model(
                torch.randint(0, vocab_size, (1, 20)),
                torch.randn(1, 20, component_dim),
                torch.randn(1, 5, component_dim * 2 + 1),
                num_passes=requested,
            )
            counts.append(out["passes_taken"])

    assert max(counts) > 1, (
        f"the reasoning loop never iterated: passes_taken was {set(counts)} across "
        f"{len(counts)} positions with num_passes={requested} requested. Every "
        f"multi-pass latency number for this model is a one-pass number."
    )


if __name__ == "__main__":
    try:
        test_model_forward()
    except Exception as e:
        print(f"Test failed: {e}")
