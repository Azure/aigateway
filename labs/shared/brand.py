"""Branded output for the Azure AI Gateway lab notebooks.

The cells show their results as cards in the style of the labs site: the same Fluent palette, Segoe UI and Cascadia
Code type, pill badges, and the AI Gateway gradient. Every helper returns an object that renders as HTML in Jupyter
and VS Code, and as plain text anywhere else:

    import sys; sys.path.insert(0, "../shared")
    from IPython.display import display
    import brand

    display(brand.reply(text, "Chat Completions API", model="gpt-5-mini", tokens=(12, 48)))
    display(brand.checks("Runtime checks", [("Without a key", 401, 401), ("With the key", 200, 200)]))

    board = brand.Board("Burst", ["Request", "Status", "Tokens used"], budget=1000)   # updates in place
    board.add([1, brand.status(200), 225], status=200, amount=225)

    display(brand.usage_chart("Burst", [(200, 225), (200, 231), (429, None)], limit=1000))   # needs matplotlib

The cards follow the light or dark theme of VS Code and JupyterLab, and stay readable as light cards elsewhere.
Nothing here prints a secret: `key` and `masked` show only the first four characters.
"""

from __future__ import annotations

import base64 as _base64
import html as _html
import io as _io
import itertools as _itertools
import json as _json
import re as _re
import time as _time

FONT = ('"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", Aptos, -apple-system, BlinkMacSystemFont, '
        'system-ui, "Helvetica Neue", Arial, sans-serif')
DISPLAY_FONT = ('"Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI", Aptos, -apple-system, '
                'BlinkMacSystemFont, system-ui, sans-serif')
MONO = '"Cascadia Code", "Cascadia Mono", "SF Mono", ui-monospace, Menlo, Consolas, monospace'
GRADIENT = "linear-gradient(90deg, #0faeff 0%, #7e5be8 55%, #bb45ea 100%)"   # the AI Gateway mark

# The labs site tokens (labs/site/css/01-tokens.css), light and dark.
LIGHT = {
    "bg": "#ffffff", "bg2": "#fafafa", "bg3": "#f5f5f5", "track": "#ebebeb", "code": "#fafafb",
    "fg": "#242424", "fg2": "#424242", "fg3": "#616161", "stroke": "#e0e0e0", "stroke2": "#ebebeb",
    "brand": "#0f6cbd", "brand-bg": "#ebf3fc", "brand-stroke": "#b4d6fa",
    "violet": "#5637c9", "violet-bg": "#f4f0ff", "violet-stroke": "#cdbff7",
    "ok": "#107c10", "ok-bg": "#f1faf1", "ok-stroke": "#9fd89f",
    "warn": "#bc4b09", "warn-bg": "#fff9f5", "warn-stroke": "#fdcfb4",
    "bad": "#c50f1f", "bad-bg": "#fdf3f4", "bad-stroke": "#eeacb2",
    "shadow": "0 1px 2px rgba(0, 0, 0, .06), 0 4px 12px rgba(0, 0, 0, .05)",
}
DARK = {
    "bg": "#1f1f24", "bg2": "#26262c", "bg3": "#2a2a30", "track": "#34343c", "code": "#1b1b20",
    "fg": "#f3f3f5", "fg2": "#d4d4d9", "fg3": "#a9a9b2", "stroke": "#3b3b44", "stroke2": "#2e2e35",
    "brand": "#62abf5", "brand-bg": "rgba(71, 158, 245, .12)", "brand-stroke": "rgba(98, 171, 245, .4)",
    "violet": "#b9a5ff", "violet-bg": "rgba(142, 91, 255, .14)", "violet-stroke": "rgba(165, 139, 255, .4)",
    "ok": "#6cc56c", "ok-bg": "rgba(84, 176, 84, .1)", "ok-stroke": "rgba(84, 176, 84, .4)",
    "warn": "#f2a35e", "warn-bg": "rgba(242, 163, 94, .09)", "warn-stroke": "rgba(242, 163, 94, .38)",
    "bad": "#f1707b", "bad-bg": "rgba(241, 112, 123, .09)", "bad-stroke": "rgba(241, 112, 123, .4)",
    "shadow": "0 6px 16px rgba(0, 0, 0, .35)",
}
# Hosts that tell the page they use a dark theme: VS Code, JupyterLab and Notebook 7, and Google Colab.
DARK_HOSTS = ("body.vscode-dark", "body.vscode-high-contrast:not(.vscode-high-contrast-light)",
              'body[data-jp-theme-light="false"]', 'html[theme="dark"]')

TONES = ("neutral", "brand", "violet", "ok", "warn", "bad")
_GLYPHS = {"neutral": "·", "brand": "•", "violet": "•", "ok": "✓", "warn": "!", "bad": "✕", "wait": "…"}


def _tokens(palette: dict) -> str:
    return "".join(f"--aigw-{name}:{value};" for name, value in palette.items())


