from agape_mainframe import testing_tools


def test_testing_tool_catalog_contract():
    out=testing_tools.status()
    assert out["ok"] is True
    ids={x["id"] for x in out["tools"]}
    assert {"axe","schemathesis","zap","lighthouse","k6","appium-windows","appium-android"} <= ids
    assert set(out["recommended_ids"]) == {"axe","schemathesis","zap","lighthouse"}


def test_testing_tool_descriptions_are_human_readable():
    for row in testing_tools.TOOLS:
        assert len(row["why"]) > 45
        assert row["cost"]
        assert isinstance(row["recommended"], bool)


def test_unknown_testing_tool_rejected():
    try:
        testing_tools.install("not-a-real-tool")
    except ValueError as exc:
        assert "UNKNOWN_TESTING_TOOL" in str(exc)
    else:
        raise AssertionError("expected unknown testing tool rejection")
