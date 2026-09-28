"""Turn verified fixes into a change report: which files each fix touched,
at which lines, and exactly which lines were removed and added. The same
structure is sent to the dashboard (`changes_ready`) and printed by the CLI
before asking whether to publish."""
from __future__ import annotations

import re

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_diff(diff: str) -> list[dict]:
    """A unified diff (as `git diff` prints it) as a list of files:

        {"path", "status": "modified"|"added"|"deleted", "added", "removed",
         "hunks": [{"header", "lines": [{"kind": "add"|"del"|"ctx", "old", "new", "text"}]}]}

    `old`/`new` are line numbers in the file before/after the change (None
    on the side where the line doesn't exist)."""
    files: list[dict] = []
    current: dict | None = None
    hunk: dict | None = None
    old_no = new_no = 0
    for raw in diff.splitlines():
        if raw.startswith("diff --git "):
            current = {"path": raw.split(" b/", 1)[-1], "status": "modified", "added": 0, "removed": 0, "hunks": []}
            files.append(current)
            hunk = None
        elif current is None:
            continue
        elif hunk is None and raw.startswith("new file mode"):
            current["status"] = "added"
        elif hunk is None and raw.startswith("deleted file mode"):
            current["status"] = "deleted"
        elif hunk is None and raw.startswith("+++ ") and raw[4:] != "/dev/null":
            current["path"] = raw[4:].removeprefix("b/")
        elif (match := _HUNK.match(raw)) is not None:
            old_no, new_no = int(match.group(1)), int(match.group(2))
            hunk = {"header": raw, "lines": []}
            current["hunks"].append(hunk)
        elif hunk is None:
            continue
        elif raw.startswith("+"):
            hunk["lines"].append({"kind": "add", "old": None, "new": new_no, "text": raw[1:]})
            current["added"] += 1
            new_no += 1
        elif raw.startswith("-"):
            hunk["lines"].append({"kind": "del", "old": old_no, "new": None, "text": raw[1:]})
            current["removed"] += 1
            old_no += 1
        elif raw.startswith(" ") or raw == "":
            hunk["lines"].append({"kind": "ctx", "old": old_no, "new": new_no, "text": raw[1:]})
            old_no += 1
            new_no += 1
    return files


def changed_line_ranges(file: dict) -> str:
    """Where a file changed, as line numbers in the new version: `12, 30-34`.
    Pure deletions are reported at the line they were removed before."""
    points: list[int] = []
    for hunk in file["hunks"]:
        lines = hunk["lines"]
        for i, line in enumerate(lines):
            if line["kind"] == "add":
                points.append(line["new"])
            elif line["kind"] == "del":
                following = next((l["new"] for l in lines[i + 1:] if l["new"] is not None), None)
                points.append(following or line["old"])
    points = sorted(set(points))
    ranges: list[str] = []
    for n in points:
        if ranges and n == int(ranges[-1].split("-")[-1]) + 1:
            ranges[-1] = f"{ranges[-1].split('-')[0]}-{n}"
        else:
            ranges.append(str(n))
    return ", ".join(ranges)


def summarize(fixes: list[dict]) -> dict:
    """`fixes` is [{"key", "title", "location", "diff"}] in commit order."""
    out = []
    for fix in fixes:
        files = parse_diff(fix["diff"])
        for file in files:
            file["lines_changed"] = changed_line_ranges(file)
        out.append({"key": fix["key"], "title": fix["title"], "location": fix["location"], "files": files})
    paths = {f["path"] for fix in out for f in fix["files"]}
    return {
        "fixes": out,
        "totals": {
            "fixes": len(out),
            "files": len(paths),
            "added": sum(f["added"] for fix in out for f in fix["files"]),
            "removed": sum(f["removed"] for fix in out for f in fix["files"]),
        },
    }


_ANSI = {"add": "\033[32m", "del": "\033[31m", "dim": "\033[2m", "bold": "\033[1m", "reset": "\033[0m"}


def render_text(changes: dict, *, color: bool = False) -> str:
    """The change report for a terminal."""
    def c(style: str, text: str) -> str:
        return f"{_ANSI[style]}{text}{_ANSI['reset']}" if color else text

    totals = changes["totals"]
    lines = [
        c("bold", f"Changes: {totals['fixes']} fix(es), {totals['files']} file(s), +{totals['added']} -{totals['removed']}"),
    ]
    for number, fix in enumerate(changes["fixes"], 1):
        lines += ["", c("bold", f"[{number}] {fix['title']}") + (c("dim", f"  ({fix['location']})") if fix["location"] else "")]
        for file in fix["files"]:
            status = "" if file["status"] == "modified" else f" ({file['status']})"
            lines.append(
                f"    {c('bold', file['path'])}{status}  "
                f"{c('add', '+' + str(file['added']))} {c('del', '-' + str(file['removed']))}  "
                f"{c('dim', 'lines ' + file['lines_changed']) if file['lines_changed'] else ''}".rstrip()
            )
            for hunk in file["hunks"]:
                lines.append("      " + c("dim", hunk["header"]))
                for line in hunk["lines"]:
                    if line["kind"] == "add":
                        lines.append(c("add", f"      {'':>5} {line['new']:>5} + {line['text']}"))
                    elif line["kind"] == "del":
                        lines.append(c("del", f"      {line['old']:>5} {'':>5} - {line['text']}"))
                    else:
                        lines.append(c("dim", f"      {line['old']:>5} {line['new']:>5}   {line['text']}"))
    return "\n".join(lines)