_CSS = f"""
.aigw{{{_tokens(LIGHT)}font:14px/1.5 {FONT};-webkit-font-smoothing:antialiased}}
{",".join(f"{host} .aigw" for host in DARK_HOSTS)}{{{_tokens(DARK)}}}
.aigw *{{box-sizing:border-box}}
.aigw .aigw-card{{position:relative;max-width:960px;margin:6px 0 12px;overflow:hidden;background:var(--aigw-bg);
  border:1px solid var(--aigw-stroke);border-radius:12px;box-shadow:var(--aigw-shadow);color:var(--aigw-fg)}}
.aigw .aigw-card::before{{content:"";position:absolute;inset:0 0 auto;height:2px;background:{GRADIENT}}}
.aigw .aigw-hd{{display:flex;align-items:center;gap:12px;padding:14px 18px 0}}
.aigw .aigw-end{{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;margin-left:auto}}
.aigw .aigw-t{{margin:0;font:600 15px/1.35 {DISPLAY_FONT};letter-spacing:-.01em;color:var(--aigw-fg)}}
.aigw .aigw-sub{{margin-top:1px;font-size:13px;color:var(--aigw-fg3);overflow-wrap:anywhere}}
.aigw .aigw-bd{{padding:12px 18px 16px}}
.aigw .aigw-blk+.aigw-blk{{margin-top:14px}}
.aigw .aigw-h{{margin:0 0 6px;font-size:13px;font-weight:600;color:var(--aigw-fg2)}}
.aigw .aigw-m{{font:12.5px/1.5 {MONO};overflow-wrap:anywhere}}
.aigw .aigw-mut{{color:var(--aigw-fg3)}}
.aigw a{{color:var(--aigw-brand);text-decoration:none}}
.aigw a:hover{{text-decoration:underline}}
.aigw .aigw-kv{{display:grid;grid-template-columns:minmax(110px,max-content) minmax(0,1fr);gap:7px 20px;align-items:baseline}}
.aigw .aigw-k{{font-size:13px;color:var(--aigw-fg3)}}
.aigw .aigw-v{{min-width:0;color:var(--aigw-fg);overflow-wrap:anywhere}}
.aigw .aigw-chip{{display:inline-flex;align-items:center;gap:6px;height:22px;padding:0 9px;border-radius:999px;
  border:1px solid var(--c-stroke);background:var(--c-bg);color:var(--c);font:600 12px/1 {FONT};white-space:nowrap;
  font-variant-numeric:tabular-nums}}
.aigw .aigw-chip.aigw-code{{font:600 12px/1 {MONO}}}
.aigw .aigw-chips{{display:flex;flex-wrap:wrap;gap:6px}}
.aigw .aigw-neutral{{--c:var(--aigw-fg2);--c-bg:var(--aigw-bg3);--c-stroke:var(--aigw-stroke)}}
.aigw .aigw-brand{{--c:var(--aigw-brand);--c-bg:var(--aigw-brand-bg);--c-stroke:var(--aigw-brand-stroke)}}
.aigw .aigw-violet{{--c:var(--aigw-violet);--c-bg:var(--aigw-violet-bg);--c-stroke:var(--aigw-violet-stroke)}}
.aigw .aigw-ok{{--c:var(--aigw-ok);--c-bg:var(--aigw-ok-bg);--c-stroke:var(--aigw-ok-stroke)}}
.aigw .aigw-warn{{--c:var(--aigw-warn);--c-bg:var(--aigw-warn-bg);--c-stroke:var(--aigw-warn-stroke)}}
.aigw .aigw-bad{{--c:var(--aigw-bad);--c-bg:var(--aigw-bad-bg);--c-stroke:var(--aigw-bad-stroke)}}
.aigw .aigw-wait{{--c:var(--aigw-fg3);--c-bg:transparent;--c-stroke:var(--aigw-stroke)}}
.aigw .aigw-tw{{overflow-x:auto}}
.aigw table.aigw-tb{{width:100%;margin:0;border-collapse:collapse;table-layout:auto;font-size:13px;color:var(--aigw-fg)}}
.aigw table.aigw-tb th{{padding:0 14px 7px 0;border:0;border-bottom:1px solid var(--aigw-stroke);background:transparent;
  text-align:left;font-size:12px;font-weight:600;color:var(--aigw-fg3);white-space:nowrap}}
.aigw table.aigw-tb td{{padding:7px 14px 7px 0;border:0;border-bottom:1px solid var(--aigw-stroke2);background:transparent;
  text-align:left;vertical-align:middle;color:var(--aigw-fg)}}
.aigw table.aigw-tb tr:nth-child(n),.aigw table.aigw-tb tr:nth-child(n):hover{{background:transparent}}
.aigw table.aigw-tb tr:last-child td{{border-bottom:0}}
.aigw table.aigw-tb .aigw-n{{text-align:right;font-variant-numeric:tabular-nums}}
.aigw table.aigw-tb th{{white-space:nowrap}}
.aigw table.aigw-tb .aigw-m{{overflow-wrap:break-word}}
.aigw .aigw-tw{{overflow-x:auto}}
.aigw table.aigw-tb tr.aigw-new td{{animation:aigw-in .5s cubic-bezier(.2,.8,.2,1)}}
.aigw .aigw-quote{{max-width:76ch;padding:12px 14px;border:1px solid var(--aigw-stroke2);border-radius:8px;
  background:var(--aigw-bg2);font-size:14.5px;line-height:1.6;color:var(--aigw-fg);white-space:pre-wrap;overflow-wrap:anywhere}}
.aigw .aigw-quote.aigw-empty{{color:var(--aigw-fg3)}}
.aigw .aigw-quote.aigw-md{{max-width:88ch;white-space:normal}}
.aigw .aigw-md>*{{margin:0 0 10px}}
.aigw .aigw-md>*:last-child{{margin-bottom:0}}
.aigw .aigw-md ul,.aigw .aigw-md ol{{padding-left:22px}}
.aigw .aigw-md li{{margin:2px 0}}
.aigw .aigw-md code{{padding:1px 5px;border-radius:4px;background:var(--aigw-code);font:12.5px/1.5 {MONO}}}
.aigw .aigw-md pre.aigw-pre code{{padding:0;background:transparent}}
.aigw .aigw-md .aigw-h{{margin-top:4px;font-size:14px;color:var(--aigw-fg)}}
.aigw .aigw-caret{{display:inline-block;width:7px;height:1.05em;margin-left:2px;vertical-align:-2px;border-radius:1px;
  background:{GRADIENT};animation:aigw-blink 1s steps(2,start) infinite}}
.aigw pre.aigw-pre{{max-height:320px;margin:0;padding:10px 12px;overflow:auto;border:1px solid var(--aigw-stroke2);
  border-radius:8px;background:var(--aigw-code);color:var(--aigw-fg);font:12.5px/1.55 {MONO};white-space:pre-wrap;
  overflow-wrap:anywhere}}
.aigw details>summary{{cursor:pointer;font-size:13px;font-weight:600;color:var(--aigw-brand)}}
.aigw details[open]>summary{{margin-bottom:8px}}
.aigw .aigw-gauge{{display:grid;gap:6px}}
.aigw .aigw-gl{{display:flex;justify-content:space-between;gap:12px;font-size:13px;color:var(--aigw-fg3)}}
.aigw .aigw-gl b{{font:600 12.5px/1.5 {MONO};color:var(--c)}}
.aigw .aigw-gt{{height:6px;overflow:hidden;border-radius:999px;background:var(--aigw-track)}}
.aigw .aigw-gf{{height:100%;border-radius:999px;background:var(--c);transition:width .4s cubic-bezier(.2,.8,.2,1)}}
.aigw .aigw-hit+.aigw-hit{{margin-top:12px;padding-top:12px;border-top:1px solid var(--aigw-stroke2)}}
.aigw .aigw-hit a{{font-weight:600}}
.aigw .aigw-hit .aigw-m{{display:block;font-size:12px;color:var(--aigw-fg3)}}
.aigw .aigw-hit p{{max-width:76ch;margin:4px 0 0;color:var(--aigw-fg2)}}
.aigw .aigw-note{{display:flex;align-items:baseline;gap:9px;max-width:960px;margin:2px 0;font-size:13.5px;color:inherit}}
.aigw .aigw-note::before{{content:"";flex:none;width:8px;height:8px;border-radius:50%;background:var(--c);
  transform:translateY(-1px)}}
.aigw .aigw-note.aigw-wait::before{{background:transparent;border:1.5px solid var(--c)}}
.aigw .aigw-note .aigw-m{{opacity:.8}}
.aigw .aigw-figw{{overflow-x:auto}}
.aigw .aigw-fig{{display:block;width:100%;min-width:560px;height:auto}}
.aigw .aigw-fig-dk{{display:none}}
{",".join(f"{host} .aigw .aigw-fig-lt" for host in DARK_HOSTS)}{{display:none}}
{",".join(f"{host} .aigw .aigw-fig-dk" for host in DARK_HOSTS)}{{display:block}}
@keyframes aigw-blink{{to{{visibility:hidden}}}}
@keyframes aigw-in{{from{{background:var(--aigw-brand-bg)}}}}
@media (prefers-reduced-motion:reduce){{.aigw *{{animation:none!important;transition:none!important}}}}
"""
_STYLE = "<style>" + " ".join(line.strip() for line in _CSS.strip().splitlines()) + "</style>"


