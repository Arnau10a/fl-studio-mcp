"""Unit tests for MCP server tool registration and Windows automation guards."""

import unittest

import server
import win_auto


class TestServerRegistration(unittest.TestCase):
    def test_expected_tools_registered(self) -> None:
        tools = server.mcp._tool_manager.list_tools()
        names = {t.name for t in tools}
        expected = {
            "fl_list_midi_ports",
            "fl_ping",
            "fl_transport",
            "fl_channels_list",
            "fl_channel_set",
            "fl_step_sequencer",
            "fl_step_sequencer_get",
            "fl_channel_editor",
            "fl_patterns",
            "fl_mixer_list",
            "fl_mixer_set",
            "fl_plugin_params",
            "fl_plugin_set",
            "fl_mixer_eq",
            "fl_playlist_list",
            "fl_playlist_set",
            "fl_midi_note",
            "fl_undo",
            "fl_ui_focus",
            "fl_add_plugin",
            "fl_search_samples",
            "fl_load_sample",
            "fl_import_midi",
            "fl_new_project",
            "fl_delete_channel",
            "ht_generate_midi",
            "ht_generate_kick_sample",
        }
        self.assertTrue(expected.issubset(names), f"Missing tools: {expected - names}")

    def test_win_auto_guard_message_when_unavailable(self) -> None:
        original = win_auto.user32
        try:
            win_auto.user32 = None
            with self.assertRaisesRegex(RuntimeError, "only supported on Windows"):
                win_auto.find_fl_studio_hwnd()
        finally:
            win_auto.user32 = original


if __name__ == "__main__":
    unittest.main()
