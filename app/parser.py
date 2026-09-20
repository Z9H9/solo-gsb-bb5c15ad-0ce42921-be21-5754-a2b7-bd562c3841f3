"""编织行指令的解析、展开与求值。

语法（大小写不敏感，可用空格 / 逗号 / 分号分隔）：

    row      := sequence
    sequence := item*
    item     := atom | group
    atom     := ("k" | "inc" | "dec") NUMBER
    group    := "[" sequence "]" "*" NUMBER

语义：
    kN       消耗 N 针，产出 N 针（平针）
    incN     消耗 1 针，产出 N 针（加针）
    decN     消耗 N 针，产出 1 针（减针）
    [seq]*M  将 seq 依次重复 M 次，可嵌套
"""

from __future__ import annotations

from dataclasses import dataclass

# 单行展开后的最大执行步数，防止失控输入（如 [[inc9]*9]*9]*9 …）拖垮服务
MAX_EXPAND_STEPS = 200_000
# 返回给前端展示的展开序列最大条数
EXPANSION_PREVIEW_LIMIT = 120


class ParseError(Exception):
    """指令语法错误。pos 为源串中的字符下标（0 起）。"""

    def __init__(self, message: str, pos: int):
        self.message = message
        self.pos = pos
        super().__init__(message)


class ExpansionTooLarge(Exception):
    """展开步数超过上限。"""


@dataclass
class Atom:
    kind: str  # 'k' | 'inc' | 'dec'
    n: int
    start: int  # 源串中的起止下标，用于错误定位高亮
    end: int

    @property
    def need(self) -> int:
        """执行该指令所需（消耗）的针数。"""
        return 1 if self.kind == "inc" else self.n

    @property
    def make(self) -> int:
        """执行该指令产出的针数。"""
        return 1 if self.kind == "dec" else self.n

    def label(self) -> str:
        return f"{self.kind}{self.n}"


@dataclass
class Group:
    items: list
    times: int
    start: int
    end: int


# ---------------------------------------------------------------- 解析


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def parse(self) -> list:
        items = self._sequence(top_level=True)
        self._skip_sep()
        if self.pos < len(self.text):
            raise ParseError(f"无法识别的字符 {self.text[self.pos]!r}", self.pos)
        return items

    def _skip_sep(self) -> None:
        while self.pos < len(self.text) and (
            self.text[self.pos].isspace() or self.text[self.pos] in ",;"
        ):
            self.pos += 1

    def _sequence(self, top_level: bool) -> list:
        items = []
        while True:
            self._skip_sep()
            if self.pos >= len(self.text):
                if top_level:
                    return items
                raise ParseError("缺少右括号 ']'", self.pos)
            ch = self.text[self.pos]
            if ch == "]":
                if top_level:
                    raise ParseError("多余的右括号 ']'", self.pos)
                return items
            items.append(self._item())

    def _item(self):
        if self.text[self.pos] == "[":
            return self._group()
        return self._atom()

    def _group(self) -> Group:
        start = self.pos
        self.pos += 1  # 消耗 '['
        items = self._sequence(top_level=False)
        self.pos += 1  # 消耗 ']'
        self._skip_sep()
        if self.pos >= len(self.text) or self.text[self.pos] != "*":
            raise ParseError("分组的 ']' 之后必须紧跟 '*重复次数'，如 [k2 inc2]*3", start)
        self.pos += 1
        times = self._number()
        if times < 1:
            raise ParseError("重复次数必须 ≥ 1", self.pos - 1)
        if not items:
            raise ParseError("分组内容不能为空", start)
        return Group(items=items, times=times, start=start, end=self.pos)

    def _atom(self) -> Atom:
        start = self.pos
        head3 = self.text[self.pos : self.pos + 3].lower()
        if head3 == "inc":
            kind, self.pos = "inc", self.pos + 3
        elif head3 == "dec":
            kind, self.pos = "dec", self.pos + 3
        elif self.text[self.pos].lower() == "k":
            kind, self.pos = "k", self.pos + 1
        else:
            raise ParseError(
                f"无法识别的指令 {self.text[self.pos]!r}，"
                "应为 kN / incN / decN / [序列]*M",
                start,
            )
        n = self._number()
        if n < 1:
            raise ParseError("针数必须 ≥ 1", start)
        return Atom(kind=kind, n=n, start=start, end=self.pos)

    def _number(self) -> int:
        self._skip_sep()
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos].isdigit():
            self.pos += 1
        if self.pos == start:
            raise ParseError("此处应为数字", self.pos)
        return int(self.text[start : self.pos])


def parse(text: str) -> list:
    """把一行指令解析为 AST（Atom / Group 列表）。"""
    return _Parser(text).parse()


# ---------------------------------------------------------------- 求值