# Building blocks -----------------------------------------------------------------------------------------------------

class Html(str):
    """Markup that the helpers insert as is, with a plain-text version. Any other value is escaped."""

    def __new__(cls, markup: str, text: str = ""):
        value = super().__new__(cls, markup)
        value.text = text
        return value


def _e(value) -> str:
    if isinstance(value, Html):
        return value
    if isinstance(value, View):
        return value.markup
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    return _html.escape(str(value))


def _plain(value) -> str:
    if isinstance(value, (Html, View)):
        return value.text
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _tone(tone: str) -> str:
    if tone not in TONES and tone != "wait":
        raise ValueError(f"tone must be one of {', '.join(TONES)}, or wait")
    return f"aigw-{tone}"


class View:
    """A rendered output: HTML for notebooks, plain text for everything else."""

    def __init__(self, markup: str, text: str):
        self.markup, self.text = markup, text

    def _repr_html_(self) -> str:
        return f'{_STYLE}<div class="aigw">{self.markup}</div>'

    def __repr__(self) -> str:
        return self.text

    __str__ = __repr__


def mono(value) -> Html:
    """Show a value in Cascadia Code: URLs, IDs, names, headers, and other data."""
    return Html(f'<span class="aigw-m">{_e(value)}</span>', _plain(value))


def masked(secret: str | None) -> Html:
    """Show the first four characters of a key or token, never the rest."""
    shown = f"{secret[:4]}…" if secret else "none"
    return Html(f'<span class="aigw-m">{_html.escape(shown)}</span>', shown)


def link(url: str, text: str | None = None) -> Html:
    label = text or url
    return Html(f'<a href="{_html.escape(url, quote=True)}" target="_blank" rel="noopener">{_html.escape(label)}</a>',
                f"{label} ({url})" if text else url)


def chip(text, tone: str = "neutral", code: bool = False) -> Html:
    """A pill badge. Tones: neutral, brand, violet, ok, warn, bad."""
    extra = " aigw-code" if code else ""
    return Html(f'<span class="aigw-chip {_tone(tone)}{extra}">{_e(text)}</span>', f"[{_plain(text)}]")


def chips(*items) -> Html:
    return Html('<div class="aigw-chips">' + "".join(_e(i) for i in items) + "</div>",
                " ".join(_plain(i) for i in items))


def status_tone(code: int) -> str:
    if 200 <= code < 300:
        return "ok"
    if code == 429:
        return "warn"
    return "bad" if code >= 400 else "brand"


def status(code: int, tone: str | None = None) -> Html:
    """An HTTP status badge: 2xx green, 429 amber, other errors red."""
    return chip(int(code), tone or status_tone(int(code)), code=True)


def kv(rows) -> Html:
    """Label and value pairs. Wrap a value in mono() to show it as data."""
    rows = list(rows)
    labels = [k.text if isinstance(k, Html) else str(k) for k, _ in rows]
    width = max(map(len, labels), default=0)
    cells = "".join(f'<div class="aigw-k">{_e(k)}</div><div class="aigw-v">{_e(v)}</div>' for k, v in rows)
    return Html(f'<div class="aigw-kv">{cells}</div>',
                "\n".join(f"{label:<{width}}  {_plain(v)}" for label, (_, v) in zip(labels, rows)))


def usd(value, digits: int = 6) -> str:
    """A US dollar amount: usd(0.0001003) is $0.000100, and round amounts stay short: usd(0.001) is $0.001."""
    if value is None or value == "":
        return "-"
    text = f"{float(value):,.{digits}f}"
    short = text.rstrip("0").rstrip(".")
    decimals = len(short.split(".")[1]) if "." in short else 0
    if decimals <= 3:
        text = short + ("0" if decimals == 1 else "")
    return f"${text}"


def _amount(value, unit: str) -> str:
    return usd(value) if unit == "USD" else f"{value:,.0f} {unit}" if unit else f"{value:,.0f}"


