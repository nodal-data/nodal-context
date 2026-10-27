"""Restricted ACF expression grammar. Never executes input."""
import re


class MeasureParser:
    """Small recursive-descent grammar; never evaluates input or accepts SQL."""

    TOKEN = re.compile(
        r"\s*(?:(metric\s*\(\s*[A-Za-z_][A-Za-z0-9_.-]*\s*\))|"
        r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)|"
        r"((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)|([()+*/-]))")
    AGGREGATES = {"SUM", "COUNT", "AVG", "MIN", "MAX"}

    def __init__(self, measure):
        if not isinstance(measure, str) or not measure.strip():
            raise ValueError("measure must be a nonempty expression")
        self.tokens, self.columns, self.references = [], set(), set()
        self.has_aggregate = False
        pos = 0
        measure = measure.strip()
        while pos < len(measure):
            match = self.TOKEN.match(measure, pos)
            if not match:
                raise ValueError(f"unsupported measure syntax near {measure[pos:pos + 30]!r}")
            self.tokens.append(next((i, v) for i, v in enumerate(match.groups()) if v is not None))
            pos = match.end()
        self.index = 0

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else (None, "")

    def take(self, value=None):
        token = self.peek()
        if not token[1] or (value is not None and token[1] != value):
            raise ValueError(f"expected {value or 'operand'}, got {token[1] or 'end of measure'}")
        self.index += 1
        return token

    def parse(self):
        self.expression()
        if self.peek()[1]:
            raise ValueError(f"unexpected token {self.peek()[1]!r}")
        return self

    def expression(self):
        self.term()
        while self.peek()[1] in ("+", "-"):
            self.take()
            self.term()

    def term(self):
        self.atom()
        while self.peek()[1] in ("*", "/"):
            self.take()
            self.atom()

    def atom(self):
        kind, value = self.take()
        if value in ("+", "-"):
            self.atom()
        elif value == "(":
            self.expression()
            self.take(")")
        elif kind == 0:
            self.references.add(value[value.index("(") + 1:-1].strip())
        elif kind == 2:
            return
        elif kind == 1 and value.upper() in self.AGGREGATES:
            self.has_aggregate = True
            self.take("(")
            distinct = self.peek()[1].upper() == "DISTINCT"
            if distinct:
                self.take()
            arg_kind, arg = self.take()
            if arg == "*" and value.upper() == "COUNT" and not distinct:
                pass
            elif arg_kind == 1:
                self.columns.add(arg)
            else:
                raise ValueError("aggregate requires a column (or COUNT(*))")
            self.take(")")
        else:
            raise ValueError(f"unsupported operand {value!r}; use aggregates or metric(name)")


def filter_fields(filters):
    for item in filters or []:
        if "field" in item:
            yield item["field"]
        else:
            yield from filter_fields(item.get("any_of", item.get("all_of", [])))
