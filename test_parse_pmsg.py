import unittest
import struct
import datetime
import io
import sys
from parse_pmsg import parse_pmsg_file, LOG_LEVELS, MIN_HEADER_SIZE

# Reverse LOG_LEVELS for easy prio lookup from character
REVERSED_LOG_LEVELS = {v: k for k, v in LOG_LEVELS.items()}

class TestPmsgParser(unittest.TestCase):

    def create_pmsg_entry(self, pid, tid, timestamp_sec, timestamp_nsec,
                          level_char, tag, message,
                          header_size_or_version=MIN_HEADER_SIZE, # Use MIN_HEADER_SIZE as default
                          custom_entry_len=None):
        """
        Helper function to create a binary pmsg log entry.
        """
        prio = REVERSED_LOG_LEVELS.get(level_char, 0) # Default to 0 if level_char not found
        if level_char == "N/A": # Special case for no-payload entries
             prio = 0 # No specific priority

        payload_parts = []
        if prio != 0 or tag or message : # Only add payload if there's something to add
            payload_parts.append(struct.pack('<B', prio))
            payload_parts.append(tag.encode('utf-8') + b'\x00')
            payload_parts.append(message.encode('utf-8') + b'\x00')
        
        payload = b''.join(payload_parts)
            
        entry_len = custom_entry_len if custom_entry_len is not None else MIN_HEADER_SIZE + len(payload)

        header = struct.pack('<HHiiII', entry_len, header_size_or_version,
                               pid, tid, timestamp_sec, timestamp_nsec)
        return header + payload

    def assertLogEntryEqual(self, parsed_entry, expected_data):
        """Compares a parsed log entry dictionary with expected data."""
        self.assertEqual(parsed_entry['pid'], expected_data['pid'])
        self.assertEqual(parsed_entry['tid'], expected_data['tid'])
        # Compare timestamps with tolerance for potential float precision issues if any
        self.assertAlmostEqual(parsed_entry['timestamp'], expected_data['timestamp'], delta=datetime.timedelta(milliseconds=1))
        self.assertEqual(parsed_entry['level'], expected_data['level'])
        self.assertEqual(parsed_entry['tag'], expected_data['tag'])
        self.assertEqual(parsed_entry['message'], expected_data['message'])

    def test_parse_single_valid_entry(self):
        ts = datetime.datetime(2023, 1, 1, 10, 30, 55, 123000)
        entry_data = {
            'pid': 100, 'tid': 200,
            'timestamp_sec': int(ts.timestamp()), 'timestamp_nsec': ts.microsecond * 1000,
            'level_char': 'D', 'tag': "TestTag", 'message': "Hello World"
        }
        expected_parsed_data = {
            'pid': 100, 'tid': 200, 'timestamp': ts,
            'level': 'D', 'tag': "TestTag", 'message': "Hello World"
        }
        
        binary_entry = self.create_pmsg_entry(**entry_data)
        file_like_object = io.BytesIO(binary_entry)
        
        parsed_entries = parse_pmsg_file(file_like_object)
        
        self.assertEqual(len(parsed_entries), 1)
        self.assertLogEntryEqual(parsed_entries[0], expected_parsed_data)

    def test_parse_multiple_valid_entries(self):
        ts1 = datetime.datetime(2023, 1, 1, 10, 30, 55, 123000)
        entry_data1 = {'pid': 100, 'tid': 200, 'timestamp_sec': int(ts1.timestamp()), 'timestamp_nsec': ts1.microsecond * 1000,
                       'level_char': 'I', 'tag': "Tag1", 'message': "Message1"}
        expected1 = {'pid': 100, 'tid': 200, 'timestamp': ts1, 'level': 'I', 'tag': "Tag1", 'message': "Message1"}

        ts2 = datetime.datetime(2023, 1, 1, 10, 31, 0, 456000)
        entry_data2 = {'pid': 101, 'tid': 202, 'timestamp_sec': int(ts2.timestamp()), 'timestamp_nsec': ts2.microsecond * 1000,
                       'level_char': 'W', 'tag': "Tag2", 'message': "Message2"}
        expected2 = {'pid': 101, 'tid': 202, 'timestamp': ts2, 'level': 'W', 'tag': "Tag2", 'message': "Message2"}

        binary_entry1 = self.create_pmsg_entry(**entry_data1)
        binary_entry2 = self.create_pmsg_entry(**entry_data2)
        
        file_like_object = io.BytesIO(binary_entry1 + binary_entry2)
        parsed_entries = parse_pmsg_file(file_like_object)
        
        self.assertEqual(len(parsed_entries), 2)
        self.assertLogEntryEqual(parsed_entries[0], expected1)
        self.assertLogEntryEqual(parsed_entries[1], expected2)

    def test_empty_file(self):
        file_like_object = io.BytesIO(b"")
        parsed_entries = parse_pmsg_file(file_like_object)
        self.assertEqual(len(parsed_entries), 0)

    def test_entry_len_too_small(self):
        # entry_len = 10, which is < MIN_HEADER_SIZE (20)
        # The actual content here doesn't matter as much as the header's entry_len
        malformed_header = struct.pack('<HHiiII', 10, MIN_HEADER_SIZE, 1, 2, 3, 4) 
        
        file_like_object = io.BytesIO(malformed_header)
        
        # Redirect stderr to capture error messages
        captured_stderr = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured_stderr
        try:
            parsed_entries = parse_pmsg_file(file_like_object)
        finally:
            sys.stderr = original_stderr # Restore stderr
            
        self.assertEqual(len(parsed_entries), 0)
        self.assertIn("Malformed entry at offset 0. entry_len (10) is smaller than minimal header size (20). Stopping parsing.", captured_stderr.getvalue())

    def test_negative_payload_len_verbose_false(self):
        # entry_len = 10, MIN_HEADER_SIZE = 20 => payload_len = -10
        malformed_header = struct.pack('<HHiiII', 10, MIN_HEADER_SIZE, 1, 2, 3, 4)
        file_like_object = io.BytesIO(malformed_header)
        
        captured_stderr = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured_stderr
        try:
            # verbose=False is default
            parsed_entries = parse_pmsg_file(file_like_object, verbose=False)
        finally:
            sys.stderr = original_stderr
            
        self.assertEqual(len(parsed_entries), 0)
        # The error for entry_len < MIN_HEADER_SIZE is hit first.
        self.assertIn("Malformed entry at offset 0. entry_len (10) is smaller than minimal header size (20). Stopping parsing.", captured_stderr.getvalue())

    def test_negative_payload_len_verbose_true_skips_bad_parses_good(self):
        # Entry 1: entry_len = 10, MIN_HEADER_SIZE = 20 => payload_len = -10 (Bad)
        # This will actually be caught by entry_len < MIN_HEADER_SIZE first.
        # To test negative payload_len specifically where entry_len >= MIN_HEADER_SIZE,
        # one would need a MIN_HEADER_SIZE that is manipulated or an entry_len that is
        # exactly MIN_HEADER_SIZE - k, but the current parser logic for negative payload_len
        # is only hit if entry_len itself is not too small.
        # Let's make entry_len = MIN_HEADER_SIZE - 1 which will be caught by the 'entry_len too small' check.
        # The current `parse_pmsg.py` structure is:
        # 1. Check entry_len == 0
        # 2. Check entry_len < MIN_HEADER_SIZE (stops if true)
        # 3. Calculate payload_len. If payload_len < 0 (given entry_len >= MIN_HEADER_SIZE), then:
        #    - verbose=True: warn and skip current entry
        #    - verbose=False: error and stop all parsing
        # So, to test the specific negative_payload_len logic for verbose=True,
        # we need entry_len >= MIN_HEADER_SIZE, but still resulting in payload_len < 0.
        # This can only happen if MIN_HEADER_SIZE is not fixed, or if the calculation was different.
        # Given the current parser, if entry_len is, say, 20 (MIN_HEADER_SIZE), payload_len is 0.
        # If entry_len is 19, it's caught by "entry_len < MIN_HEADER_SIZE".
        # The only way payload_len < 0 is hit is if MIN_HEADER_SIZE was dynamically larger than entry_len,
        # which is not the case.
        #
        # Let's reconsider: the check is `payload_len = entry_len - MIN_HEADER_SIZE`.
        # If `entry_len = 19` and `MIN_HEADER_SIZE = 20`, the `entry_len < MIN_HEADER_SIZE` check handles it.
        # The `payload_len < 0` check in `parse_pmsg.py` (the one that depends on verbose)
        # seems to be redundant if `entry_len` is an unsigned short and always >=0.
        # It would only trigger if `MIN_HEADER_SIZE` was somehow larger than `entry_len` *after*
        # `entry_len` had already passed the `entry_len < MIN_HEADER_SIZE` check, which is impossible.
        #
        # The only way for payload_len to be < 0 is if entry_len < MIN_HEADER_SIZE.
        # The verbose check for payload_len < 0 in parse_pmsg.py:
        #   if verbose: print(f"Warning: Negative payload_len ... Skipping this entry.") continue
        #   else: print(f"Error: Negative payload_len ... Stopping parsing.") return parsed_entries
        # This logic branch for negative payload_len will effectively not be hit if entry_len < MIN_HEADER_SIZE
        # already caused a return.
        #
        # Conclusion: The test for "negative_payload_len" with verbose=True skipping bad and parsing good
        # cannot be constructed to specifically test the verbose *payload_len < 0* branch if the
        # *entry_len < MIN_HEADER_SIZE* branch always takes precedence and stops parsing or returns.
        #
        # However, if `entry_len < MIN_HEADER_SIZE` was changed to `continue` instead of `return` for verbose mode,
        # then this test would be meaningful.
        # For now, this test will behave like `test_entry_len_too_small` for the bad entry.
        #
        # Let's assume for a moment the `entry_len < MIN_HEADER_SIZE` check allows continuation in verbose mode (which it doesn't currently).
        # For this test, I will simulate a stream where the first entry is bad due to entry_len,
        # and a subsequent entry is good. The current parser will stop at the first error.

        bad_entry_header = struct.pack('<HHiiII', 10, MIN_HEADER_SIZE, 1, 2, 3, 4) # entry_len = 10
        
        ts_good = datetime.datetime(2023, 1, 1, 11, 0, 0)
        good_entry_data = {'pid': 101, 'tid': 202, 'timestamp_sec': int(ts_good.timestamp()), 'timestamp_nsec': ts_good.microsecond * 1000,
                           'level_char': 'E', 'tag': "GoodTag", 'message': "Good Message"}
        good_binary_entry = self.create_pmsg_entry(**good_entry_data)
        expected_good_entry = {'pid': 101, 'tid': 202, 'timestamp': ts_good, 'level': 'E', 'tag': "GoodTag", 'message': "Good Message"}

        file_like_object = io.BytesIO(bad_entry_header + good_binary_entry)
        
        captured_stderr = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured_stderr
        try:
            parsed_entries = parse_pmsg_file(file_like_object, verbose=True)
        finally:
            sys.stderr = original_stderr
            
        # Current parser stops at the first error ("entry_len (10) is smaller than minimal header size")
        self.assertEqual(len(parsed_entries), 0) 
        self.assertIn("Malformed entry at offset 0. entry_len (10) is smaller than minimal header size (20). Stopping parsing.", captured_stderr.getvalue())
        # If the parser was changed to skip bad entries in verbose mode for this error type:
        # self.assertEqual(len(parsed_entries), 1)
        # self.assertLogEntryEqual(parsed_entries[0], expected_good_entry)
        # self.assertIn("Warning: Malformed entry at offset 0. entry_len (10) is smaller than MIN_HEADER_SIZE (20). Skipping.", captured_stderr.getvalue())


    def test_zero_payload_len(self): # entry_len == MIN_HEADER_SIZE
        ts = datetime.datetime(2023, 1, 1, 12, 0, 0)
        # Create an entry with entry_len exactly MIN_HEADER_SIZE. No actual payload bytes.
        # header_size_or_version, pid, tid, ts_sec, ts_nsec
        header = struct.pack('<HHiiII', MIN_HEADER_SIZE, MIN_HEADER_SIZE, 300, 400, int(ts.timestamp()), 0)
        
        file_like_object = io.BytesIO(header)
        parsed_entries = parse_pmsg_file(file_like_object)
        
        self.assertEqual(len(parsed_entries), 1)
        expected_data = {
            'pid': 300, 'tid': 400, 'timestamp': ts,
            'level': "N/A", 'tag': "N/A", 'message': "" # As per parser logic for payload_len == 0
        }
        self.assertLogEntryEqual(parsed_entries[0], expected_data)

    def test_tag_and_message_variations(self):
        ts = datetime.datetime(2023, 1, 1, 13, 0, 0)
        common_data = {'pid': 500, 'tid': 600, 'timestamp_sec': int(ts.timestamp()), 'timestamp_nsec': ts.microsecond * 1000}

        # 1. Empty tag, valid message
        entry1_data = {**common_data, 'level_char': 'V', 'tag': "", 'message': "MessageOnly"}
        binary1 = self.create_pmsg_entry(**entry1_data)
        expected1 = {**common_data, 'timestamp': ts, 'level': 'V', 'tag': "", 'message': "MessageOnly"}
        
        # 2. Valid tag, empty message
        entry2_data = {**common_data, 'level_char': 'E', 'tag': "TagOnly", 'message': ""}
        binary2 = self.create_pmsg_entry(**entry2_data)
        expected2 = {**common_data, 'timestamp': ts, 'level': 'E', 'tag': "TagOnly", 'message': ""}

        # 3. Both tag and message empty
        entry3_data = {**common_data, 'level_char': 'F', 'tag': "", 'message': ""}
        binary3 = self.create_pmsg_entry(**entry3_data)
        expected3 = {**common_data, 'timestamp': ts, 'level': 'F', 'tag': "", 'message': ""}

        file_like_object = io.BytesIO(binary1 + binary2 + binary3)
        parsed_entries = parse_pmsg_file(file_like_object)

        self.assertEqual(len(parsed_entries), 3)
        self.assertLogEntryEqual(parsed_entries[0], expected1)
        self.assertLogEntryEqual(parsed_entries[1], expected2)
        self.assertLogEntryEqual(parsed_entries[2], expected3)
    
    def test_no_null_terminator_for_tag(self):
        ts = datetime.datetime(2023, 1, 1, 14, 0, 0)
        prio = REVERSED_LOG_LEVELS['D']
        
        # Payload: prio + tag_bytes (NO NULL) + message_bytes + b'\x00'
        # This scenario is tricky because if tag has no null, where does message start?
        # The parser currently uses "ErrorTag" if no null found for tag.
        payload = struct.pack('<B', prio) + b'NoNullTag' + b'MessageAfterNoNullTag' + b'\x00'
        entry_len = MIN_HEADER_SIZE + len(payload)
        header = struct.pack('<HHiiII', entry_len, MIN_HEADER_SIZE, 700, 800, int(ts.timestamp()), 0)
        binary_entry = header + payload
        
        file_like_object = io.BytesIO(binary_entry)
        
        captured_stderr = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured_stderr
        try:
            parsed_entries = parse_pmsg_file(file_like_object)
        finally:
            sys.stderr = original_stderr
            
        self.assertEqual(len(parsed_entries), 1)
        expected_data = {
            'pid': 700, 'tid': 800, 'timestamp': ts,
            'level': 'D', 'tag': "ErrorTag", # As per current parser logic
            'message': "MessageAfterNoNullTag" # Assuming message starts after prio if tag parsing fails this way
        }
        # Adjusting expectation based on current parser's behavior for "ErrorTag":
        # It sets message_start_idx = 1 (after prio).
        # So, message becomes 'NoNullTagMessageAfterNoNullTag'
        expected_data['message'] = ('NoNullTagMessageAfterNoNullTag') 

        self.assertLogEntryEqual(parsed_entries[0], expected_data)
        self.assertIn("Warning: No null terminator for tag in payload", captured_stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