def _numeric(cell) -> bool:
    if isinstance(cell, str):
        return bool(_re.fullmatch(r"\$?\d[\d,]*(\.\d+)?", cell))
    return isinstance(cell, (int, float)) and not isinstance(cell, bool)


def grid(columns, rows, fresh: int = -1) -> Html:
    """A table. Number columns align right; the row at index `fresh` flashes once, for live tables."""
    blank = (None, "", "-", "—")
    numeric = [any(_numeric(r[i]) for r in rows if i < len(r))
               and all(_numeric(r[i]) or r[i] in blank for r in rows if i < len(r))
               for i in range(len(columns))]
    right = ' class="aigw-n"'

    def cell(i, value):
        shown = f"{int(value):,}" if isinstance(value, str) and value.isdigit() else _e("" if value is None else value)
        return f"<td{right if i < len(numeric) and numeric[i] else ''}>{shown}</td>"

    head = "".join(f"<th{right if numeric[i] else ''}>{_e(c)}</th>" for i, c in enumerate(columns))
    fresh_row = ' class="aigw-new"'
    body = "".join(f"<tr{fresh_row if n == fresh else ''}>" + "".join(cell(i, c) for i, c in enumerate(row)) + "</tr>"
                   for n, row in enumerate(rows))
    lines = [[_plain(c) for c in columns]] + [[_plain(c) for c in row] for row in rows]
    widths = [max(len(line[i]) for line in lines if i < len(line)) for i in range(len(columns))]
    text = "\n".join("  ".join(v.ljust(w) for v, w in zip(line, widths)).rstrip() for line in lines)
    return Html(f'<div class="aigw-tw"><table class="aigw-tb"><thead><tr>{head}</tr></thead>'
                f"<tbody>{body}</tbody></table></div>", text)


def pre(text: str) -> Html:
    return Html(f'<pre class="aigw-pre">{_html.escape(text)}</pre>', text)


def quote(text: str) -> Html:
    return Html(f'<div class="aigw-quote">{_html.escape(text)}</div>', text)


def _inline(text: str) -> str:
    """Escape a line, then render `code`, **bold**, and [links](https://...)."""
    parts = _re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if len(part) > 1 and part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{_html.escape(part[1:-1])}</code>")
            continue
        part = _html.escape(part, quote=False)
        part = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", part)
        part = _re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
                       lambda m: f'<a href="{m[2].replace(chr(34), "&quot;")}" target="_blank" rel="noopener">{m[1]}</a>', part)
        out.append(part)
    return "".join(out)


def markdown(text: str) -> Html:
    """An agent's Markdown answer: paragraphs, headings, lists, tables, code, bold, and links. HTML stays escaped."""
    blocks, lines, i = [], text.strip().splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.lstrip().startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("```"):
                j += 1
            blocks.append(f'<pre class="aigw-pre">{_html.escape(chr(10).join(lines[i + 1:j]))}</pre>')
            i = j + 1
        elif line.lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in lines[i:j]]
            rows = [r for r in rows if not all(_re.fullmatch(r":?-{2,}:?", c) for c in r)]
            head = "".join(f"<th>{_inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            blocks.append(f'<div class="aigw-tw"><table class="aigw-tb"><thead><tr>{head}</tr></thead>'
                          f"<tbody>{body}</tbody></table></div>")
            i = j
        elif _re.match(r"\s*([-*]|\d+\.)\s", line):
            tag = "ol" if _re.match(r"\s*\d+\.", line) else "ul"
            items = []
            while i < len(lines) and lines[i].strip():
                item = _re.match(r"\s*(?:[-*]|\d+\.)\s+(.*)", lines[i])
                if item:
                    items.append(item[1])
                elif items:
                    items[-1] += " " + lines[i].strip()
                i += 1
            blocks.append(f"<{tag}>" + "".join(f"<li>{_inline(t)}</li>" for t in items) + f"</{tag}>")
        elif _re.match(r"#{1,6}\s", line):
            blocks.append(f'<div class="aigw-h">{_inline(line.lstrip("#").strip())}</div>')
            i += 1
        else:
            j = i
            while j < len(lines) and lines[j].strip() and not _re.match(r"\s*([-*]|\d+\.|\||```|#{1,6}\s)", lines[j]):
                j += 1
            j = max(j, i + 1)
            blocks.append("<p>" + "<br>".join(_inline(l) for l in lines[i:j]) + "</p>")
            i = j
    return Html(f'<div class="aigw-quote aigw-md">{"".join(blocks)}</div>', text)


_markdown = markdown   # reply() has a parameter of the same name


def section(title: str, block) -> Html:
    """A heading over a block, inside a card."""
    return Html(f'<div class="aigw-h">{_e(title)}</div>{_e(block)}', f"{title}\n{_plain(block)}")


def gauge(used: float, total: float, label: str, unit: str = "tokens") -> Html:
    """A budget bar: blue under 70%, amber under 100%, red when the budget is used up. `unit` USD shows dollars."""
    share = used / total if total else 0
    tone = "brand" if share < .7 else "warn" if share < 1 else "bad"
    bar = "#" * min(20, round(share * 20))
    shown = f"{usd(used)} / {usd(total)}" if unit == "USD" else f"{used:,} / {total:,} {unit}"
    return Html(
        f'<div class="aigw-gauge {_tone(tone)}" role="meter" aria-valuemin="0" aria-valuemax="{total}" '
        f'aria-valuenow="{used}" aria-label="{_html.escape(label)}"><div class="aigw-gl"><span>{_e(label)}</span>'
        f"<b>{_e(shown)}</b></div>"
        f'<div class="aigw-gt"><div class="aigw-gf" style="width:{min(share, 1) * 100:.1f}%"></div></div></div>',
        f"{label}: {shown} [{bar:<20}]")


def details(summary: str, block) -> Html:
    return Html(f"<details><summary>{_e(summary)}</summary>{_e(block)}</details>", f"{summary}\n{_plain(block)}")


