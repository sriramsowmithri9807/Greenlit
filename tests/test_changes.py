from greenlit.changes import changed_line_ranges, parse_diff, render_text, summarize

DIFF = """diff --git a/pkg/mod.py b/pkg/mod.py
index 1111111..2222222 100644
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -1,4 +1,5 @@
 import os
-x = 1
+x = 2
+y = 3
 
 def f():
@@ -20,3 +21,2 @@ def g():
     a = 1
-    b = 2
     return a
diff --git a/pkg/new.py b/pkg/new.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/pkg/new.py
@@ -0,0 +1 @@
+VALUE = 1
"""


def test_parse_diff_tracks_line_numbers_on_both_sides():
    mod, new = parse_diff(DIFF)
    assert (mod["path"], mod["status"], mod["added"], mod["removed"]) == ("pkg/mod.py", "modified", 2, 2)
    first = mod["hunks"][0]["lines"]
    assert [(l["kind"], l["old"], l["new"]) for l in first] == [
        ("ctx", 1, 1), ("del", 2, None), ("add", None, 2), ("add", None, 3), ("ctx", 3, 4), ("ctx", 4, 5),
    ]
    assert (new["path"], new["status"], new["added"]) == ("pkg/new.py", "added", 1)


def test_changed_line_ranges_merges_runs_and_places_deletions():
    mod, new = parse_diff(DIFF)
    assert changed_line_ranges(mod) == "2-3, 22"
    assert changed_line_ranges(new) == "1"


def test_render_text_shows_files_lines_and_code():
    changes = summarize([{"key": "k", "title": "x is wrong", "location": "pkg/mod.py:2", "diff": DIFF}])
    assert changes["totals"] == {"fixes": 1, "files": 2, "added": 3, "removed": 2}
    text = render_text(changes)
    assert "[1] x is wrong" in text and "pkg/mod.py  +2 -2  lines 2-3, 22" in text
    assert "pkg/new.py (added)" in text
    assert "    2       - x = 1" in text and "          2 + x = 2" in text
    assert "\033[" not in text and "\033[32m" in render_text(changes, color=True)
