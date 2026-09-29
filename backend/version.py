"""Single source of truth for the build marker shown in the app header and
bundled into "Copy diagnostic info". There's no package registry or
auto-update mechanism here to infer a build from otherwise, so without
this, a field tester's bug report carries no way to know which build it
came from.

A date, not a semantic version: what a bug report needs is "which build,"
not an API-compatibility number, and a date is both trivial to keep
accurate (no scheme to get wrong) and immediately useful on its own
("reported against the Sep 11 build" is more informative at a glance than
"reported against 1.4.2").

Bump this to today's date whenever a change goes into a build meant to
leave this dev machine (i.e. as part of the build/deploy cycle, not on
every commit) — see build/build_windows.bat.
"""

APP_VERSION = "2026-09-11"
