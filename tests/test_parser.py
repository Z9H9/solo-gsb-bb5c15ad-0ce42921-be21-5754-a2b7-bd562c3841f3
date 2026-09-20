"""parser 模块与 /api/evaluate 接口的单元测试。"""

import pytest

from app.parser import Atom, Group, ParseError, evaluate_plan, parse

# ---------------------------------------------------------------- 解析


def test_parse_simple_atoms():
    items = parse("k3 inc2 dec4")
    assert [type(i) for i in items] == [Atom, Atom, Atom]
    assert [(i.kind, i.n) for i in items] == [("k", 3), ("inc", 2), ("dec", 4)]


def test_parse_group_and_nesting():
    items = parse("[k2 [inc2 k1]*2]*3")
    assert len(items) == 1
    outer = items[0]
    assert isinstance(outer, Group) and outer.times == 3
    assert isinstance(outer.items[0], Atom)
    inner = outer.items[1]
    assert isinstance(inner, Group) and inner.times == 2
    assert [(a.kind, a.n) for a in inner.items] == [("inc", 2), ("k", 1)]


def test_parse_case_insensitive_and_separators():
    items = parse("K2, INC3 ; dec2")
    assert [(i.kind, i.n) for i in items] == [("k", 2), ("inc", 3), ("dec", 2)]


@pytest.mark.parametrize(
    "text",
    ["k", "k0", "inc", "x3", "[k2]", "[k2]*", "[k2]*0", "[]*2", "k2]", "*3", "[k2*3"],
)
def test_parse_errors(text):
    with pytest.raises(ParseError):
        parse(text)


def test_atom_spans_point_into_source():
    src = "k2 [inc3 k1]*2"
    items = parse(src)
    group = items[1]
    atom = group.items[0]
    assert src[atom.start : atom.end] == "inc3"
    assert src[group.start : group.end] == "[inc3 k1]*2"


# ---------------------------------------------------------------- 单行求值


def test_k_row_balanced():
    (r,) = evaluate_plan(12, ["k12"])
    assert r["status"] == "ok"
    assert (r["available"], r["consumed"], r["produced"], r["remaining"]) == (12, 12, 12, 0)


def test_inc_and_dec_counts():
    # inc2：耗 1 产 2；k1：耗 1 产 1 → 每组耗 2 产 3，重复 6 次
    (r,) = evaluate_plan(12, ["[inc2 k1]*6"])
    assert (r["status"], r["consumed"], r["produced"]) == ("ok", 12, 18)
    # dec2：耗 2 产 1
    (r,) = evaluate_plan(18, ["[dec2 k2]*4 k2"])
    assert (r["status"], r["consumed"], r["produced"], r["remaining"]) == ("ok", 18, 14, 0)


def test_nested_group_expansion():
    (r,) = evaluate_plan(4, ["[[inc2]*2]*2"])
    assert r["status"] == "ok"
    assert r["consumed"] == 4 and r["produced"] == 8
    assert r["expansion"] == ["inc2"] * 4


# ---------------------------------------------------------------- 错误定位


def test_insufficient_locates_first_failing_atom():
    (r,) = evaluate_plan(3, ["k2 k2"])
    err = r["error"]
    assert r["status"] == "error" and err["type"] == "insufficient"
    assert r["source"][err["position"]["start"] : err["position"]["end"]] == "k2"
    assert err["position"]["start"] == 3  # 第二条 k2
    assert (err["need"], err["left"], err["short"]) == (2, 1, 1)


def test_insufficient_inside_group_reports_repetition():
    (r,) = evaluate_plan(5, ["[k2]*3"])
    err = r["error"]
    assert err["type"] == "insufficient"
    assert err["repetition"] == [{"context": "[k2]*3", "rep": 3, "times": 3}]
    assert "第 3 次重复" in err["message"]
    assert err["short"] == 1


def test_unconsumed_reported_and_stitches_carry_over():
    rows = evaluate_plan(10, ["k6", "k10"])
    assert rows[0]["status"] == "error"
    assert rows[0]["error"]["type"] == "unconsumed"
    assert rows[0]["error"]["unconsumed"] == 4
    # 未消耗的 4 针仍在针上 → 下一行可用 10
    assert rows[1]["status"] == "ok" and rows[1]["available"] == 10


def test_blocked_after_error():
    rows = evaluate_plan(2, ["k5", "k1", "bad!"])
    assert rows[0]["error"]["type"] == "insufficient"
    assert rows[1]["status"] == "blocked"
    assert rows[2]["status"] == "blocked"


def test_parse_error_blocks_following_rows():
    rows = evaluate_plan(5, ["k2]", "k5"])
    assert rows[0]["error"]["type"] == "parse"
    assert rows[1]["status"] == "blocked"


def test_empty_row_passes_stitches_through():
    rows = evaluate_plan(8, ["", "k8"])
    assert rows[0]["status"] == "empty"
    assert rows[1]["available"] == 8 and rows[1]["status"] == "ok"


def test_chain_uses_previous_produced():
    rows = evaluate_plan(12, ["k12", "[inc2 k1]*6", "[k2 dec2]*4 k2"])
    assert [r["status"] for r in rows] == ["ok", "ok", "ok"]
    assert [r["available"] for r in rows] == [12, 12, 18]
    assert rows[-1]["produced"] == 14


# ---------------------------------------------------------------- API


def test_evaluate_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/evaluate", json={"start": 4, "rows": ["k4", "[inc2]*4"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows"][0]["produced"] == 4
    assert data["rows"][1]["available"] == 4
    assert data["rows"][1]["produced"] == 8


def test_index_page_served():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "编织行指令审校工具" in resp.text
