from __future__ import annotations

import ast

from scripts import check_architecture_debt as debt


def test_function_nesting_ignores_nested_helpers() -> None:
    tree = ast.parse(
        """
def outer():
    if ready:
        def helper():
            if first:
                if second:
                    return True

        class Local:
            def method(self):
                if nested:
                    if deeper:
                        return True

        return helper()
"""
    )

    metrics = debt.function_metrics(tree)

    assert metrics["outer"].nesting == 1
    assert metrics["outer.helper"].nesting == 2
    assert metrics["outer.Local.method"].nesting == 2