def card(title: str, *blocks, sub=None, badge: Html | None = None) -> View:
    """A card with a title, an optional subtitle and badge, and blocks stacked below. Blocks can be views."""
    sub_html = f'<div class="aigw-sub">{_e(sub)}</div>' if sub else ""
    end = f'<div class="aigw-end">{badge}</div>' if badge else ""
    body = "".join(f'<div class="aigw-blk">{_e(b)}</div>' for b in blocks if b is not None)
    markup = (f'<div class="aigw-card"><div class="aigw-hd"><div><div class="aigw-t">{_e(title)}</div>{sub_html}</div>'
              f'{end}</div><div class="aigw-bd">{body}</div></div>')
    head = title + (f" · {_plain(sub)}" if sub else "") + (f"  {badge.text}" if badge else "")
    text = "\n\n".join(_plain(b) for b in blocks if b is not None)
    return View(markup, f"{head}\n{'─' * min(len(head), 80)}\n{text}")


# Cards for the labs --------------------------------------------------------------------------------------------------

def info(title: str, rows, sub=None, badge: Html | None = None) -> View:
    """A card of label and value pairs."""
    return card(title, kv(rows), sub=sub, badge=badge)


def table(title: str, columns, rows, sub=None, badge: Html | None = None) -> View:
    return card(title, grid(columns, [list(r) for r in rows]), sub=sub, badge=badge)


def note(text: str, tone: str = "brand", code=None) -> View:
    """A one-line status. Tones: ok, brand, warn, bad, neutral, and wait for work in progress."""
    extra = f' <span class="aigw-m">{_e(code)}</span>' if code is not None else ""
    plain = f"{_GLYPHS.get(tone, '•')} {text}" + (f"  {_plain(code)}" if code is not None else "")
    return View(f'<div class="aigw-note {_tone(tone)}"><span>{_e(text)}{extra}</span></div>', plain)


def key(name: str, value: str, created: bool | None = None) -> View:
    """Say which runtime key the notebook uses, showing only its first four characters."""
    verb = "Key" if created is None else "Created key" if created else "Reusing key"
    return note(f"{verb} {name}", "ok" if created else "brand", masked(value))


def checks(title: str, rows, sub=None) -> View:
    """A pass or fail board. Each row is (label, status, expected) or (label, status, expected, detail).

    `expected` is a status, a tuple of statuses, or a range.
    """
    body, passed = [], 0
    for label, code, expected, *rest in rows:
        allowed = expected if isinstance(expected, (tuple, list, range, set)) else (expected,)
        ok = code in allowed
        passed += ok
        if isinstance(expected, range):
            want = f"{expected.start}–{expected.stop - 1}"
        else:
            want = " or ".join(str(s) for s in allowed)
        body.append([label, status(code, "ok" if ok else "bad"), Html(f'<span class="aigw-mut">{want}</span>', want),
                     chip("Pass", "ok") if ok else chip("Fail", "bad"),
                     mono(" ".join(str(rest[0]).split())[:140]) if rest and rest[0] else ""])
    has_detail = any(r[-1] for r in body)
    columns = ["Request", "Status", "Expected", "Result"] + (["Detail"] if has_detail else [])
    rows_out = [r if has_detail else r[:-1] for r in body]
    total = len(rows_out)
    badge = chip(f"{passed} of {total} passed", "ok" if passed == total else "bad")
    return card(title, grid(columns, rows_out), sub=sub, badge=badge)


def reply(text: str, title: str, model: str | None = None, tokens=None, sub=None, badge: Html | None = None,
          markdown: bool = False) -> View:
    """A model's answer, with the alias and the tokens it used. `tokens` is a total, or (input, output).

    Set `markdown` for agents that answer in Markdown, such as GitHub Copilot.
    """
    if isinstance(tokens, (tuple, list)):
        used = f"{tokens[0]:,} in · {tokens[1]:,} out tokens"
    elif tokens is not None:
        used = f"{tokens:,} tokens"
    else:
        used = None
    meta = [m for m in (chip(model, "violet", code=True) if model else None, chip(used) if used else None) if m]
    body = _markdown(text) if markdown and text else quote(text or "(empty)")
    return card(title, body, chips(*meta) if meta else None, sub=sub, badge=badge)


def http(code: int, headers, body: str, title: str, sub=None, keys=None) -> View:
    """The anatomy of an HTTP response: status, headers, and body. `keys` limits the headers shown.

    Retry-After, and the -retry-after headers of cost limits, show as amber badges.
    """
    items = [(k.lower(), v) for k, v in headers.items()]
    if keys:
        wanted = [k.lower() for k in keys]
        items = [(k, v) for k, v in items if k in wanted]

    def retry(name):
        return name == "retry-after" or name.endswith("-retry-after")

    rows = [(k, chip(v, "warn", code=True) if retry(k) else mono(v)) for k, v in items]
    try:
        shown = _json.dumps(_json.loads(body), indent=2)
    except (TypeError, ValueError):
        shown = body or ""
    retry_after = next((v for k, v in items if retry(k)), None)
    badge = Html(status(code) + (f" {chip(f'Retry-After {retry_after} s', 'warn')}" if retry_after else ""),
                 f"[{code}]" + (f" [Retry-After {retry_after} s]" if retry_after else ""))
    return card(title, section("Headers", kv(rows)), section("Body", pre(shown[:2000])), sub=sub, badge=badge)


