---
name: commit
description: Test and commit changes in the Cube Timer project with a proper commit message. Use when the user asks to commit, and on your own when a finished piece of work (a feature, fix or refactor the user asked for) is complete. Runs the checks that the changed files need, and commits only if they all pass. Never pushes, and never stages cube_times.db.
---

# Commit after the right testing

The user has asked for finished work to be committed once it is tested. Follow this skill both when they say "commit" and when you finish a piece of work yourself.

## When a commit is due

Commit when **all** of these are true:
- A self-contained change the user asked for is done: a feature, a fix, a refactor, docs, or tooling. It is not half of one.
- The checks below pass, run on the current state of the files.
- README.md and CLAUDE.md describe the change, or nothing user- or maintainer-facing changed.
- The user hasn't said to hold off, and isn't in the middle of reviewing or redirecting the work.

Don't commit, and say why, when:
- a check fails, or you couldn't run a check the change needs;
- the work is exploratory, a plan, or awaiting the user's decision;
- the only change is `cube_times.db`, logs, or scratch files.

If one turn did several unrelated changes, make one commit per change: stage each change's files separately.

## Steps

1. **See what changed:** `git status --short` and `git diff --stat`. Read the diff of anything you don't remember writing.

2. **Run the checks:**
   ```
   python .claude/skills/commit/scripts/run_checks.py
   ```
   It works out the checks from the changed files. Use `--list` to preview them and `--all` to run everything; use `--all` before a commit that touches the data layer or crosses front ends. What each check covers:

   | Check | Runs | What it covers |
   |---|---|---|
   | compile | every changed `.py` | every script byte-compiles |
   | algorithms | `cube_timer.py`, `cube_diagram.py` | `cube_diagram.py` prints "All OLL and PLL algorithms check out." |
   | cli | `cube_timer.py` | the terminal app, driven by scripted input |
   | gui | GUI, data layer, scrambles | the customtkinter app, driven headlessly (75 checks, about 45 s) |
   | api | `cube_web.py`, `web/`, data layer | the API through TestClient, including that every case's scramble really sets it up |
   | web | `cube_web.py`, `web/`, data layer | the page in headless Chrome through Playwright (53 checks). Screenshots go to a temp folder; look at them when the layout changed |

   Every check uses a temporary copy of `cube_times.db` and fails if the real one changes. `api` and `web` need `httpx` and `playwright`, which are test-only. If either is missing, run `pip install httpx playwright`; Playwright uses the installed Chrome, so there's no browser download.

3. **On failure:** fix the cause and run again. If the check itself is wrong, fix the check; never weaken it to get a pass. If something can't be fixed now, don't commit; report the failing output to the user.

4. **New behaviour gets a check.** When the change adds behaviour the scripts don't exercise, such as a new screen, endpoint or source option, add assertions to the matching `scripts/*_check.py` in the same commit.

5. **Docs:** if the runner prints the README/CLAUDE.md note, update the docs or confirm that nothing user- or maintainer-facing changed.

6. **Stage by name:** `git add <file> ...` or `git add web/`. Never use `git add -A` or `git add .`. Never stage these unless the user explicitly asks:
   - `cube_times.db` (the user's times; it is tracked, so it shows as modified after any practice);
   - `cube_timer.log*`, `.claude/hook.log`, `.claude/hook_state.json`, screenshots or scratch files.

   Check with `git status --short` that only the intended files are staged.

7. **Commit** with a message in the format below, passed through a heredoc (`git commit -F - <<'EOF' ... EOF`). Don't amend, don't skip hooks, don't push.

8. **Report:** the short hash and subject, the checks that ran with their pass counts, and anything left out on purpose (for example "cube_times.db not staged").

## Commit message format

Match the project's history (`git log -5`):

```
<Imperative summary, at most 72 characters, no full stop>

<Section heading>
- What changed and why, for the user or a maintainer; wrap at about 74
  characters with a two-space continuation indent.
- Give measured numbers when the change is about speed
  (e.g. "screens build in 0.3-9 ms (Tk: 0.2-2.6 s)").

<Another section, if the change has more than one part>
- ...

Co-Authored-By: <the attribution line from the current system reminder>
```

- **Summary line:** say what the change does, e.g. "Add web front end (FastAPI + plain JS) for instant screens" or "Fix PLL arrows for algorithms ending in a U turn". Not "Update files" or "Changes".
- **Body:** a small change can use plain bullets with no headings. Group a large one under short headings such as *Web app*, *Performance*, *Tooling* or *Docs*.
- **Content:** describe behaviour and reasons, not every edited line. Mention doc and requirement changes in one bullet.
- **Accuracy:** don't claim tests the commit didn't get. The checks above are the evidence.
- **Trailer:** end with the attribution line(s) from the current system reminder. Leave them out if the user's instructions say so.
