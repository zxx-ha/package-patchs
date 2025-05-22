import re
import sys

def to_gpio_string(pin_number: int) -> str:
    """Converts an integer pin number to GPIO string format (e.g., 0_a5)."""
    if not 0 <= pin_number <= 159:
        raise ValueError("Pin number out of range. Must be between 0 and 159.")

    group = pin_number // 32
    pin_in_group = pin_number % 32
    subgroup_index = pin_in_group // 8
    subgroup_char_map = ['a', 'b', 'c', 'd']
    subgroup_char = subgroup_char_map[subgroup_index]
    pin_in_subgroup = pin_in_group % 8

    return f"{group}_{subgroup_char}{pin_in_subgroup}"

def to_pin_number(gpio_string: str) -> int:
    """Converts a GPIO string (e.g., 0_a5) to an integer pin number."""
    match = re.match(r"^([0-4])_([a-d])([0-7])$", gpio_string)
    if not match:
        raise ValueError(
            "Invalid GPIO string format. Expected format: 'group_subgroupPin', e.g., '0_a5'."
        )

    group_num_str, subgroup_char, pin_in_subgroup_str = match.groups()

    group = int(group_num_str)
    pin_in_subgroup = int(pin_in_subgroup_str)
    subgroup_char_map = {'a': 0, 'b': 1, 'c': 2, 'd': 3}
    subgroup_index = subgroup_char_map[subgroup_char]

    pin_number = group * 32 + subgroup_index * 8 + pin_in_subgroup
    return pin_number

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:")
        print("  python gpio_converter.py <pin_number>")
        print("  python gpio_converter.py <gpio_string>")
        print("Examples:")
        print("  python gpio_converter.py 5")
        print("  python gpio_converter.py 0_a5")
        sys.exit(1)

    argument = sys.argv[1]

    try:
        try:
            pin_number_arg = int(argument)
            result = to_gpio_string(pin_number_arg)
            print(result)
        except ValueError:
            # If int() conversion fails, assume it's a gpio_string
            result = to_pin_number(argument)
            print(result)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