def policies(alias: str, items) -> View:
    """The policies on an alias or model, with token limits and cost limits spelled out."""
    def caller(override):
        if override.get("apiKeyResourceId"):
            return mono(f"API key {override['apiKeyResourceId'].rsplit('/', 1)[-1]}")
        claims = override.get("claims") or {}
        return mono("Entra ID " + ", ".join(f"{k} {v}" for k, v in claims.items()))

    blocks = []
    for policy in items:
        keys = chips(*(chip(k, "violet", code=True) for k in policy.get("counterKey") or []))
        if policy.get("type") == "tokenLimit":
            blocks.append(kv([("Policy", mono("tokenLimit")),
                              ("Allowance", f"{policy.get('count', 0):,} tokens per {policy.get('period', '?')}"),
                              ("Counter key", keys)]))
        elif policy.get("type") == "costLimit":
            overrides = policy.get("overrides") or []
            rows = [("Policy", mono("costLimit")),
                    ("Budget", f"{usd(policy.get('amount'))} per {policy.get('period', '?')} for each caller"),
                    ("Counter key", keys)]
            if overrides:
                rows.append(("Overrides", grid(["Caller", "Budget"], [[caller(o), usd(o.get("amount"))]
                                                                     for o in overrides])))
            blocks.append(kv(rows))
        else:
            blocks.append(kv([("Policy", mono(policy.get("type"))), ("Settings", mono(_json.dumps(policy)))]))
    raw = details("Policy JSON", pre(_json.dumps(items, indent=2)))
    count = len(items)
    return card(f"Policies on {alias}", *(blocks or [note("No policies", "neutral")]), raw,
                badge=chip(f"{count} {'policy' if count == 1 else 'policies'}", "violet"))


def hits(title: str, results, sub=None) -> View:
    """Search results: each item is a dict with title, url, and text."""
    markup, lines = [], []
    for hit in results:
        excerpt = " ".join(str(hit.get("text") or "").split())
        excerpt = excerpt[:240] + ("…" if len(excerpt) > 240 else "")
        url = hit.get("url") or ""
        heading = link(url, hit.get("title") or url) if url else _e(hit.get("title"))
        markup.append(f'<div class="aigw-hit">{heading}<span class="aigw-m">{_e(url)}</span>'
                      f"{f'<p>{_e(excerpt)}</p>' if excerpt else ''}</div>")
        lines.append(f"{hit.get('title')}\n  {url}\n  {excerpt}".rstrip())
    return card(title, Html("".join(markup), "\n".join(lines)), sub=sub, badge=chip(f"{len(results)} results"))


# Live output ---------------------------------------------------------------------------------------------------------

def _kernel() -> bool:
    try:
        from IPython import get_ipython
    except ImportError:
        return False
    shell = get_ipython()
    return shell is not None and getattr(shell, "kernel", None) is not None


def show(view: View):
    """Display a view in a notebook, or print it elsewhere."""
    if _kernel():
        from IPython.display import display
        display(view)
    else:
        print(view.text, flush=True)


class live:
    """One output that updates in place: `status = brand.live()`, then `status.update(view)` as often as needed."""

    def __init__(self, view: View | None = None):
        self._handle = None
        self.shown = False
        if view is not None:
            self.update(view)

    def update(self, view: View):
        self.shown = True
        if not _kernel():
            print(view.text, flush=True)
        elif self._handle is None:
            from IPython.display import display
            self._handle = display(view, display_id=True)
        else:
            self._handle.update(view)

    def finish(self, view: View):
        """Show the final state, but only if something was shown: a wait that never happened stays silent."""
        if self.shown:
            self.update(view)


def wait(seconds: int, reason: str):
    """Sleep with a countdown, for example `brand.wait(60, "for a fresh token counter")`."""
    status = live(note(f"Waiting {seconds} s {reason}", "wait"))
    for left in range(seconds, 0, -1):
        if _kernel():
            status.update(note(f"Waiting {left} s {reason}", "wait"))
        _time.sleep(1)
    status.update(note(f"Waited {seconds} s {reason}", "neutral"))


class Board:
    """A table that grows one row at a time, with an optional budget bar: a burst of requests, for example.

    `stop` is the status the gateway answers when the limit is reached: 429 for a token limit, 403 for a cost limit.
    `unit` USD shows the budget bar in dollars.
    """

    def __init__(self, title: str, columns, sub=None, budget: float | None = None,
                 budget_label: str = "Tokens used", unit: str = "tokens", stop: int = 429):
        self.title, self.columns, self.sub = title, list(columns), sub
        self.budget, self.budget_label, self.unit, self.stop = budget, budget_label, unit, stop
        self.rows, self.statuses, self.used = [], [], 0
        self._live = live()
        if _kernel():
            self._live.update(self.view())
        else:
            print(f"{title}" + (f" · {sub}" if sub else ""), flush=True)

    def add(self, cells, status: int | None = None, amount: float | None = None):
        """Add a row. `amount` is what the request used: tokens, or dollars when `unit` is USD."""
        self.rows.append(list(cells))
        if status is not None:
            self.statuses.append(status)
        self.used += amount or 0
        if _kernel():
            self._live.update(self.view(fresh=len(self.rows) - 1))
        else:
            print("  ".join(_plain(c) for c in cells), flush=True)
        return self

    def view(self, fresh: int = -1) -> View:
        stopped = sum(1 for s in self.statuses if s == self.stop)
        failed = sum(1 for s in self.statuses if s >= 400 and s != self.stop)
        if failed:
            badge = chip(f"{failed} failed", "bad")
        elif stopped:
            verb = "throttled" if self.stop == 429 else "blocked"
            badge = chip(f"{stopped} of {len(self.statuses)} {verb}", status_tone(self.stop))
        else:
            badge = chip(f"{len(self.rows)} {'request' if len(self.rows) == 1 else 'requests'}", "brand")
        bar = gauge(self.used, self.budget, self.budget_label, self.unit) if self.budget else None
        rows = grid(self.columns, self.rows, fresh) if self.rows else note("Sending the first request", "wait")
        return card(self.title, bar, rows, sub=self.sub, badge=badge)


class Stream:
    """Text that arrives token by token, with a caret while it streams and stats when it's done."""

    def __init__(self, title: str, sub=None, interval: float = .05):
        self.title, self.sub, self.text, self.interval = title, sub, "", interval
        self._last = 0.0
        self._live = live()
        if _kernel():
            self._live.update(self.view())
        else:
            print(f"{title}" + (f" · {sub}" if sub else ""), flush=True)

    def write(self, delta: str):
        self.text += delta
        if not _kernel():
            print(delta, end="", flush=True)
            return
        now = _time.perf_counter()
        if now - self._last >= self.interval:
            self._last = now
            self._live.update(self.view())

    def done(self, rows=(), badge: Html | None = None):
        rows = list(rows)
        if _kernel():
            self._live.update(self.view(rows, badge, finished=True))
        else:
            print("\n" + kv(rows).text if rows else "", flush=True)

    def view(self, rows=(), badge: Html | None = None, finished: bool = False) -> View:
        if self.text:
            caret = "" if finished else '<span class="aigw-caret"></span>'
            body = Html(f'<div class="aigw-quote">{_html.escape(self.text)}{caret}</div>', self.text)
        else:
            body = Html('<div class="aigw-quote aigw-empty">Waiting for the first token…'
                        '<span class="aigw-caret"></span></div>', "")
        badge = badge or (chip("Done", "ok") if finished else chip("Streaming", "brand"))
        return card(self.title, body, kv(rows) if rows else None, sub=self.sub, badge=badge)


