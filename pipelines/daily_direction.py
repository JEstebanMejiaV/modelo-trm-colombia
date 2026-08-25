"""Wrapper instalable del entry point legacy de pronóstico diario."""

from __future__ import annotations


def run() -> None:
    from forecast_daily.run import main

    main()


if __name__ == "__main__":
    run()
