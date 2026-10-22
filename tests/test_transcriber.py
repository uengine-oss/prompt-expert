import unittest
from unittest.mock import patch

from winwhisper.transcriber import Transcriber


class ModelSelectionTest(unittest.TestCase):
    @patch("winwhisper.transcriber.cuda_usable", return_value=False)
    def test_existing_defaults_use_small_on_cpu(self, _):
        transcriber = Transcriber()
        self.assertEqual((transcriber.model_name, transcriber.device,
                          transcriber.compute_type), ("small", "cpu", "int8"))
        self.assertEqual(transcriber.beam_size, 1)

    @patch("winwhisper.transcriber.cuda_usable", return_value=True)
    def test_cuda_keeps_large_model(self, _):
        self.assertEqual(Transcriber().model_name, "large-v3-turbo")

    @patch("winwhisper.transcriber.cuda_usable", return_value=False)
    def test_explicit_choices_are_preserved(self, _):
        self.assertEqual(Transcriber(device="cpu").model_name, "large-v3-turbo")
        self.assertEqual(Transcriber(model="base").model_name, "base")
        self.assertEqual(Transcriber(cpu_model=None).model_name, "large-v3-turbo")
