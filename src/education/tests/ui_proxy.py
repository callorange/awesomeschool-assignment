"""수동 브라우저 검증에서만 쓰는 loopback HTTP 장애·주소 SDK fixture다.

개발 서버 8001 앞에서 8002로 실행한다. apply/?case=lost 등으로 시나리오를
선택하며 실제 API·DB 경로는 유지하고 응답 유실과 외부 SDK만 대체한다.
운영 URL에 등록하지 않고 요청 본문·개인정보는 로그로 출력하지 않는다.
"""

import http.client
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

SDK_URL = "https://t1.kakaocdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js"
SDK_FIXTURE = b"""
window.kakao = {Postcode: class {
  constructor(options) { this.options = options; }
  embed(element) {
    for (const type of ['R', 'J']) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = type === 'R' ? 'Fixture road address' : 'Fixture lot address';
      button.onclick = () => this.options.oncomplete({
        zonecode: '04524', userSelectedType: type,
        roadAddress: 'Sejong-daero 110', jibunAddress: 'Taepyeong-ro 1',
      });
      element.append(button);
    }
    this.options.onresize({height: 420});
  }
}};
"""


class FixtureServer(ThreadingHTTPServer):
    scenario = "normal"
    posts = 0
    education_reads = 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        """개인정보가 포함될 수 있는 요청을 기본 HTTP 로그에 남기지 않는다."""

    def _reply(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _get_fixture(self, parsed, case):
        """외부 SDK와 교육 조회 실패만 대체하고 나머지는 실제 서버로 전달한다."""
        if parsed.path == "/fixture-postcode.js":
            self._reply(
                503 if case == "sdk-error" else 200, SDK_FIXTURE, "text/javascript"
            )
            return True
        if parsed.path.startswith("/api/educations/"):
            self.server.education_reads += 1
            if case == "get-failure" and self.server.education_reads == 1:
                self._reply(503, b'{"detail":"fixture unavailable"}')
                return True
        return False

    def _post_fixture(self, case):
        """확정 오류와 응답 유실 뒤 CSRF 실패를 HTTP 경계에서 재현한다."""
        self.server.posts += 1
        index = self.server.posts
        if case == "conflict":
            self._reply(409, b'{"detail":"fixture conflict"}')
            return True
        if case == "invalid" and index == 1:
            self._reply(
                400, json.dumps({"email": ["이메일을 확인해 주세요."]}).encode()
            )
            return True
        if case == "lost-csrf" and index == 2:
            self._reply(403, b"csrf fixture", "text/html")
            return True
        return False

    def _forward(self):
        """고정된 로컬 개발 서버만 호출하며 case별 응답 경계에 장애를 주입한다."""
        parsed = urlsplit(self.path)
        if parsed.path.endswith("/apply/"):
            case = parse_qs(parsed.query).get("case", ["normal"])[0]
            if case != self.server.scenario:
                self.server.scenario, self.server.posts, self.server.education_reads = (
                    case,
                    0,
                    0,
                )
        case = self.server.scenario
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        is_post = self.command == "POST" and parsed.path == "/api/applications/"
        if self._get_fixture(parsed, case) or (is_post and self._post_fixture(case)):
            return
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"if-modified-since", "if-none-match", "connection"}
        }
        connection = http.client.HTTPConnection("127.0.0.1", 8001, timeout=20)
        try:
            connection.request(self.command, self.path, body, headers)
            response = connection.getresponse()
            result = response.read()
            if self._lost_response(is_post, case, response.status):
                return
            if parsed.path.startswith("/api/educations/") and case == "stopped":
                data = json.loads(result)
                data["is_accepting_inquiries"] = False
                result = json.dumps(data).encode()
            if parsed.path == "/static/js/application.js" and case != "official":
                result = result.replace(SDK_URL.encode(), b"/fixture-postcode.js")
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in {"content-length", "connection", "cache-control"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(result)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(result)
        finally:
            connection.close()

    def _lost_response(self, is_post, case, status):
        """실제 201 저장을 확인한 뒤에만 브라우저에 실패 응답을 돌려준다."""
        if not (is_post and case in {"lost", "lost-csrf"} and self.server.posts == 1):
            return False
        if status != 201:
            raise RuntimeError("접수 후 응답 유실 fixture의 최초 저장이 실패했습니다.")
        self._reply(503, b'{"detail":"response lost after commit"}')
        return True

    def do_GET(self):
        self._forward()

    def do_POST(self):
        self._forward()


if __name__ == "__main__":
    print("UI fixture proxy: http://127.0.0.1:8002", flush=True)
    FixtureServer(("127.0.0.1", 8002), Handler).serve_forever()
