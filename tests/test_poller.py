import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import poller

SAMPLE_PAGE = """
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message" data-post="sourcechan/101">
  <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://cdn.example/pic1.jpg')"></a>
  <div class="tgme_widget_message_text"><b>Big Sale</b> on headphones<br/>Now <a href="https://shop.example/item/1">only 999</a> &amp; free shipping</div>
 </div>
 <div class="tgme_widget_message" data-post="sourcechan/102">
  <div class="tgme_widget_message_text">Plain text post, no photo</div>
 </div>
</div>
"""


class ParserTests(unittest.TestCase):
    def setUp(self):
        p = poller.PreviewPageParser()
        p.feed(SAMPLE_PAGE)
        self.msgs = sorted(p.messages, key=lambda m: m["id"])

    def test_two_messages_with_ids(self):
        self.assertEqual([m["id"] for m in self.msgs], [101, 102])

    def test_photo_extracted(self):
        self.assertEqual(self.msgs[0]["photo"], "https://cdn.example/pic1.jpg")
        self.assertIsNone(self.msgs[1]["photo"])

    def test_caption_html_kept(self):
        self.assertIn("<b>Big Sale</b>", self.msgs[0]["html"])


class HtmlTests(unittest.TestCase):
    def test_allowed_tags_kept_others_dropped(self):
        out = poller.to_telegram_html('<b>Hi</b> <span style="x">there</span> <script>alert(1)</script>')
        self.assertIn("<b>Hi</b>", out)
        self.assertNotIn("span", out)
        self.assertNotIn("script", out)

    def test_br_becomes_newline_and_entities_escaped(self):
        out = poller.to_telegram_html("a<br>b & c < d")
        self.assertEqual(out, "a\nb &amp; c &lt; d")

    def test_link_kept(self):
        out = poller.to_telegram_html('<a href="https://x.example/p">go</a>')
        self.assertEqual(out, '<a href="https://x.example/p">go</a>')

    def test_strong_em_normalised(self):
        out = poller.to_telegram_html("<strong>S</strong> <em>E</em>")
        self.assertEqual(out, "<b>S</b> <i>E</i>")


class LinkTests(unittest.TestCase):
    def test_first_link(self):
        html = '<a href="https://a.example/1">x</a> <a href="https://b.example/2">y</a>'
        self.assertEqual(poller.extract_first_link(html), "https://a.example/1")

    def test_no_link(self):
        self.assertIsNone(poller.extract_first_link("no links here"))


class StateTests(unittest.TestCase):
    def test_missing_token_is_a_clear_error(self):
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        with self.assertRaises(RuntimeError):
            poller.bot_url("sendMessage")


if __name__ == "__main__":
    unittest.main()
