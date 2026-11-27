# Code reference

These pages are generated automatically from the docstrings and type hints in the source code, using [mkdocstrings](https://mkdocstrings.github.io/). They're always in sync with the code. Expand **Source code** under any function to read its implementation.

| Page | Modules |
|---|---|
| [Config & pipeline](core.md) | `coin_buddy.config`, `coin_buddy.pipeline` |
| [Data sources](data.md) | `coin_buddy.data.market`, `coin_buddy.data.sentiment` |
| [Analytics](analytics.md) | `coin_buddy.indicators`, `coin_buddy.signals`, `coin_buddy.backtest`, `coin_buddy.ml` |
| [App layer](app.md) | `coin_buddy.storage`, `coin_buddy.alerts`, `coin_buddy.charts`, `coin_buddy.cli`, `coin_buddy.web.server` |

For how the modules fit together, start with the [Architecture overview](../architecture/overview.md).

!!! tip "Where to start reading the code"
    1. `pipeline.take_snapshot`: one live signal, end to end.
    2. `signals.evaluate`: how votes become a decision.
    3. `backtest.run_backtest`: the cost and timing model in about 20 lines.
    4. `ml.walk_forward`: honest model evaluation.
