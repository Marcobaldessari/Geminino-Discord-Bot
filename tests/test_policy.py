import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy import (  # noqa: E402
    DISCORD_MESSAGE_LIMIT,
    MAX_ATTACHMENT_CHARS,
    BotRequest,
    ContextMessage,
    TextAttachment,
    compose_question,
    ensure_sources,
    find_pending_question,
    fit_to_discord_message,
    format_transcript,
    is_text_attachment,
    parse_bot_request,
    prepare_discord_reply,
    resolve_mode,
    split_into_messages,
    strip_bot_mention,
    suppress_link_previews,
)


def _message(author_id: str, content: str, created_at: datetime, bot: bool = False) -> ContextMessage:
    return ContextMessage(
        author=author_id, content=content, created_at=created_at, author_id=author_id, bot=bot
    )


class TranscriptTests(unittest.TestCase):
    def test_keeps_only_the_latest_messages(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        messages = [
            ContextMessage(author=f"user-{i}", content=f"message-{i}", created_at=base + timedelta(seconds=i))
            for i in range(35)
        ]
        result = format_transcript(messages, limit=30)
        self.assertEqual(len(result.split("\n")), 30)
        self.assertNotIn("message-4:", result)
        self.assertIn("message-5", result)
        self.assertIn("message-34", result)

    def test_marks_empty_messages(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = format_transcript([ContextMessage(author="a", content="  ", created_at=base)])
        self.assertIn("[attachment or empty message]", result)


class LinkTests(unittest.TestCase):
    def test_wraps_markdown_and_bare_urls(self):
        self.assertEqual(
            suppress_link_previews("See [OECD](https://oecd.org) and https://pewresearch.org/x."),
            "See [OECD](<https://oecd.org>) and <https://pewresearch.org/x>.",
        )

    def test_does_not_double_wrap(self):
        text = "See <https://oecd.org> and [Pew](<https://pewresearch.org>)"
        self.assertEqual(suppress_link_previews(text), text)

    def test_fits_a_long_reply_into_one_message(self):
        result = fit_to_discord_message("word " * 1000)
        self.assertLessEqual(len(result), DISCORD_MESSAGE_LIMIT)

    def test_appends_missing_sources(self):
        self.assertIn(
            "Sources:\n- <https://example.com/source>",
            ensure_sources("Answer", ["https://example.com/source"]),
        )


class ParsingTests(unittest.TestCase):
    def test_parses_mode_commands_and_one_shot_overrides(self):
        self.assertEqual(parse_bot_request("mode"), BotRequest(type="status"))
        self.assertEqual(parse_bot_request("mode deep"), BotRequest(type="set", mode="deep"))
        self.assertEqual(parse_bot_request("approfondito"), BotRequest(type="set", mode="deep"))
        self.assertEqual(
            parse_bot_request("deep fertility in Italy"),
            BotRequest(type="ask", text="fertility in Italy", mode="deep", persist=False),
        )
        self.assertEqual(
            parse_bot_request("mode deep fertility in Italy"),
            BotRequest(type="ask", text="fertility in Italy", mode="deep", persist=True),
        )
        self.assertEqual(
            parse_bot_request("What is TFR in Italy?"),
            BotRequest(type="ask", text="What is TFR in Italy?"),
        )
        self.assertEqual(parse_bot_request("help"), BotRequest(type="help"))
        self.assertEqual(parse_bot_request("aiuto"), BotRequest(type="help"))

    def test_accepts_the_mode_keyword_on_either_side(self):
        self.assertEqual(parse_bot_request("deep mode"), BotRequest(type="set", mode="deep"))
        self.assertEqual(parse_bot_request("compact modo"), BotRequest(type="set", mode="compact"))
        self.assertEqual(parse_bot_request("modalità deep"), BotRequest(type="set", mode="deep"))
        self.assertEqual(parse_bot_request("deep mode?"), BotRequest(type="set", mode="deep"))
        self.assertEqual(
            parse_bot_request("deep mode fertility in Italy"),
            BotRequest(type="ask", text="fertility in Italy", mode="deep", persist=True),
        )

    def test_does_not_eat_the_first_word_of_a_question(self):
        self.assertEqual(
            parse_bot_request("Analisi del calo demografico italiano"),
            BotRequest(type="ask", text="Analisi del calo demografico italiano"),
        )
        self.assertEqual(
            parse_bot_request("Report completo sul debito pubblico"),
            BotRequest(type="ask", text="Report completo sul debito pubblico"),
        )
        self.assertEqual(parse_bot_request("analisi"), BotRequest(type="set", mode="deep"))

    def test_resolves_a_configured_default_mode(self):
        self.assertEqual(resolve_mode("deep"), "deep")
        self.assertEqual(resolve_mode(" Compact "), "compact")
        self.assertEqual(resolve_mode("approfondito"), "deep")
        self.assertIsNone(resolve_mode("verbose"))
        self.assertIsNone(resolve_mode(None))

    def test_strips_bot_mentions_before_parsing(self):
        self.assertEqual(strip_bot_mention("@Geminino mode deep", ["Geminino"]), "mode deep")
        self.assertEqual(strip_bot_mention("<@123456> mode deep", []), "mode deep")

    def test_keeps_line_breaks_in_long_prompts(self):
        self.assertEqual(
            strip_bot_mention("@Geminino  Analizza:\n\n- punto  uno\n- punto due", ["Geminino"]),
            "Analizza:\n\n- punto uno\n- punto due",
        )


class AttachmentTests(unittest.TestCase):
    def test_recognises_text_attachments(self):
        self.assertTrue(is_text_attachment("message.txt", "text/plain; charset=utf-8"))
        self.assertTrue(is_text_attachment("prompt.md", None))
        self.assertTrue(is_text_attachment("data.json", "application/json"))
        self.assertFalse(is_text_attachment("screenshot.png", "image/png"))

    def test_uses_an_attached_file_as_the_prompt(self):
        attached = [TextAttachment(name="message.txt", text="Analizza il calo demografico italiano.\n")]
        self.assertEqual(
            compose_question(None, attached),
            'Attached file "message.txt":\nAnalizza il calo demografico italiano.',
        )
        self.assertEqual(
            compose_question("Confronta con la Spagna", attached),
            'Confronta con la Spagna\n\nAttached file "message.txt":\nAnalizza il calo demografico italiano.',
        )
        self.assertEqual(compose_question(None, [TextAttachment(name="empty.txt", text="   ")]), "")
        oversized = compose_question(None, [TextAttachment(name="big.txt", text="x" * (MAX_ATTACHMENT_CHARS + 500))])
        self.assertEqual(len(oversized), MAX_ATTACHMENT_CHARS + len('Attached file "big.txt":\n'))


class PendingQuestionTests(unittest.TestCase):
    def test_uses_the_previous_user_prompt_after_a_bare_mode_switch(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        found = find_pending_question(
            [
                _message("u1", "Analizza il calo demografico italiano con tre scenari.", now - timedelta(minutes=1)),
                _message("u1", "@Geminino mode deep", now),
            ],
            author_id="u1",
            bot_names=["Geminino"],
            now=now,
        )
        self.assertEqual(found, "Analizza il calo demografico italiano con tre scenari.")

    def test_ignores_other_authors_bots_and_stale_messages(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        messages = [
            _message("u2", "Domanda di un altro utente", now - timedelta(minutes=1)),
            _message("u1", "Domanda vecchia", now - timedelta(hours=2)),
            _message("u1", "Risposta del bot", now, bot=True),
        ]
        self.assertIsNone(find_pending_question(messages, author_id="u1", bot_names=["Geminino"], now=now))


class ReplyTests(unittest.TestCase):
    def test_splits_a_report_into_sendable_messages(self):
        report = "\n\n".join(f"## Section {i}\n\n{'parola ' * 60}" for i in range(60))
        chunks = split_into_messages(report)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= DISCORD_MESSAGE_LIMIT and chunk.strip() for chunk in chunks))
        self.assertTrue(chunks[0].startswith("## Section 0"))
        self.assertEqual(split_into_messages("short one"), ["short one"])
        self.assertEqual(split_into_messages("   "), [])

    def test_caps_the_number_of_chunks(self):
        chunks = split_into_messages("x " * 40_000, DISCORD_MESSAGE_LIMIT, 3)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(chunks[-1].endswith("…"))

    def test_compact_stays_in_one_message_and_deep_attaches_overflow(self):
        long_text = f"{'word ' * 500}\nhttps://example.com/a"
        compact = prepare_discord_reply(long_text, [], "compact")
        self.assertLessEqual(len(compact.content), DISCORD_MESSAGE_LIMIT)
        self.assertEqual(compact.files, [])
        deep = prepare_discord_reply(long_text, [], "deep")
        self.assertIn("full report attached", deep.content)
        self.assertEqual(deep.files[0][0], "report.md")


if __name__ == "__main__":
    unittest.main()