class InsufficientStitches(Exception):
    """执行到某条源指令时剩余针数不足。

    reps 记录从外到内的分组重复上下文：((group, 第几次重复), ...)
    """

    def __init__(self, atom: Atom, available: int, reps: tuple):
        self.atom = atom
        self.available = available
        self.reps = reps
        super().__init__(f"针数不足：需要 {atom.need}，仅剩 {available}")


def _eval_sequence(items, available, expansion, steps, reps=()):
    """顺序执行指令序列，返回 (消耗, 产出, 剩余可用)。"""
    consumed = produced = 0
    for item in items:
        if isinstance(item, Atom):
            if item.need > available:
                raise InsufficientStitches(item, available, reps)
            # 本行新产出的针放到另一根针上，行内不可再被消耗，
            # 因此 available 只随消耗减少；行末剩下的即未消耗针数。
            available -= item.need
            consumed += item.need
            produced += item.make
            steps[0] += 1
            if steps[0] > MAX_EXPAND_STEPS:
                raise ExpansionTooLarge
            if len(expansion) < EXPANSION_PREVIEW_LIMIT:
                expansion.append(item.label())
        else:
            for r in range(1, item.times + 1):
                c, p, available = _eval_sequence(
                    item.items, available, expansion, steps, reps + ((item, r),)
                )
                consumed += c
                produced += p
    return consumed, produced, available


# ---------------------------------------------------------------- 行 / 方案求值


def _err(message, start, end, **extra):
    return {"message": message, "position": {"start": start, "end": end}, **extra}


def evaluate_plan(start: int, rows: list) -> list:
    """逐行求值整个方案。

    上一行的产出（含未消耗的留针）作为下一行的可用针数；
    某行出现语法错误或针数不足时，后续行标记为 blocked。
    """
    results = []
    available = start
    blocked = False

    for i, raw in enumerate(rows):
        src = raw if isinstance(raw, str) else ""
        base = {
            "index": i,
            "source": src,
            "available": None,
            "consumed": None,
            "produced": None,
            "remaining": None,
            "expansion": [],
            "expansionTotal": 0,
            "error": None,
        }

        if blocked:
            results.append({**base, "status": "blocked"})
            continue

        if not src.strip():
            # 空行：针数原样传递到下一行
            results.append(
                {
                    **base,
                    "status": "empty",
                    "available": available,
                    "consumed": 0,
                    "produced": 0,
                    "remaining": 0,
                }
            )
            continue

        base["available"] = available

        try:
            items = parse(src)
        except ParseError as e:
            pos = min(e.pos, len(src))
            results.append(
                {
                    **base,
                    "status": "error",
                    "error": _err(
                        f"语法错误：{e.message}",
                        pos,
                        min(pos + 1, len(src)),
                        type="parse",
                    ),
                }
            )
            blocked = True
            continue

        expansion: list = []
        steps = [0]
        try:
            consumed, produced, remaining = _eval_sequence(items, available, expansion, steps)
        except InsufficientStitches as e:
            atom = e.atom
            message = (
                f"执行到 “{src[atom.start:atom.end]}” 时针数不足："
                f"需要 {atom.need} 针，仅剩 {e.available} 针"
                f"（短缺 {atom.need - e.available} 针）"
            )
            repetition = []
            for group, r in e.reps:
                label = src[group.start : group.end]
                repetition.append({"context": label, "rep": r, "times": group.times})
                message += f"；位于 “{label}” 的第 {r} 次重复"
            results.append(
                {
                    **base,
                    "status": "error",
                    "error": _err(
                        message,
                        atom.start,
                        atom.end,
                        type="insufficient",
                        instruction=atom.label(),
                        need=atom.need,
                        left=e.available,
                        short=atom.need - e.available,
                        repetition=repetition,
                    ),
                }
            )
            blocked = True
            continue
        except ExpansionTooLarge:
            results.append(
                {
                    **base,
                    "status": "error",
                    "error": _err(
                        f"展开步数超过上限（{MAX_EXPAND_STEPS} 步），请检查重复次数",
                        0,
                        len(src),
                        type="too_large",
                    ),
                }
            )
            blocked = True
            continue

        error = None
        status = "ok"
        if remaining > 0:
            status = "error"
            stripped_end = len(src.rstrip())
            error = _err(
                f"行末剩余 {remaining} 针未被消耗",
                stripped_end,
                stripped_end,
                type="unconsumed",
                unconsumed=remaining,
            )

        results.append(
            {
                **base,
                "status": status,
                "consumed": consumed,
                "produced": produced,
                "remaining": remaining,
                "expansion": expansion,
                "expansionTotal": steps[0],
                "error": error,
            }
        )
        # 未消耗的针仍留在针上，计入下一行可用针数
        available = produced + remaining

    return results
