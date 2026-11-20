from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts import prune_checkpoints as script


def _container(count: int):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {"deleted": count}
    pool = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    closed: list = []
    return SimpleNamespace(pool=pool, close=lambda: closed.append(True)), conn, closed


def test_without_yes_prints_plan_and_touches_nothing(capsys):
    built: list = []
    assert script.main([], build=lambda: built.append(1)) == 0
    assert built == []
    assert "--yes" in capsys.readouterr().out


def test_yes_calls_prune_and_prints_count(capsys):
    c, conn, closed = _container(7)
    assert script.main(["--yes", "--older", "3 days"], build=lambda: c) == 0
    sql, params = conn.execute.call_args.args
    assert "public.prune_checkpoints(%s::interval)" in sql
    assert params == ("3 days",)
    assert capsys.readouterr().out.strip() == "deleted 7 checkpoint rows"
    assert closed == [True]
