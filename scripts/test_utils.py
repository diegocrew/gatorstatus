import errno
import io
import unittest
from contextlib import ExitStack, redirect_stdout
from itertools import product
from unittest.mock import Mock, call, patch

import check_discord
import check_epic
import check_psn
import statusgator
import utils


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(utils, "TELEGRAM_TOKEN", "test-token"))
        self.stack.enter_context(patch.object(utils, "TELEGRAM_CHAT", "123"))
        self.output = self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.connect = self.stack.enter_context(
            patch.object(utils.http.client, "HTTPSConnection")
        )

    def connection(self, status=200):
        conn = Mock()
        conn.getresponse.return_value.status = status
        conn.getresponse.return_value.read.return_value = b'{"ok": true}'
        return conn

    def test_success_sends_html_and_closes_connection(self):
        conn = self.connection()
        self.connect.return_value = conn

        self.assertTrue(utils.send_telegram("<b>Recovered</b>"))

        conn.request.assert_called_once()
        self.assertIn(b'"parse_mode": "HTML"', conn.request.call_args.kwargs["body"])
        conn.close.assert_called_once()

    def test_network_failure_retries_with_a_fresh_connection(self):
        failed = self.connection()
        failed.request.side_effect = OSError(errno.ENETUNREACH, "Network is unreachable")
        recovered = self.connection()
        self.connect.side_effect = [failed, recovered]

        with patch("time.sleep") as sleep:
            self.assertTrue(utils.send_telegram("Recovered"))

        self.assertEqual(self.connect.call_count, 2)
        sleep.assert_called_once_with(2)
        failed.close.assert_called_once()
        recovered.close.assert_called_once()
        self.assertIn("Network is unreachable", self.output.getvalue())

    def test_exhausted_network_retries_return_false_and_close_connections(self):
        connections = [self.connection() for _ in range(3)]
        for conn in connections:
            conn.request.side_effect = OSError(errno.ENETUNREACH, "Network is unreachable")
        self.connect.side_effect = connections

        with patch("time.sleep") as sleep:
            self.assertFalse(utils.send_telegram("Recovered"))

        self.assertEqual(self.connect.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(2), call(4)])
        for conn in connections:
            conn.close.assert_called_once()
        self.assertIn("Telegram delivery failed", self.output.getvalue())

    def test_response_read_failure_is_retried(self):
        failed = self.connection()
        failed.getresponse.return_value.read.side_effect = (
            utils.http.client.IncompleteRead(b"partial", 10)
        )
        self.connect.side_effect = [failed, self.connection()]

        with patch("time.sleep"):
            self.assertTrue(utils.send_telegram("Recovered"))

        failed.close.assert_called_once()

    def test_http_rejection_is_reported_without_retry(self):
        conn = self.connection(status=403)
        self.connect.return_value = conn

        self.assertFalse(utils.send_telegram("Recovered"))

        self.connect.assert_called_once()
        conn.close.assert_called_once()
        self.assertIn("Telegram error HTTP 403", self.output.getvalue())


class NotificationStateTests(unittest.TestCase):
    def test_monitors_update_state_only_when_notification_is_delivered(self):
        cases = [
            (statusgator, "api_get", [
                (200, {"data": [{"id": "board", "name": "test"}]}),
                (200, {"data": [{"display_name": "EA", "filtered_status": "up"}]}),
            ]),
            (check_discord, "fetch_summary", [{"status": {"indicator": "none"}}]),
            (check_psn, "fetch_psn_status", [{}]),
            (check_epic, "fetch_epic_summary", [{"components": [
                {"id": "store", "name": "Epic Games Store", "group": True},
                {"group_id": "store", "status": "operational"},
            ]}]),
        ]
        for (module, fetch_name, responses), delivered in product(cases, (False, True)):
            with self.subTest(monitor=module.__name__, delivered=delivered), ExitStack() as stack:
                stack.enter_context(redirect_stdout(io.StringIO()))
                for name in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT"):
                    stack.enter_context(patch.object(module, name, "test"))
                stack.enter_context(patch.object(module, fetch_name, side_effect=responses))
                stack.enter_context(patch.object(module, "load_state", return_value={}))
                send = stack.enter_context(
                    patch.object(module, "send_telegram", return_value=delivered)
                )
                save = stack.enter_context(patch.object(module, "save_state"))
                history = stack.enter_context(patch.object(module, "append_history"))
                if module is statusgator:
                    stack.enter_context(patch.object(module, "STATUSGATOR_TOKEN", "test"))
                    stack.enter_context(patch.object(
                        module, "load_config", return_value=[{"match": "ea", "name": "EA"}]
                    ))

                if delivered:
                    module.main()
                    save.assert_called_once()
                    history.assert_called_once()
                else:
                    with self.assertRaises(SystemExit) as result:
                        module.main()
                    self.assertEqual(result.exception.code, 1)
                    save.assert_not_called()
                    history.assert_not_called()
                send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
