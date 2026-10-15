# Portable regression suite

Start this clone with a fresh data directory. Tests require Python httpx, Playwright and its Chromium runtime (development tools; not required to run the website). Reuse the documented loopback SMTP server.

From the clone directory:

```sh
TICKTICK_TEST_BASE=http://127.0.0.1:18122 python tests/run_suite.py
```

The suite creates only synthetic local accounts and reads their messages. It never clears SMTP or application data. It writes reports to artifacts/ and temporary evidence to run/.
