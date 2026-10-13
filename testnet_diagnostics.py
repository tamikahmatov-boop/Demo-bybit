#!/usr/bin/env python3
"""Безопасная read-only диагностика подключения к Bybit Testnet.

Запуск из корня репозитория:
    python testnet_diagnostics.py

Скрипт НЕ создаёт, не меняет и не отменяет ордера. Он проверяет:
1) флаги среды и точный REST endpoint;
2) публичный серверный API;
3) приватную авторизацию через чтение позиций;
4) чтение открытых линейных USDT-ордеров.

Использует API_KEY/API_SECRET из config.py. Не выводит ключи и секреты.
"""
from __future__ import annotations

import sys
from typing import Callable

from pybit.unified_trading import HTTP
import config as cfg


EXPECTED_ENDPOINT = "https://api-testnet.bybit.com"


def _safe_error(exc: BaseException) -> str:
    message = str(exc)
    for secret in (
        str(getattr(cfg, "API_KEY", "") or ""),
        str(getattr(cfg, "API_SECRET", "") or ""),
    ):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return f"{type(exc).__name__}: {message[:700]}"


def _check(label: str, action: Callable[[], object]) -> bool:
    try:
        result = action()
        if isinstance(result, dict) and result.get("retCode", 0) != 0:
            raise RuntimeError(
                f"Bybit retCode={result.get('retCode')}: {result.get('retMsg', 'unknown error')}"
            )
        print(f"[OK] {label}")
        return True
    except Exception as exc:
        print(f"[FAIL] {label}: {_safe_error(exc)}")
        return False


def main() -> int:
    if getattr(cfg, "TESTNET", None) is not True:
        print("[FAIL] config.TESTNET должен быть True. Остановка без запросов.")
        return 2
    if getattr(cfg, "DEMO_TRADING", False) is not False:
        print("[FAIL] config.DEMO_TRADING должен быть False для Testnet. Остановка без запросов.")
        return 2
    if not getattr(cfg, "API_KEY", "") or not getattr(cfg, "API_SECRET", ""):
        print("[FAIL] В config.py не заданы API_KEY/API_SECRET. Остановка без запросов.")
        return 2

    try:
        client = HTTP(
            testnet=True,
            demo=False,
            api_key=cfg.API_KEY,
            api_secret=cfg.API_SECRET,
            timeout=getattr(cfg, "REQUEST_TIMEOUT_SEC", 10),
            recv_window=20000,
        )
        # Явно фиксируем Testnet и затем проверяем фактический endpoint.
        client.endpoint = EXPECTED_ENDPOINT
    except Exception as exc:
        print(f"[FAIL] Создание Testnet-клиента: {_safe_error(exc)}")
        return 2

    actual_endpoint = str(getattr(client, "endpoint", "") or "").rstrip("/")
    if actual_endpoint != EXPECTED_ENDPOINT:
        print(
            "[FAIL] Неверный endpoint: "
            f"ожидался {EXPECTED_ENDPOINT}, получен {actual_endpoint or 'не определён'}"
        )
        return 2
    print(f"[OK] REST endpoint заблокирован на {EXPECTED_ENDPOINT}")

    results = []
    results.append(_check("Публичный API / server time", client.get_server_time))
    # Приватные проверки только читают данные аккаунта.
    results.append(
        _check(
            "Приватная авторизация / позиции USDT Perpetual",
            lambda: client.get_positions(category="linear", settleCoin="USDT"),
        )
    )
    results.append(
        _check(
            "Чтение открытых ордеров USDT Perpetual",
            lambda: client.get_open_orders(category="linear", settleCoin="USDT", limit=1),
        )
    )

    passed = sum(results)
    failed = len(results) - passed
    print(f"\nИТОГ: успешно {passed}/{len(results)}, ошибок {failed}.")
    if failed:
        print(
            "Если получен ErrCode 10003, ключи, вероятно, созданы не для Testnet "
            "или подключение идёт не к той среде. Создайте ключи на "
            "https://testnet.bybit.com/app/user/api-management."
        )
        print("Ордера не размещались и не изменялись.")
        return 1

    print("Диагностика завершена. Скрипт не размещал и не изменял ордера.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
