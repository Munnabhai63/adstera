# AGENT REPORT

**Filled by:** (agent name)
**Date:**
**Branch worked on:**
**Commit range:**

> Fill this after working through `docs/AGENT_TASKS.md`.
> Paste real command output. If a task was impossible or its premise was wrong, mark it `SPEC-WRONG`
> and explain — do not silently skip it, and do not edit an assertion to make it pass.

---

## TASK 1.1 — Check 7 can never pass

STATUS:
FILES:
CHANGE:
PROVE:
```
$ python scripts/verify_all.py
<output>
```
```
$ # after appending a probe leak
<output showing Check 7 FAIL>
```
REGRESSION:
NOTES:

---

## TASK 1.2 — Check 9 tests the fix with the fix

STATUS:
FILES:
CHANGE:
PROVE:
```
<output>
```
REGRESSION:
NOTES:

---

## TASK 1.3 — Check 2 string-match + skipped transport

STATUS:
FILES:
CHANGE:
PROVE:
```
<output>
REGRESSION:
NOTES:

---

## TASK 2.1 — availWidth === width

STATUS:
FILES:
CHANGE:
PROVE:
```
$ python3 - <<'PY'  ... 200 profiles
<output>
```
NOTES:

---

## TASK 2.2 — avail_height from viewport

STATUS:
FILES:
CHANGE:
PROVE:
```
<output>
```
NOTES:

---

## TASK 2.3 — dpr guessed from width

STATUS:
FILES:
CHANGE:
PROVE:
```
<output>
```
NOTES:

---

## TASK 2.4 — delete screen.width is a no-op

STATUS:
FILES:
CHANGE:
PROVE:
```
<output of the two getOwnPropertyDescriptor assertions>
```
NOTES:

---

## TASK 3.1 — Cloudflare Tunnel token

STATUS:
FILES:
CHANGE:
PROVE:
```
$ git grep -n 'eyJhIjoi' -- '*.py' '*.js' '*.yaml' ':!docs/*'
<output — must be empty>
```
NOTES:

---

## TASK 3.2 — Telegram chat_id

STATUS:
FILES:
CHANGE:
PROVE:
```
<output>
```
NOTES:

---

## TASK 4.1 — git push origin master

STATUS:
FILES:
CHANGE:
PROVE:
```
<output>
```
NOTES:

---

## TASK 4.2 — proxies.txt empty + --allow-no-transport

STATUS:
FILES:
CHANGE:
PROVE:
```
$ python main.py
<output — must exit non-zero within 5s>
```
NOTES:

---

## TASK 4.3 — code default 5/50 vs config 1/10

STATUS:
FILES:
CHANGE:
PROVE:
```
<output>
```
NOTES:

---

## TASK 4.4 — static/sw.js still on 5gvci.com

STATUS:
FILES:
CHANGE:
PROVE:
```
$ git grep -rn '5gvci' -- sites/
<output — must be empty>
```
NOTES:

---

## TASK 5.1 — CSP vs hosts the pages actually use

STATUS:
FILES:
CHANGE:
PROVE:
```
<output>
```
NOTES:

---

## TASK 6.1 — HANDOFF_REPORT.md corrections

STATUS:
FILES:
CHANGE:
PROVE:
NOTES:

---

## OWNER MUST DO

1.
2.
3.

---

## WHAT REMAINS UNSOLVED

(Be honest. Do not claim the network is undetectable.)
