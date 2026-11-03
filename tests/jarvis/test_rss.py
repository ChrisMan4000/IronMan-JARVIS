"""RSS news: the public-https guard (no home-network addresses), parsing, the tool."""

from __future__ import annotations

import socket
import urllib.error

import pytest

from openjarvis.tools import rss_news as rss


def _resolves_to(monkeypatch, *addresses):
    def fake_getaddrinfo(host, port, proto=0):
        if not addresses:
            raise socket.gaierror("unknown host")
        return [
            (socket.AF_INET, socket.SOCK_STREAM, proto, "", (a, port))
            for a in addresses
        ]

    monkeypatch.setattr(rss.socket, "getaddrinfo", fake_getaddrinfo)


@pytest.mark.parametrize(
    "addresses, ok",
    [
        (("93.184.216.34",), True),
        (("2606:2800:220:1::1",), True),
        (("192.168.2.101",), False),  # the Hue bridge
        (("127.0.0.1",), False),
        (("::1",), False),
        (("10.0.0.1",), False),
        (("169.254.1.1",), False),
        (
            ("93.184.216.34", "192.168.2.101"),
            False,
        ),  # one private answer is enough to refuse
        ((), False),  # name does not resolve
    ],
)
def test_public_https_guard(monkeypatch, addresses, ok):
    _resolves_to(monkeypatch, *addresses)
    assert rss._public_https("https://feeds.example.org/rss") is ok


@pytest.mark.parametrize(
    "url",
    ["http://feeds.example.org/rss", "file:///etc/passwd", "https://", "not a url"],
)
def test_only_https_urls_pass(monkeypatch, url):
    _resolves_to(monkeypatch, "93.184.216.34")
    assert rss._public_https(url) is False


def test_redirects_into_the_home_network_are_refused(monkeypatch):
    _resolves_to(monkeypatch, "192.168.2.101")
    with pytest.raises(urllib.error.URLError, match="redirect"):
        rss._SafeRedirect().redirect_request(
            None, None, 302, "Found", {}, "https://router.local/"
        )


def test_feed_url(monkeypatch):
    assert rss.feed_url("BBC") == rss.FEEDS["bbc"]
    _resolves_to(monkeypatch, "127.0.0.1")
    with pytest.raises(rss.FeedError, match="Feed refused"):
        rss.feed_url("https://localhost/feed")


RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title> First </title><pubDate>Mon, 02 Nov 2026</pubDate><link>https://a.example/1</link></item>
<item><title>Second</title><link>https://a.example/2</link></item>
</channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom one</title>
<updated>2026-11-02</updated><link href="https://b.example/1"/></entry></feed>"""


def test_headlines_rss_and_atom():
    assert rss.headlines(RSS, 5) == [
        "1. First (Mon, 02 Nov 2026) https://a.example/1",
        "2. Second () https://a.example/2",
    ]
    assert rss.headlines(RSS, 1) == ["1. First (Mon, 02 Nov 2026) https://a.example/1"]
    assert rss.headlines(ATOM, 5) == ["1. Atom one (2026-11-02) https://b.example/1"]


@pytest.mark.parametrize(
    "data, error",
    [
        (b'<!DOCTYPE r [<!ENTITY a "aaaa">]><rss>&a;</rss>', "entity declaration"),
        (b"<rss><item>", "not valid RSS or Atom"),
        (b"<rss><channel/></rss>", "No headlines found"),
    ],
)
def test_bad_feeds(data, error):
    with pytest.raises(rss.FeedError, match=error):
        rss.headlines(data, 5)


@pytest.mark.parametrize(
    "raw, limit", [(None, 5), ("x", 5), (0, 5), (-3, 1), (50, 10), ("2", 2)]
)
def test_limit(raw, limit):
    assert rss._limit(raw) == limit


def test_tool_reports_headlines_as_untrusted(monkeypatch):
    monkeypatch.setattr(rss, "download", lambda url: RSS)
    r = rss.RssNewsTool().execute(feed="nyt", limit=1)
    assert r.success
    assert (
        r.content
        == "Source: %s\n1. First (Mon, 02 Nov 2026) https://a.example/1\n%s"
        % (
            rss.FEEDS["nyt"],
            rss.UNTRUSTED_NOTE,
        )
    )


def test_tool_refuses_private_feed_without_downloading(monkeypatch):
    _resolves_to(monkeypatch, "192.168.2.101")
    monkeypatch.setattr(rss, "download", lambda url: pytest.fail("must not download"))
    r = rss.RssNewsTool().execute(feed="https://192.168.2.101/api")
    assert not r.success and r.content.startswith("Feed refused")


def test_download_failure_is_explained(monkeypatch):
    def offline(*args, **kwargs):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(rss.urllib.request.OpenerDirector, "open", offline)
    with pytest.raises(rss.FeedError, match="did not answer"):
        rss.download("https://feeds.example.org/rss")
