"""Load one public page or a topic, without following links or accessing local services."""

from dataclasses import dataclass
import http.client
from html.parser import HTMLParser
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import quote, urljoin, urlsplit, urlunsplit


MAX_DOWNLOAD_BYTES = 1_000_000
REQUEST_TIMEOUT = 8
MAX_REDIRECTS = 3


class SourceError(ValueError):
    """A safe, user-readable source loading failure."""


@dataclass(frozen=True)
class Source:
    title: str
    text: str
    source_url: str = ""
    truncated: bool = False


def _validated_url(value: str) -> str:
    if len(value) > 2048:
        raise SourceError("Keep the page URL under 2,048 characters.")
    if not value or any(char.isspace() or ord(char) < 32 for char in value) or "\\" in value:
        raise SourceError("Enter a complete http:// or https:// URL without spaces.")
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError
        if parts.username is not None or parts.password is not None:
            raise SourceError("URLs containing login credentials are not supported.")
        expected_port = 443 if parts.scheme.lower() == "https" else 80
        if parts.port not in {None, expected_port}:
            raise SourceError("Use a public page on the standard HTTP or HTTPS port.")
        hostname = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if not hostname or "%" in hostname:
            raise ValueError
        host = f"[{hostname}]" if ":" in hostname else hostname
        path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(parts.query, safe="/%?:@!$&'()*+,;=-._~")
        return urlunsplit((parts.scheme.lower(), host, path, query, ""))
    except SourceError:
        raise
    except (ValueError, UnicodeError):
        raise SourceError("Enter a valid complete http:// or https:// URL.") from None


def _public_address(hostname: str, port: int) -> str:
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise SourceError("The page hostname could not be resolved.")
        for _, _, _, _, address in addresses:
            parsed = ipaddress.ip_address(address[0])
            checked = parsed.ipv4_mapped if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped else parsed
            if not checked.is_global or checked.is_multicast or checked.is_reserved:
                raise SourceError("Only public web pages are allowed; local and private addresses are blocked.")
        return addresses[0][4][0]
    except SourceError:
        raise
    except (OSError, ValueError):
        raise SourceError("The page hostname could not be resolved.") from None


class _PinnedConnection(http.client.HTTPConnection):
    """Connect to the validated IP, keeping the original hostname for TLS verification."""

    def __init__(self, hostname: str, port: int, address: str, secure: bool):
        super().__init__(hostname, port, timeout=REQUEST_TIMEOUT)
        self.address = address
        self.secure = secure

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)
        if self.secure:
            try:
                self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)
            except Exception:
                self.sock.close()
                raise


def _request_once(url: str) -> tuple[int, dict[str, str], bytes]:
    parts = urlsplit(url)
    secure = parts.scheme == "https"
    port = 443 if secure else 80
    address = _public_address(parts.hostname, port)
    connection = _PinnedConnection(parts.hostname, port, address, secure)
    deadline = time.monotonic() + REQUEST_TIMEOUT
    try:
        target = urlunsplit(("", "", parts.path or "/", parts.query, ""))
        connection.request("GET", target, headers={
            "User-Agent": "StudyTutor/1.0 (single-page study material)",
            "Accept": "text/html, text/plain",
            "Accept-Encoding": "identity",
        })
        active_socket = connection.sock
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        if response.status != 200:
            return response.status, headers, b""
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
            raise SourceError("This URL does not return a readable HTML or text page. Paste its text instead.")
        if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
            raise SourceError("This page uses an unsupported response encoding. Paste its text instead.")
        try:
            content_length = int(headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        if content_length > MAX_DOWNLOAD_BYTES:
            raise SourceError("The page is too large. Paste the relevant section instead.")
        chunks = []
        downloaded = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceError("The page took too long to load. Paste its text instead.")
            active_socket.settimeout(remaining)
            chunk = response.read1(min(65_536, MAX_DOWNLOAD_BYTES + 1 - downloaded))
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if downloaded > MAX_DOWNLOAD_BYTES:
                raise SourceError("The page is too large. Paste the relevant section instead.")
        return response.status, headers, b"".join(chunks)
    finally:
        connection.close()


class _PageText(HTMLParser):
    ignored = {"head", "script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"}
    blocks = {"p", "div", "section", "article", "main", "li", "pre", "br", "hr", "tr", "h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = []
        self.in_title = False
        self.focus_depth = 0
        self.title = []
        self.all_text = []
        self.focus_text = []

    def _append(self, value):
        self.all_text.append(value)
        if self.focus_depth:
            self.focus_text.append(value)

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag in self.ignored:
            self.skip.append(tag)
        if self.skip:
            return
        if tag in {"main", "article"}:
            self.focus_depth += 1
        if tag in self.blocks:
            self._append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in self.skip:
            self.skip = self.skip[:len(self.skip) - 1 - self.skip[::-1].index(tag)]
            return
        if self.skip:
            return
        if tag in self.blocks:
            self._append("\n")
        if tag in {"main", "article"}:
            self.focus_depth = max(0, self.focus_depth - 1)

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        elif not self.skip:
            self._append(data)


def _clean(value: str) -> str:
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _fetch_page(url: str) -> tuple[str, str, str]:
    current = url
    try:
        for attempt in range(MAX_REDIRECTS + 1):
            status, headers, body = _request_once(current)
            if status in {301, 302, 303, 307, 308}:
                location = headers.get("location", "")
                if not location or attempt == MAX_REDIRECTS:
                    raise SourceError("The page has too many or invalid redirects. Paste its text instead.")
                current = _validated_url(urljoin(current, location))
                continue
            if status != 200:
                raise SourceError("The page could not be loaded. It may require login or block downloads. Paste its text instead.")
            charset = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", headers.get("content-type", ""), re.I)
            try:
                decoded = body.decode(charset.group(1) if charset else "utf-8", errors="replace")
            except LookupError:
                decoded = body.decode("utf-8", errors="replace")
            if headers.get("content-type", "").split(";", 1)[0].lower().strip() == "text/plain":
                title, text = urlsplit(current).hostname, _clean(decoded)
            else:
                parser = _PageText()
                parser.feed(decoded)
                title = _clean("".join(parser.title)) or urlsplit(current).hostname
                text = _clean("".join(parser.focus_text)) or _clean("".join(parser.all_text))
            if len(text) < 80 or len(text.split()) < 12:
                raise SourceError("Too little readable text was found. The page may need JavaScript or login; paste its text instead.")
            return title[:200], text, current
    except SourceError:
        raise
    except (OSError, http.client.HTTPException, ValueError, UnicodeError):
        raise SourceError("The page could not be downloaded safely. Paste its text instead.") from None


def load_source(url: str, topic: str, pasted_text: str = "", max_chars: int = 6000) -> Source:
    """Pasted text explicitly substitutes URL retrieval; topics can be used on their own."""
    url, topic, pasted_text = url.strip(), topic.strip(), pasted_text.strip()
    if max_chars < 80:
        raise SourceError("The source text limit must be at least 80 characters.")
    if len(topic) > 200:
        raise SourceError("Keep the topic under 200 characters.")
    if not any((url, topic, pasted_text)):
        raise SourceError("Enter a complete page URL, a topic, or pasted material.")
    validated_url = _validated_url(url) if url else ""
    if pasted_text:
        title, text, source_url = topic or "Pasted study material", pasted_text, validated_url
    elif validated_url:
        title, text, source_url = _fetch_page(validated_url)
        title = topic or title
    else:
        title, text, source_url = topic, f"Study topic: {topic}", ""
    return Source(title, text[:max_chars], source_url, len(text) > max_chars)
