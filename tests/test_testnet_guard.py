import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _parse(path: str):
    return ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)


def _last_assignment(tree: ast.AST, name: str):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                found.append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            found.append(node.value)
    assert found, f"Не найдена настройка {name}"
    return found[-1]


def test_config_selects_testnet_and_disables_demo():
    tree = _parse("config.py")
    assert isinstance(_last_assignment(tree, "TESTNET"), ast.Constant)
    assert _last_assignment(tree, "TESTNET").value is True
    assert isinstance(_last_assignment(tree, "DEMO_TRADING"), ast.Constant)
    assert _last_assignment(tree, "DEMO_TRADING").value is False


def test_bot_rest_client_is_hard_locked_to_testnet():
    tree = _parse("main.py")
    client_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BybitClient"
    )
    init = next(
        node for node in client_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    http_calls = [
        node for node in ast.walk(init)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "HTTP"
    ]
    assert len(http_calls) == 1, "Ожидался ровно один HTTP-клиент Bybit"
    kwargs = {kw.arg: kw.value for kw in http_calls[0].keywords if kw.arg}
    assert isinstance(kwargs.get("testnet"), ast.Constant) and kwargs["testnet"].value is True
    assert isinstance(kwargs.get("demo"), ast.Constant) and kwargs["demo"].value is False

    endpoint_assignments = [
        node for node in ast.walk(init)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "expected_endpoint" for target in node.targets)
    ]
    assert endpoint_assignments, "Не найден защитный expected_endpoint"
    endpoint = endpoint_assignments[-1].value
    assert isinstance(endpoint, ast.Constant)
    assert endpoint.value == "https://api-testnet.bybit.com"


def test_startup_auth_check_does_not_place_orders():
    tree = _parse("main.py")
    client_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BybitClient"
    )
    init = next(
        node for node in client_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    called_methods = {
        node.func.attr for node in ast.walk(init)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    forbidden = {"place_order", "create_order", "cancel_order", "cancel_all_orders", "set_trading_stop"}
    assert not (called_methods & forbidden), (
        "Конструктор BybitClient не должен выставлять/отменять ордера или менять TP/SL"
    )
    assert "get_positions" in called_methods, "Не найдена read-only проверка авторизации"


def test_startup_logs_are_not_mislabeled_as_demo():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "BYBIT TESTNET CONNECTION CHECK OK" in source
    assert "BYBIT TESTNET CONNECTION CHECK FAILED" in source
    assert "BYBIT DEMO CONNECTION CHECK" not in source
