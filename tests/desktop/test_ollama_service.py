import unittest
from unittest import mock

from backend.desktop import ollama_service
from backend.desktop.ollama_service import OllamaService


class OllamaServiceTest(unittest.TestCase):
    def test_existing_service_is_never_started_or_stopped(self):
        service = OllamaService("http://localhost:11434")
        with mock.patch.object(service, "available", return_value=True), \
                mock.patch.object(ollama_service.subprocess, "Popen") as process:
            service.start()
            service.close()
        process.assert_not_called()

    def test_remote_endpoint_never_starts_a_local_process(self):
        with mock.patch.object(ollama_service.subprocess, "Popen") as process:
            OllamaService("https://example.org").start()
        process.assert_not_called()

    def test_owned_service_is_stopped_on_close(self):
        service = OllamaService("http://localhost:11434")
        process = mock.Mock()
        process.poll.return_value = None
        with mock.patch.object(service, "available", side_effect=[False, True]), \
                mock.patch.object(ollama_service, "find_ollama", return_value="ollama"), \
                mock.patch.object(ollama_service.subprocess, "Popen", return_value=process) as start:
            service.start()
            self.assertEqual(start.call_args.args[0], ["ollama", "serve"])
            service.close()
            service.close()
        process.terminate.assert_called_once()

    def test_missing_or_unstartable_service_does_not_prevent_opening_the_app(self):
        service = OllamaService("http://localhost:11434")
        with mock.patch.object(service, "available", return_value=False), \
                mock.patch.object(ollama_service, "find_ollama", return_value=None):
            service.start()
        with mock.patch.object(service, "available", return_value=False), \
                mock.patch.object(ollama_service, "find_ollama", return_value="ollama"), \
                mock.patch.object(ollama_service.subprocess, "Popen", side_effect=OSError("missing")), \
                self.assertLogs(ollama_service.log, "ERROR"):
            service.start()
