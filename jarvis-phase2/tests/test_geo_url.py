import unittest

try:
    from jarvis.geo_url import normalize_url
except ModuleNotFoundError:
    from geo_url import normalize_url


class NormalizeURLTests(unittest.TestCase):
    def test_tracking_removed_but_variant_preserved(self):
        first = normalize_url("HTTPS://Example.COM:443/p?utm_source=x&variant=50ml#details")
        second = normalize_url("https://example.com/p?variant=100ml")
        self.assertEqual(first.url, "https://example.com/p?variant=50ml")
        self.assertEqual(first.domain, "example.com")
        self.assertNotEqual(first.url_hash, second.url_hash)

    def test_query_order_and_tracking_do_not_change_hash(self):
        first = normalize_url("https://example.com/p?b=2&a=1&fbclid=abc")
        second = normalize_url("https://example.com/p?a=1&b=2")
        self.assertEqual(first.url_hash, second.url_hash)

    def test_source_domain_drops_www_but_url_identity_retains_it(self):
        result = normalize_url("https://www.example.com/p")
        self.assertEqual(result.domain, "example.com")
        self.assertEqual(result.url, "https://www.example.com/p")

    def test_blank_and_repeated_nontracking_values_survive(self):
        result = normalize_url("https://example.com/p?variant=&variant=50ml")
        self.assertEqual(result.url, "https://example.com/p?variant=&variant=50ml")

    def test_reject_unsafe_or_invalid_urls(self):
        for value in ("", "javascript:alert(1)", "/relative", "https://u:p@example.com/p", "https://example.com:bad/p"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_url(value)


if __name__ == "__main__":
    unittest.main()
