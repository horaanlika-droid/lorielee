#!/usr/bin/env python3
"""Dev server for the player with HTTP Range support (chapter seeking without a full download).

    python3 scripts/serve_local.py [--port 8000]

Not needed on GitHub Pages; it is only for checking the site locally.
"""

from __future__ import annotations

import argparse
import functools
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):  # noqa: N802 - имя из базового класса
        header = self.headers.get("Range")
        if not header or not (match := RANGE.match(header)):
            return super().send_head()
        path = self.translate_path(self.path)
        if not Path(path).is_file():
            return super().send_head()
        size = Path(path).stat().st_size
        start = int(match.group(1) or 0)
        end = int(match.group(2)) if match.group(2) else size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        file = open(path, "rb")
        file.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._range_left = end - start + 1
        return file

    def copyfile(self, source, outputfile):  # noqa: N802
        left = getattr(self, "_range_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            chunk = source.read(min(65536, left))
            if not chunk:
                break
            outputfile.write(chunk)
            left -= len(chunk)
        self._range_left = None

    def log_message(self, fmt, *args):  # тише в логах
        if "/episodes.json" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    handler = functools.partial(RangeHandler, directory=str(ROOT))
    with ThreadingHTTPServer(("0.0.0.0", args.port), handler) as httpd:
        print(f"Serving {ROOT} on 0.0.0.0:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
