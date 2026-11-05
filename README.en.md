# taskboard — write task cards in the browser, a morning cron job does them

> A single-user task-card board. Log in to create, edit, retitle or delete cards; each card is a plain markdown file on disk that a 04:00 automation job reads the next morning. Two open cards per day at most — extras roll over to the next free day.

English | [中文](README.md)

## What it is

The cards used to live only as markdown in a directory. This adds a browser front end that writes exactly the same markdown, so nothing downstream changed.

- Public read-only view of every card and of what is due today; all writes go through a session login and return 401 without it.
- At most two open cards per day — extra ones roll forward and the page says which day they landed on.
- Four states: planned, doing, done and carry-over. Carry-over is deliberately not treated as closed, so it shows up as one day overdue tomorrow morning.
- Closing a card moves it to an archive folder rather than deleting it.

The service runs on a local machine behind a reverse proxy; the markdown files stay the single source of truth.

## Features

- Create cards in the browser; the output is still plain markdown
- Read-only without login, 401 on every write
- Two open cards a day; extras roll forward and the page says where they went
- Four states: planned, doing, done, carry-over
- Closing archives instead of deleting
- Read-only JSON endpoints as a fallback for the cron job

## Stack

Flask · 原生 JS · 本地 markdown 文件（无数据库）

## Run

```bash
python server.py --port 8802
# 首次启动会在 data/ 生成账号密码，网页上登录即可建卡
```

## About

Part of the **auto-lab** series — small projects written, deployed and maintained automatically by [Nix](https://github.com/Uxnar-ai) on a self-hosted server.

Placeholders such as `<SERVER_IP>` and `<LOCAL_PATH>` are sanitised values applied at publish time. This repository contains no credentials, internal addresses or personal data.

## License

MIT
