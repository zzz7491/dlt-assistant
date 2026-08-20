"""Simple API Server for pick-v2.html
This provides the /api/recommend-new endpoint for local testing.
Run with: python api_server.py
"""
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from recommendation_adapter import get_recommendation


class APIHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for recommendation API."""
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/api/recommend-new":
            self._handle_recommend()
        elif self.path.startswith("/public/"):
            self._serve_static()
        else:
            self.send_error(404)
    
    def _handle_recommend(self):
        """Handle recommendation API request."""
        try:
            result = get_recommendation(prev_issue=None)
            self._send_json(result)
        except Exception as e:
            error_result = {
                "status": "error",
                "message": str(e)
            }
            self._send_json(error_result, 500)
    
    def _serve_static(self):
        """Serve static files from public directory."""
        file_path = Path(__file__).parent / self.path.lstrip("/")
        if file_path.exists() and file_path.is_file():
            content_type = self._get_content_type(file_path.suffix)
            with open(file_path, "rb") as f:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", len(f.read()))
                self.end_headers()
                f.seek(0)
                self.wfile.write(f.read())
        else:
            self.send_error(404)
    
    def _send_json(self, data, status=200):
        """Send JSON response."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    
    def _get_content_type(self, suffix):
        """Get content type based on file extension."""
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
        }
        return types.get(suffix, "application/octet-stream")
    
    def log_message(self, format, *args):
        """Custom log format."""
        print(f"[API] {args[0]}")


def main():
    """Start the API server."""
    host = "localhost"
    port = 8080
    
    server = HTTPServer((host, port), APIHandler)
    print(f"\n{'='*60}")
    print(f"API Server started at http://{host}:{port}")
    print(f"{'='*60}")
    print(f"\nEndpoints:")
    print(f"  - GET /api/recommend-new  (Get recommendation)")
    print(f"  - GET /pick-v2.html       (Frontend page)")
    print(f"\nPress Ctrl+C to stop\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


if __name__ == "__main__":
    main()