class Progress:
    """A deployment that updates in place: its state, elapsed time, and resources, then its outputs or errors."""

    _STATES = {"Succeeded": "ok", "Failed": "bad", "Canceled": "bad"}

    def __init__(self, title: str, sub=None):
        self.title, self.sub = title, sub
        self._live = live()
        if _kernel():
            self._live.update(self._view(chip("Starting", "brand"), [note("Submitting the deployment", "wait")]))
        else:
            print(f"🚀 {title}" + (f" to {sub}" if sub else ""), flush=True)

    def _resources(self, operations) -> Html | None:
        if not operations:
            return None
        rows = [[mono(kind), mono(name), chip(state, self._STATES.get(state, "brand"))] for kind, name, state in operations]
        return grid(["Resource type", "Name", "State"], rows)

    def _view(self, badge: Html, blocks) -> View:
        return card(self.title, *blocks, sub=self.sub, badge=badge)

    def update(self, state: str, elapsed: int, operations=()):
        if _kernel():
            resources = self._resources(operations) or note("Waiting for Azure Resource Manager to start", "wait")
            self._live.update(self._view(chip(f"{state} · {elapsed} s", "brand"), [resources]))
        else:
            pending = [f"{k} {n}" for k, n, s in operations if s != "Succeeded"][:3]
            print(f"⏳ {elapsed:>4} s  {', '.join(pending) or state}", flush=True)

    def done(self, elapsed: int, operations=(), outputs: dict | None = None):
        if _kernel():
            def value(v):
                return ", ".join(map(str, v)) if isinstance(v, list) else _json.dumps(v) if isinstance(v, dict) else v

            out = section("Outputs", kv((k, mono(value(v))) for k, v in outputs.items())) if outputs else None
            self._live.update(self._view(chip(f"Succeeded in {elapsed} s", "ok"), [self._resources(operations), out]))
        else:
            print(f"✅ Deployed in {elapsed} s", flush=True)

    def fail(self, state: str, elapsed: int, operations=(), errors=()):
        if _kernel():
            self._live.update(self._view(chip(f"{state} after {elapsed} s", "bad"),
                                         [self._resources(operations), section("Errors", pre("\n".join(errors)))]))
        else:
            print(f"❌ {state} after {elapsed} s", flush=True)


# Charts --------------------------------------------------------------------------------------------------------------

_SANS = ("Segoe UI", "Aptos", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans")
_MONOS = ("Cascadia Code", "Cascadia Mono", "SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono")


def _installed(names) -> list:
    from matplotlib import font_manager
    have = {font.name for font in font_manager.fontManager.ttflist}
    return [name for name in names if name in have]


def _mpl_style(palette: dict) -> dict:
    """matplotlib settings in the style of the labs site, for one palette."""
    from matplotlib import cycler
    return {
        "font.family": "sans-serif", "font.sans-serif": _installed(_SANS), "font.monospace": _installed(_MONOS),
        "font.size": 9.5, "text.color": palette["fg"],
        "axes.prop_cycle": cycler(color=[palette[k] for k in ("brand", "violet", "ok", "warn", "bad", "fg3")]),
        "axes.facecolor": "none", "axes.edgecolor": palette["stroke"], "axes.linewidth": .8,
        "axes.labelcolor": palette["fg3"], "axes.labelsize": 9, "axes.labelpad": 6,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "axes.axisbelow": True,
        "grid.color": palette["stroke2"], "grid.linewidth": .8,
        "xtick.color": palette["stroke"], "xtick.labelcolor": palette["fg3"], "xtick.labelsize": 8.5,
        "ytick.color": palette["stroke"], "ytick.labelcolor": palette["fg3"], "ytick.labelsize": 8.5,
        "xtick.major.size": 3, "ytick.major.size": 0, "ytick.major.pad": 6,
        "legend.frameon": False, "legend.fontsize": 9, "legend.labelcolor": palette["fg2"],
        "figure.facecolor": "none",
    }


def use_matplotlib_style(dark: bool = False):
    """Style your own matplotlib charts like the labs site. Pass dark=True when the notebook uses a dark theme."""
    import matplotlib as mpl
    palette = DARK if dark else LIGHT
    mpl.rcParams.update(_mpl_style(palette) | {"figure.facecolor": palette["bg"], "savefig.facecolor": palette["bg"]})


def _usage_svg(rows, totals, limit, limit_label, unit, palette) -> bytes:
    import matplotlib as mpl
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    def tick(value, _):
        return "$" + f"{value:,.6f}".rstrip("0").rstrip(".") if unit == "USD" else f"{value:,.0f}"

    xs = list(range(1, len(rows) + 1))
    amounts = [a or 0 for _, a in rows]
    tones = [palette[status_tone(s)] for s, _ in rows]
    with mpl.rc_context(_mpl_style(palette) | {"svg.fonttype": "none", "svg.hashsalt": "aigw"}):
        fig = Figure(figsize=(9.6, 3.5))
        ax = fig.add_subplot()
        twin = ax.twinx()

        # One bar per request, on the left axis. Refused requests show their status code at the baseline.
        ax.bar(xs, amounts, width=.62, color=tones, alpha=.6, linewidth=0, zorder=2)
        for x, (code, _) in zip(xs, rows):
            if not 200 <= code < 300:
                ax.text(x, .02, str(code), transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                        color=palette[status_tone(code)], family="monospace", weight="bold", fontsize=8)
        ax.set_ylim(0, max(amounts or [0]) * 2.4 or 1)
        ax.set_xlim(.4, len(rows) + .6)
        if len(rows) <= 30:
            ax.set_xticks(xs)
        else:
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.yaxis.set_major_locator(MaxNLocator(4))
        ax.yaxis.set_major_formatter(FuncFormatter(tick))
        ax.set_xlabel("Request")
        ax.set_ylabel("Cost per request (US$)" if unit == "USD" else f"{unit.capitalize()} per request")

        # The running total and the limit, on the right axis.
        twin.grid(False)
        for side in ("top", "left", "bottom"):
            twin.spines[side].set_visible(False)
        twin.fill_between(xs, totals, color=palette["brand"], alpha=.08, linewidth=0, zorder=1)
        twin.plot(xs, totals, color=palette["brand"], linewidth=2, solid_capstyle="round", zorder=3)
        twin.scatter(xs, totals, s=24, zorder=4, linewidths=0,
                     color=[palette["brand"] if 200 <= s < 300 else palette[status_tone(s)] for s, _ in rows])
        top = max([limit or 0] + totals) * 1.24 or 1
        twin.set_ylim(0, top)
        twin.yaxis.set_major_locator(MaxNLocator(4))
        twin.yaxis.set_major_formatter(FuncFormatter(tick))
        twin.tick_params(axis="y", labelcolor=palette["brand"])
        twin.set_ylabel("Spent in this run" if unit == "USD" else "Running total", color=palette["brand"])
        if totals:
            twin.annotate(usd(totals[-1]) if unit == "USD" else f"{totals[-1]:,.0f}", (xs[-1], totals[-1]),
                          xytext=(0, 8), textcoords="offset points", ha="center", va="bottom",
                          color=palette["brand"], weight="bold", fontsize=8.5)
        if limit:
            twin.axhline(limit, color=palette["violet"], linewidth=1.3, dashes=(5, 3), zorder=2)
            twin.text(.01, limit + top * .02, limit_label or f"Limit: {tick(limit, None)}",
                      transform=twin.get_yaxis_transform(), ha="left", va="bottom",
                      color=palette["violet"], weight="bold", fontsize=8.5)

        handles = [Patch(color=palette["ok"], alpha=.6, label="Answered (200)")]
        for code in sorted({s for s, _ in rows if not 200 <= s < 300}):
            verb = "Throttled" if code == 429 else "Blocked" if code == 403 else "Failed"
            handles.append(Patch(color=palette[status_tone(code)], alpha=.6, label=f"{verb} ({code})"))
        handles.append(Line2D([], [], color=palette["brand"], linewidth=2, marker="o", markersize=4.5,
                              label="Running total"))
        ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=len(handles), borderaxespad=0,
                  handlelength=1.3, handleheight=.8, handletextpad=.5, columnspacing=1.8)

        buffer = _io.BytesIO()
        fig.savefig(buffer, format="svg", bbox_inches="tight", pad_inches=.05, transparent=True,
                    metadata={"Date": None})
        return buffer.getvalue()


