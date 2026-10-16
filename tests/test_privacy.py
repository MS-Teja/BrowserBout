from browserbout.suites.privacy import TrackerList, site_domain


def test_tracker_domains_match_subdomains() -> None:
    trackers = TrackerList(["# comment", "doubleclick.net", "", "facebook.com/tr"])
    assert trackers.match("https://securepubads.g.doubleclick.net/x.js") == "doubleclick.net"
    assert trackers.match("https://doubleclick.net/") == "doubleclick.net"
    assert trackers.match("https://notdoubleclick.net/") is None
    assert trackers.match("https://www.facebook.com/tr?id=1") == "facebook.com/tr"
    assert trackers.match("https://www.facebook.com/profile") is None


def test_bundled_list_loads() -> None:
    trackers = TrackerList.bundled()
    assert "google-analytics.com" in trackers.domains
    assert trackers.match("https://www.googletagmanager.com/gtm.js") == "googletagmanager.com"


def test_site_domain() -> None:
    assert site_domain("https://www.leetcode.com/problemset/") == "leetcode.com"
    assert site_domain("https://news.bbc.co.uk/") == "bbc.co.uk"
    assert site_domain("https://github.com") == "github.com"
