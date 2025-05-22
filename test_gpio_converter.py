import unittest
from gpio_converter import to_gpio_string, to_pin_number

class TestGpioConverter(unittest.TestCase):

    def test_to_gpio_string_valid_cases(self):
        # Test cases for integer to string conversion
        # (input_pin, expected_string)
        test_data = [
            (0, "0_a0"),      # First pin overall
            (5, "0_a5"),      # Provided example
            (7, "0_a7"),      # Last pin of first subgroup
            (8, "0_b0"),      # First pin of second subgroup
            (31, "0_d7"),     # Last pin of first group
            (32, "1_a0"),     # First pin of second group
            (159, "4_d7"),    # Last pin overall
            (64, "2_a0"),     # Start of group 2
            (95, "2_d7"),     # End of group 2, subgroup d
            (96, "3_a0"),     # Start of group 3
        ]
        for pin_number, expected_gpio_string in test_data:
            with self.subTest(pin_number=pin_number):
                self.assertEqual(to_gpio_string(pin_number), expected_gpio_string)

    def test_to_gpio_string_invalid_cases(self):
        # Test for out-of-range inputs
        with self.assertRaisesRegex(ValueError, "Pin number out of range. Must be between 0 and 159."):
            to_gpio_string(-1)
        with self.assertRaisesRegex(ValueError, "Pin number out of range. Must be between 0 and 159."):
            to_gpio_string(160)

    def test_to_pin_number_valid_cases(self):
        # Test cases for string to integer conversion
        # (input_gpio_string, expected_pin_number)
        test_data = [
            ("0_a0", 0),
            ("0_a5", 5),
            ("0_a7", 7),
            ("0_b0", 8),
            ("0_d7", 31),
            ("1_a0", 32),
            ("4_d7", 159),
            ("2_a0", 64),
            ("2_d7", 95),
            ("3_a0", 96),
        ]
        for gpio_string, expected_pin_number in test_data:
            with self.subTest(gpio_string=gpio_string):
                self.assertEqual(to_pin_number(gpio_string), expected_pin_number)

    def test_to_pin_number_invalid_format_cases(self):
        # Test for various invalid string formats
        invalid_strings = [
            "0_e0",  # Invalid subgroup
            "5_a0",  # Invalid group
            "0_a8",  # Invalid pin in subgroup
            "0a0",   # Missing underscore
            "_a0",   # Missing group
            "0_0",   # Missing subgroup char
            "0_a",   # Missing pin number
            "0_a0_extra", # Extra characters
            "0_A0", # Uppercase subgroup
            "0_a00", # Too many digits for pin
            "-1_a0", # Negative group
        ]
        for gpio_string in invalid_strings:
            with self.subTest(gpio_string=gpio_string):
                with self.assertRaisesRegex(ValueError, "Invalid GPIO string format. Expected format: 'group_subgroupPin', e.g., '0_a5'."):
                    to_pin_number(gpio_string)

if __name__ == '__main__':
    unittest.main()
