from sandesh.multiturn import _alternate


def test_alternate_merges_consecutive_roles():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"}, {"role": "user", "content": "tool result"},
            {"role": "user", "content": "follow-up"}, {"role": "assistant", "content": "a2"}]
    out = _alternate(msgs)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "user", "assistant"]
    assert out[3]["content"] == "tool result\n\nfollow-up"
    assert msgs[3]["content"] == "tool result"  # input untouched


def test_alternate_keeps_alternating_chat():
    msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    assert _alternate(msgs) == msgs
