import os
import ssl
import socket
import psutil
import secrets
import logging

from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from passgen import generate_passphrase, Wordlist


class Colors:
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    ENDC = "\033[0m"


async def login(request):
    session = await get_session(request)

    if session.get("logged_in"):
        raise web.HTTPFound("/", headers={"Cache-Control": "no-store"})

    state = request.app["state"]

    with open(os.path.join(dir_path, "static", "login.html"), encoding="utf-8") as f:
        login_html = f.read()

    if request.method == "POST":
        data = await request.post()
        password = data.get("password", "")

        try:
            state["ph"].verify(state["password_hash"], password)
        except VerifyMismatchError:
            return web.Response(
                text=login_html.replace(
                    "{message}", '<p class="error">Invalid password</p>'
                ),
                content_type="text/html",
                headers={"Cache-Control": "no-store"},
            )

        session.clear()
        session["logged_in"] = True

        raise web.HTTPFound("/", headers={"Cache-Control": "no-store"})

    return web.Response(
        text=login_html.replace("{message}", ""),
        content_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


async def logout(request):
    session = await get_session(request)

    session.invalidate()

    raise web.HTTPFound("/login", headers={"Cache-Control": "no-store"})


async def index(request):
    session = await get_session(request)

    if not session.get("logged_in"):
        raise web.HTTPFound("/login")

    with open(os.path.join(dir_path, "static", "index.html"), encoding="utf-8") as f:
        index_html = f.read()

    return web.Response(
        text=index_html,
        content_type="text/html",
    )


async def websocket_handler(request):
    session = await get_session(request)

    if not session.get("logged_in"):
        return web.Response(status=401)

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    state = request.app["state"]
    clients = state["clients"]
    clients.add(ws)

    # Send current text to new client
    await ws.send_str(state["shared_text"])

    try:
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue

            # prevent updates and revert to last valid state if text reached character limit
            if len(msg.data.encode("utf-8")) > MAX_MESSAGE_SIZE:
                await ws.send_str(state["shared_text"])
                continue

            state["shared_text"] = msg.data

            dead = []
            for client in list(clients):
                if client.closed:
                    dead.append(client)
                    continue
                # don't send sender's updates back to themselves
                if client is ws:
                    continue

                try:
                    await client.send_str(state["shared_text"])
                except Exception:
                    dead.append(client)

            for client in dead:
                clients.discard(client)

    finally:
        clients.discard(ws)

    return ws


async def on_shutdown(app):
    """Clean shutdown by closing websockets first"""
    for ws in list(app["state"]["clients"]):
        await ws.close(
            code=1001,
            message=b"Server shutting down",
        )
    print(f"{Colors.BLUE}CTRL+C detected, shutting down server...{Colors.ENDC}")


def get_interfaces():
    """Get active physical network adapters"""
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    exclude = (
        "virtual",
        "vmware",
        "vbox",
        "hyper-v",
        "bluetooth",
        "npcap",
        "teredo",
        "isatap",
        "wsl",
        "docker",
        "vethernet",
        "hamachi",
        "tailscale",
        "zerotier",
    )
    interfaces = []

    for iface, stat in stats.items():
        if not stat.isup:
            continue

        name = iface.lower()

        if any(x in name for x in exclude):
            continue

        for addr in addrs.get(iface, []):
            if addr.family == socket.AF_INET:
                interfaces.append((iface, addr.address))

    return interfaces


if __name__ == "__main__":
    dir_path = os.path.dirname(os.path.realpath(__file__))
    MAX_MESSAGE_SIZE = 1 * 1024 * 1024  # 1 MiB

    app = web.Application()
    logging.basicConfig(level=logging.INFO)

    # per instance session token
    secret_key = secrets.token_bytes(32)
    setup(
        app,
        EncryptedCookieStorage(secret_key, samesite="Strict"),
    )

    # randomly generated session password
    ph = PasswordHasher()
    password = generate_passphrase(
        num_words=2, separator="", add_symbols=True, wordlist=Wordlist.SHORT_2
    )
    password_hash = ph.hash(password)

    app["state"] = {
        "shared_text": "",
        "clients": set(),
        "ph": ph,
        "password_hash": password_hash,
    }

    static_dir = os.path.join(dir_path, "static")
    app.router.add_static("/static/", static_dir)
    app.router.add_get("/", index)
    app.router.add_get("/login", login)
    app.router.add_post("/login", login)
    app.router.add_get("/logout", logout)
    app.router.add_get("/ws", websocket_handler)
    app.on_shutdown.append(on_shutdown)

    # ssl certs
    cert_path = os.path.join(dir_path, "cert", "server.crt")
    key_path = os.path.join(dir_path, "cert", "server.key")
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(cert_path, key_path)
    HOST = "0.0.0.0"
    PORT = 3924

    if HOST == "0.0.0.0":
        print(
            f" * Running on all interfaces: {Colors.UNDERLINE}https://0.0.0.0:{PORT}{Colors.ENDC}"
        )
        interfaces = get_interfaces()
        for interface, ip in interfaces:
            print(
                f"   * {interface}: {Colors.UNDERLINE}https://{ip}:{PORT}{Colors.ENDC}"
            )
    else:
        print(f" * Running on {Colors.UNDERLINE}https://{HOST}:{PORT}{Colors.ENDC}")

    print(f" * Password: {Colors.BOLD}{password}{Colors.ENDC}")
    print(f"{Colors.BLUE}Press CTRL+C to quit{Colors.ENDC}")

    try:
        web.run_app(
            app,
            host=HOST,
            port=PORT,
            ssl_context=ssl_context,
            shutdown_timeout=2,
            print=None,
        )
    except KeyboardInterrupt:
        pass
