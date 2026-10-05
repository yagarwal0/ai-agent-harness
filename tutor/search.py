"""One bounded Brave web search for study context; result pages are never fetched."""

from dataclasses import dataclass
from html import unescape
import http.client
import ipaddress
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit, urlunsplit


MAX_QUERY_CHARS = 300
MAX_RESULTS = 3
MAX_CONTEXT_CHARS = 4_000
MAX_RESPONSE_BYTES = 1_000_000
REQUEST_TIMEOUT = 8


class SearchError(ValueError):
    """A safe, user-readable failure without provider response bodies or credentials."""


@dataclass(frozen=True)
class SearchContext:
    text: str
    sources: list[dict[str, str]]
    query: str


def _text(value: object, key: str, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    value = unescape(re.sub(r"<[^>]*>", "", value)).replace(key, "[REDACTED]")
    return " ".join(value.split())[:limit]


def _source_url(value: object, key: str) -> str:
    """Validate citation links without DNS lookups or following them."""
    if not isinstance(value, str) or len(value) > 2_048 or key in value:
        return ""
    if "\\" in value or any(char.isspace() or ord(char) < 32 for char in value):
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return ""
        if parts.username is not None or parts.password is not None:
            return ""
        if parts.port not in {None, 443 if parts.scheme == "https" else 80}:
            return ""
        host = parts.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local")):
            return ""
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # A dotted hostname is a citation, not an instruction to fetch a page.
            if "." not in host or "%" in host:
                return ""
        else:
            checked = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
            if not checked.is_global or checked.is_multicast or checked.is_reserved:
                return ""
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    except (ValueError, UnicodeError):
        return ""


class BraveSearch:
    """Credentials are loaded only when an explicitly requested search starts."""

    def __init__(self, key_path: str | Path | None = None):
        self.key_path = key_path

    def search(self, query: str, *, max_results: int = MAX_RESULTS) -> SearchContext:
        query = " ".join(query.split())
        if not query or len(query) > MAX_QUERY_CHARS or len(query.split()) > 75:
            raise SearchError("Keep the context search query between 1 and 300 characters and at most 75 words.")
        if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= MAX_RESULTS:
            raise SearchError("A context search can return at most three sources.")

        # Load Brave credentials only when a search is actually requested.
        from tutor.secrets import load_key
        try:
            key = load_key("brave", self.key_path)
        except (OSError, ValueError):
            raise SearchError("Brave Search credentials are unavailable. Check the local key configuration.") from None
        if not isinstance(key, str) or not key or "\n" in key or "\r" in key:
            raise SearchError("Brave Search credentials are unavailable. Check the local key configuration.")

        params = urlencode({"q": query, "count": max_results, "result_filter": "web", "text_decorations": "false"})
        connection = http.client.HTTPSConnection("api.search.brave.com", timeout=REQUEST_TIMEOUT)
        deadline = time.monotonic() + REQUEST_TIMEOUT
        try:
            connection.request("GET", "/res/v1/web/search?" + params, headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "X-Subscription-Token": key,
            })
            active_socket = connection.sock
            response = connection.getresponse()
            if response.status != 200:
                # Do not read error bodies: providers can echo sensitive headers.
                raise SearchError("Brave Search could not provide context. Check its key, plan, or request allowance.")
            headers = {name.lower(): value for name, value in response.getheaders()}
            if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                raise SearchError("Brave Search returned an unsupported response.")
            try:
                content_length = int(headers.get("content-length", "0"))
            except ValueError:
                content_length = 0
            if content_length > MAX_RESPONSE_BYTES:
                raise SearchError("Brave Search returned too much data.")
            chunks, downloaded = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SearchError("Brave Search took too long to provide context.")
                active_socket.settimeout(remaining)
                chunk = response.read1(min(65_536, MAX_RESPONSE_BYTES + 1 - downloaded))
                if not chunk:
                    break
                chunks.append(chunk)
                downloaded += len(chunk)
                if downloaded > MAX_RESPONSE_BYTES:
                    raise SearchError("Brave Search returned too much data.")
            data = json.loads(b"".join(chunks).decode("utf-8"))
        except SearchError:
            raise
        except (OSError, http.client.HTTPException, ValueError, UnicodeError):
            raise SearchError("Brave Search could not provide context safely. Try again later or paste study material.") from None
        finally:
            connection.close()

        web = data.get("web") if isinstance(data, dict) else None
        results = web.get("results") if isinstance(web, dict) else None
        if not isinstance(results, list):
            raise SearchError("Brave Search did not return usable study sources.")
        sources, blocks, seen = [], [], set()
        for item in results:
            if not isinstance(item, dict):
                continue
            url = _source_url(item.get("url"), key)
            snippet = _text(item.get("description"), key, 800)
            title = _text(item.get("title"), key, 160) or "Study source"
            if not url or not snippet or url in seen:
                continue
            block = f"Source: {title}\nURL: {url}\nSearch snippet: {snippet}"
            if len("\n\n".join([*blocks, block])) > MAX_CONTEXT_CHARS:
                break
            sources.append({"title": title, "url": url})
            blocks.append(block)
            seen.add(url)
            if len(sources) == max_results:
                break
        if not sources:
            raise SearchError("Brave Search did not return usable study sources. Paste relevant material instead.")
        return SearchContext("\n\n".join(blocks), sources, query.replace(key, "[REDACTED]"))
