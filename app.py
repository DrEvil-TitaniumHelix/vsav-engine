"""app.py — native-window launcher for The Vassal.

The double-click entrypoint for testers: starts the local engine on a private
port in a background thread and shows the game menu in a native application
window (pywebview → WebView2 on Windows, WebKit on macOS). No browser, no
address bar, no "localhost", no command line.

Run from source:  python app.py            (random free port)
                   python app.py 8650       (fixed port, for testing)
Packaged:          double-click The Vassal.exe / The Vassal.app
"""
import os
import sys
import socket
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "ui"))
import server        # noqa: E402
import webview       # noqa: E402


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else free_port()
    # Pre-load the flagship game so /api/state is always valid even before the
    # tester picks; the menu still drives the choice via /api/load_game.
    first = os.path.join(server.ROOT, "games", server.RELEASE_GAMES[0])
    server.load_game(first)
    httpd = server.make_server(port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"The Vassal v{server.VERSION} — engine on http://127.0.0.1:{port}/menu",
          flush=True)
    webview.create_window(
        f"Legality Engine for VASSAL  ·  v{server.VERSION}",
        f"http://127.0.0.1:{port}/menu",
        # opens maximized — the fixed no-wrap topbar wants room; the minimum
        # (generous, to survive Windows display scaling) guarantees the rows
        # always fit even if the tester shrinks the window, so every control
        # keeps its permanent position (Bruce's fixed-layout rule)
        width=1600, height=900, min_size=(1600, 900), maximized=True)
    webview.start()          # blocks until the window is closed
    httpd.shutdown()


if __name__ == "__main__":
    main()
