#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""taskboard · <HOST> 任务卡发布站

在 <HOST>（本机 Windows）上跑 Flask，读写 <LOCAL_PATH>/auto-lab/tasks/ 里的卡片 markdown。
5105 只做 nginx 反代 → http://<SERVER_IP>:8802 ，不在服务器留任何数据。

    python server.py                 # 默认 0.0.0.0:8802
    python server.py --port 8802

首次启动会生成账号密码，写到 data/INITIAL_CREDENTIALS.txt（推送后请删掉该文件）。
忘了密码：删 data/auth.json 后重启，会重新生成。
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import cards

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
AUTH_PATH = DATA_DIR / "auth.json"
CRED_PATH = DATA_DIR / "INITIAL_CREDENTIALS.txt"
SECRET_PATH = DATA_DIR / "secret.key"

SESSION_HOURS = 12
MAX_FAIL = 5
LOCK_MINUTES = 10

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# ------------------------------------------------------------------ 认证


def _load_secret() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    SECRET_PATH.write_text(key, encoding="utf-8")
    return key


app.secret_key = _load_secret()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=SESSION_HOURS * 3600,
    MAX_CONTENT_LENGTH=512 * 1024,
)


def _init_auth() -> None:
    """首次启动生成账号密码；已有则什么都不做。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if AUTH_PATH.exists():
        return
    user = "<USER>"
    pw = secrets.token_urlsafe(12)
    AUTH_PATH.write_text(json.dumps({
        "user": user,
        "pw_hash": generate_password_hash(pw, method="pbkdf2:sha256:600000"),
        "created": datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    CRED_PATH.write_text(
        f"地址  https://task.824109091.xyz/\n账号  {user}\n密码  {pw}\n"
        f"生成  {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"—— 推送完成后可删除本文件；忘了就删 data/auth.json 重启重新生成\n",
        encoding="utf-8")


def _auth() -> dict:
    try:
        return json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


_fails: dict[str, list[float]] = {}


def _locked(ip: str) -> int:
    """返回还需锁多少秒，0 表示没锁"""
    now = time.time()
    hits = [t for t in _fails.get(ip, []) if now - t < LOCK_MINUTES * 60]
    _fails[ip] = hits
    if len(hits) >= MAX_FAIL:
        return int(LOCK_MINUTES * 60 - (now - hits[-1]))
    return 0


def logged_in() -> bool:
    return bool(session.get("u")) and session.get("u") == _auth().get("user")


def require_login(fn):
    @wraps(fn)
    def inner(*a, **kw):
        if not logged_in():
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "login required"}), 401
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return inner


@app.context_processor
def inject():
    return {
        "authed": logged_in(),
        "status_label": cards.STATUS_LABEL,
        "today": date.today().isoformat(),
        "max_per_day": cards.MAX_PER_DAY,
        "cards_dir": str(cards.CARDS_DIR),
    }


# ------------------------------------------------------------------ 页面


def _grouped():
    all_cards = cards.list_cards(include_archive=True)
    live = [c for c in all_cards if not c["archived"]]
    today = date.today().isoformat()
    overdue, here, future = [], [], []
    for c in live:
        if c["date"] == today:
            here.append(c)
        elif c["date"] and c["date"] < today:
            overdue.append(c)
        else:
            future.append(c)
    done = sorted([c for c in all_cards if c["archived"]],
                  key=lambda c: c.get("updated") or c["date"], reverse=True)[:12]
    order = {"doing": 0, "carry": 1, "planned": 2}
    for group in (overdue, here, future):
        group.sort(key=lambda c: (order.get(c["status"], 3), c["date"]))
    return overdue, here, future, done


@app.route("/")
def index():
    overdue, here, future, done = _grouped()
    return render_template("index.html", overdue=overdue, here=here,
                           future=future, done=done, st=cards.stats())


@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        ip = request.headers.get("X-Real-IP") or request.remote_addr or "?"
        left = _locked(ip)
        if left:
            err = f"失败次数过多，请 {left // 60 + 1} 分钟后再试"
        else:
            a = _auth()
            u = (request.form.get("u") or "").strip()
            p = request.form.get("p") or ""
            if u == a.get("user") and a.get("pw_hash") and check_password_hash(a["pw_hash"], p):
                session.permanent = True
                session["u"] = u
                _fails.pop(ip, None)
                return redirect(request.args.get("next") or url_for("index"))
            _fails.setdefault(ip, []).append(time.time())
            err = "账号或密码不对"
    return render_template("login.html", err=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/new", methods=["GET", "POST"])
@require_login
def new():
    if request.method == "POST":
        f = request.form
        try:
            card = cards.create(
                title=f.get("title", ""),
                lede=f.get("lede", ""),
                slug=f.get("slug", ""),
                budget=f.get("budget", "full"),
                spec=f.get("spec", ""),
                reqs=_lines(f.get("reqs")),
                criteria=_lines(f.get("criteria")),
                notes=f.get("notes", ""),
                want_date=f.get("date", ""),
                origin="web",
            )
        except ValueError as e:
            return render_template("form.html", mode="new", err=str(e),
                                   form=f, budgets=cards.BUDGETS), 400
        q = f"?shifted={card['date']}" if card.get("shifted") else ""
        return redirect(url_for("index") + q)
    return render_template("form.html", mode="new", err="", form={},
                           budgets=cards.BUDGETS)


@app.route("/edit/<slug>", methods=["GET", "POST"])
@require_login
def edit(slug):
    card = cards.get(slug, include_archive=False)
    if not card:
        abort(404)
    if request.method == "POST":
        f = request.form
        cards.update(slug,
                     title=f.get("title", card["title"]),
                     lede=f.get("lede", ""),
                     budget=f.get("budget", card["budget"]),
                     spec=f.get("spec", card["spec"]),
                     reqs=_lines(f.get("reqs")),
                     criteria=_lines(f.get("criteria")),
                     notes=f.get("notes", ""),
                     date=f.get("date") or card["date"])
        return redirect(url_for("index"))
    form = dict(card)
    form["reqs_text"] = "\n".join(card["reqs"])
    form["criteria_text"] = "\n".join(card["criteria"])
    return render_template("form.html", mode="edit", err="", form=form,
                           budgets=cards.BUDGETS, slug=slug)


@app.route("/status/<slug>", methods=["POST"])
@require_login
def change_status(slug):
    status = request.form.get("status", "")
    note = request.form.get("note", "")
    try:
        cards.set_status(slug, status, note=note)
    except (KeyError, ValueError):
        abort(400)
    return redirect(url_for("index"))


@app.route("/delete/<slug>", methods=["POST"])
@require_login
def delete(slug):
    try:
        cards.remove(slug)
    except KeyError:
        abort(404)
    except PermissionError as e:
        return str(e), 400
    return redirect(url_for("index"))


# ------------------------------------------------------------------ 只读 API


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/today")
def api_today():
    return _cors(jsonify(cards.today_view(request.args.get("date"))))


@app.route("/api/cards")
def api_cards():
    all_cards = cards.list_cards(include_archive=True)
    return _cors(jsonify({"count": len(all_cards),
                          "cards": [cards._public(c) for c in all_cards],
                          "stats": cards.stats()}))


@app.route("/api/card/<slug>")
def api_card(slug):
    c = cards.get(slug, include_archive=True)
    if not c:
        return _cors(jsonify({"ok": False, "error": "not found"})), 404
    return _cors(jsonify(cards._public(c) | {"raw": c["raw"]}))


@app.route("/api/cards", methods=["POST"])
@require_login
def api_create():
    d = request.get_json(silent=True) or request.form.to_dict()
    try:
        card = cards.create(
            title=d.get("title", ""),
            lede=d.get("lede", ""),
            slug=d.get("slug", ""),
            budget=d.get("budget", "full"),
            spec=d.get("spec", ""),
            reqs=_lines(d.get("reqs")) if isinstance(d.get("reqs"), str) else (d.get("reqs") or []),
            criteria=_lines(d.get("criteria")) if isinstance(d.get("criteria"), str) else (d.get("criteria") or []),
            notes=d.get("notes", ""),
            want_date=d.get("date", ""),
            origin=d.get("origin", "api"),
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    body = cards._public(card)
    body.update({"ok": True, "shifted": card.get("shifted"), "wanted_date": card.get("wanted_date")})
    return jsonify(body), 201


@app.route("/api/card/<slug>", methods=["PATCH"])
@require_login
def api_update(slug):
    d = request.get_json(silent=True) or {}
    try:
        card = cards.update(slug, **d)
    except KeyError:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "card": cards._public(card)})


@app.route("/api/card/<slug>/status", methods=["POST"])
@require_login
def api_status(slug):
    d = request.get_json(silent=True) or request.form.to_dict()
    try:
        cards.set_status(slug, d.get("status", ""), note=d.get("note", ""))
    except KeyError:
        return jsonify({"ok": False, "error": "not found"}), 404
    except ValueError:
        return jsonify({"ok": False, "error": "bad status"}), 400
    return jsonify({"ok": True})


@app.route("/api/card/<slug>", methods=["DELETE"])
@require_login
def api_delete(slug):
    try:
        cards.remove(slug)
    except KeyError:
        return jsonify({"ok": False, "error": "not found"}), 404
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    return jsonify({"ok": True})


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "cards_dir": str(cards.CARDS_DIR),
                    "cards": len(cards.list_cards())})


def _lines(text: str | None) -> list[str]:
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


# ------------------------------------------------------------------ 启动


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8802)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    _init_auth()
    print(f"taskboard  卡片目录 {cards.CARDS_DIR}")
    print(f"           {len(cards.list_cards())} 张卡 · 监听 {a.host}:{a.port}")
    if CRED_PATH.exists():
        print(f"           首次凭据在 {CRED_PATH}")
    app.run(host=a.host, port=a.port, debug=a.debug, threaded=True)


if __name__ == "__main__":
    sys.exit(main())
