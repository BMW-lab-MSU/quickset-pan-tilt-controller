import unittest

from quickset_pan_tilt.protocol import *

class TestProtocol(unittest.TestCase):

    def test_insert_escape_sequence1(self):
        to_send = 0x02
        expected = bytes.fromhex("1b82")

        escaped = QuicksetProtocol.insert_escape_sequence(to_send)

        self.assertEqual(expected, escaped)

    def test_insert_escape_sequence2(self):
        to_send = 0x1B
        expected = bytes.fromhex("1B9B")

        escaped = QuicksetProtocol.insert_escape_sequence(to_send)

        self.assertEqual(expected, escaped)

    def test_insert_two_escape_sequences(self):
        to_send = bytes.fromhex("0203")
        expected = bytes.fromhex("1b821b83")

        escaped = QuicksetProtocol.escape_control_chars(to_send)

        self.assertEqual(expected, escaped)
    
    def test_remove_escape_sequence(self):
        received = bytes.fromhex("1b9b")
        expected = bytes.fromhex("1b")

        res = QuicksetProtocol.remove_escape_sequences(received)

        self.assertEqual(expected, res)

    def test_remove_escape_sequence2(self):
        received = bytes.fromhex("1b821b83")
        expected = bytes.fromhex("0203")

        res = QuicksetProtocol.remove_escape_sequences(received)

        self.assertEqual(expected, res)

        
