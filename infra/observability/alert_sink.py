"""Owned, bounded local webhook receiver; no forwarding to external recipients."""
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

events = deque(maxlen=256)


class Receiver(BaseHTTPRequestHandler):
    def do_GET(self):
        data = json.dumps(list(events)).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= 262144:
            self.send_error(413)
            return
        try:
            event = json.loads(self.rfile.read(size))
        except ValueError:
            self.send_error(400)
            return
        events.append({'received_at': datetime.now(timezone.utc).isoformat(), 'payload': event})
        self.send_response(200)
        self.end_headers()


HTTPServer(('0.0.0.0', 8090), Receiver).serve_forever()