def usage_chart(title: str, rows, limit: float | None = None, limit_label: str | None = None,
                unit: str = "tokens", sub=None) -> View:
    """A burst as a chart: a bar per request, the running total, and the limit that stopped it.

    `rows` holds (status, amount) for each request, where amount is what the request used: tokens, or dollars when
    `unit` is USD. Use None for a request the gateway refused. Needs matplotlib; the chart follows the notebook theme.
    """
    rows = [(int(code), amount) for code, amount in rows]
    totals = list(_itertools.accumulate((amount or 0 for _, amount in rows), initial=0))[1:]
    answered = sum(1 for code, _ in rows if 200 <= code < 300)
    stop = next((code for code, _ in rows if code in (403, 429)), None)
    refused = sum(1 for code, _ in rows if code == stop)
    failed = len(rows) - answered - refused
    verb = "throttled" if stop == 429 else "blocked"
    total = totals[-1] if totals else 0

    summary = [chip(f"{answered} answered", "ok")]
    if refused:
        summary.append(chip(f"{refused} {verb}", status_tone(stop)))
    if failed:
        summary.append(chip(f"{failed} failed", "bad"))
    summary.append(chip(f"Total {_amount(total, unit)}", "brand"))
    if limit:
        summary.append(chip(limit_label or f"Limit {_amount(limit, unit)}", "violet"))
    badge = (chip(f"{refused} of {len(rows)} {verb}", status_tone(stop)) if refused
             else chip(f"{len(rows)} {'request' if len(rows) == 1 else 'requests'}", "brand"))

    label = "Cost" if unit == "USD" else unit.capitalize()
    def shown(value):
        return usd(value) if unit == "USD" else value

    table_rows = [[n, status(code), "-" if amount is None else shown(amount), shown(run)]
                  for n, ((code, amount), run) in enumerate(zip(rows, totals), 1)]
    data = grid(["Request", "Status", label, "Running total"], table_rows)
    alt = (f"Chart of {len(rows)} requests: {answered} answered" + (f", {refused} {verb}" if refused else "")
           + f". The running total reached {_amount(total, unit)}"
           + (f" against a limit of {_amount(limit, unit)}." if limit else "."))
    if not _kernel():
        return card(title, data, chips(*summary), sub=sub, badge=badge)
    try:
        images = []
        for palette, theme in ((LIGHT, "lt"), (DARK, "dk")):
            svg = _base64.b64encode(_usage_svg(rows, totals, limit, limit_label, unit, palette)).decode()
            images.append(f'<img class="aigw-fig aigw-fig-{theme}" alt="{_html.escape(alt)}" '
                          f'src="data:image/svg+xml;base64,{svg}">')
    except ImportError:
        missing = note("Install matplotlib to see this as a chart: run %pip install matplotlib, then this cell again",
                       "warn")
        return card(title, missing, data, chips(*summary), sub=sub, badge=badge)
    figure = Html(f'<div class="aigw-figw">{"".join(images)}</div>', alt)
    return card(title, figure, chips(*summary), details("Show the data", data), sub=sub, badge=badge)
