"""Wrapper instalable del producto de volatilidad diario legacy."""

from __future__ import annotations


def run() -> None:
    from volatility_model import main

    main()


if __name__ == "__main__":
    run()
