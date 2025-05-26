"""
Parses Android pmsg (Persistent Message Store) log files.

This script assumes a common structure for userspace logger entries found in pmsg,
often used for logs like "logcat -L" (brief format). The pmsg entries are typically
a sequence of binary structures.

Assumed Log Entry Structure (logger_entry_v2/v3 like):
------------------------------------------------------
Each entry is expected to have the following structure:

1.  Header (Fixed size, typically 20 bytes = MIN_HEADER_SIZE):
    *   `entry_len` (uint16_t): Total length of this log entry (header + payload).
    *   `header_size_or_version` (uint16_t): Size of this header or version indicator.
                                         This script uses a fixed MIN_HEADER_SIZE (20 bytes)
                                         for payload calculation, assuming a common structure.
    *   `pid` (int32_t): Process ID of the logging process.
    *   `tid` (int32_t): Thread ID of the logging thread.
    *   `sec` (int32_t): Timestamp in seconds since epoch.
    *   `nsec` (int32_t): Nanoseconds part of the timestamp.

2.  Payload (Variable size, `entry_len - MIN_HEADER_SIZE`):
    *   `prio` (uint8_t): Priority of the log message (maps to V, D, I, W, E, F).
    *   `tag` (null-terminated string): Log tag (e.g., "ActivityManager").
    *   `message` (null-terminated string): The actual log message.

The script reads these binary entries, parses them, and outputs them in a
human-readable format, similar to `logcat -L`. It also includes error handling
for malformed entries and a verbose mode for debugging.
"""
import struct
import datetime
import argparse
import sys
import os

# Mapping of log priority values to their character representations (e.g., logcat brief format)
LOG_LEVELS = {
    2: "V",  # Verbose
    3: "D",  # Debug
    4: "I",  # Info
    5: "W",  # Warn
    6: "E",  # Error
    7: "F",  # Fatal
}

# Minimum size of the entry header (entry_len, header_size_or_version, pid, tid, sec, nsec)
# 2 (entry_len) + 2 (header_size_or_version) + 4 (pid) + 4 (tid) + 4 (sec) + 4 (nsec) = 20 bytes
MIN_HEADER_SIZE = 20

def parse_pmsg_file(filepath, verbose=False):
    """
    Parses a pmsg log file based on the assumed Android userspace logger structure.

    Args:
        filepath (str or file-like object): The path to the pmsg file or a file-like object.
        verbose (bool): Whether to print verbose diagnostic output to stderr.

    Returns:
        list: A list of dictionaries, where each dictionary represents a parsed log entry.
              Each dictionary contains keys: "timestamp", "pid", "tid", "level", "tag", "message".
              Returns an empty list if the file cannot be read, is empty, or parsing fails early.
    """
    parsed_entries = []
    file_opened_successfully = False # Flag to provide better error context for generic exceptions

    # Internal helper to determine if we're dealing with a real file path or a file-like object
    is_file_path = isinstance(filepath, (str, bytes, os.PathLike))

    try:
        # Open the file in binary read mode. If filepath is already a file-like object, use it directly.
        with (open(filepath, 'rb') if is_file_path else filepath) as f:
            if not is_file_path: # If it's a file-like object, ensure it's seekable for f.tell()
                f.seek(0, os.SEEK_CUR) # Test seekability / get current position for non-file objects

            file_opened_successfully = True
            while True:
                current_offset = f.tell() # Get current file offset for error reporting

                # 1. Read the first part of the header: entry_len and header_size_or_version
                #    `entry_len`: Total length of this log entry (header + payload). (uint16_t)
                #    `header_size_or_version`: Typically the size of this header. (uint16_t)
                header_prefix_data = f.read(4) # Read 2 bytes for entry_len, 2 for header_size_or_version
                
                if not header_prefix_data:
                    break  # End of file reached cleanly

                if len(header_prefix_data) < 4:
                    # Should not happen if `not header_prefix_data` is true, but good for robustness.
                    print(f"Error: Incomplete entry header prefix at offset {current_offset}. Read {len(header_prefix_data)} bytes, expected 4. Stopping.", file=sys.stderr)
                    break # Stop parsing on incomplete critical header fields
                
                try:
                    # Unpack as little-endian unsigned shorts (H)
                    entry_len, header_size_or_version = struct.unpack('<HH', header_prefix_data)
                except struct.error as e:
                    print(f"Error: Failed to unpack entry_len/header_size_or_version at offset {current_offset}. Struct error: {e}. Stopping.", file=sys.stderr)
                    return parsed_entries # Return what has been successfully parsed so far

                # Handle entries with entry_len == 0 (often padding or end markers)
                if entry_len == 0:
                    if verbose:
                        print(f"Verbose: Skipping entry with zero length at offset {current_offset}.", file=sys.stderr)
                    continue # Move to the next entry

                # Validate entry_len against the minimum expected header size
                if entry_len < MIN_HEADER_SIZE:
                    print(f"Error: Malformed entry at offset {current_offset}. entry_len ({entry_len}) is smaller than minimal header size ({MIN_HEADER_SIZE}). Stopping parsing.", file=sys.stderr)
                    return parsed_entries # Stop parsing as the entry is critically malformed

                # 2. Read the rest of the fixed-size header fields
                #    `pid` (int32_t): Process ID.
                #    `tid` (int32_t): Thread ID.
                #    `sec` (int32_t): Timestamp (seconds).
                #    `nsec` (int32_t): Timestamp (nanoseconds).
                fixed_header_data_len_expected = MIN_HEADER_SIZE - 4 # Already read 4 bytes
                fixed_header_data = f.read(fixed_header_data_len_expected)
                
                if len(fixed_header_data) < fixed_header_data_len_expected:
                    print(f"Error: Incomplete entry header at offset {current_offset + 4}. Expected {fixed_header_data_len_expected} bytes, got {len(fixed_header_data)}. Stopping.", file=sys.stderr)
                    break # Stop parsing due to incomplete header
                
                try:
                    # Unpack as little-endian: signed int (i), signed int (i), unsigned int (I), unsigned int (I)
                    pid, tid, sec, nsec = struct.unpack('<iiII', fixed_header_data)
                except struct.error as e:
                    print(f"Error: Failed to unpack pid/tid/sec/nsec at offset {current_offset + 4}. Struct error: {e}. Stopping.", file=sys.stderr)
                    return parsed_entries

                # Calculate payload length
                payload_len = entry_len - MIN_HEADER_SIZE
                
                if verbose:
                    print(f"Verbose: Parsed header at offset {current_offset}: raw_len={entry_len}, hdr_size={header_size_or_version}, pid={pid}, tid={tid}, sec={sec}, nsec={nsec}, payload_len={payload_len}", file=sys.stderr)

                # Handle potentially corrupted payload_len (should be caught by entry_len < MIN_HEADER_SIZE if negative)
                if payload_len < 0:
                    if verbose:
                        # In verbose mode, warn and try to skip this problematic entry.
                        # This situation (payload_len < 0 while entry_len >= MIN_HEADER_SIZE) implies
                        # a highly unusual or corrupted entry_len value.
                        print(f"Warning: Negative payload_len ({payload_len}) calculated for entry_len {entry_len} at offset {current_offset}. This is unexpected as entry_len check passed. Skipping this entry.", file=sys.stderr)
                        # Attempting to skip the remainder of the claimed entry_len.
                        # We've read MIN_HEADER_SIZE bytes for the header from this entry.
                        # The rest to skip would be entry_len - MIN_HEADER_SIZE.
                        # However, since payload_len is negative, this is payload_len itself.
                        # This indicates a fundamental inconsistency.
                        # The most robust way to skip would be to advance f by (current_offset + entry_len)
                        # but f.read() is safer if entry_len is astronomically large and wrong.
                        # For now, we just continue, effectively skipping the payload read.
                        # The file pointer is already at the start of the payload.
                        # We need to advance it by payload_len if we were to read it.
                        # Since we are skipping, and payload_len is negative, we cannot f.read(negative_value).
                        # The next loop iteration will start reading from current_offset + MIN_HEADER_SIZE.
                        # This might lead to cascading errors if the file structure is truly off.
                        # A safer skip for corrupted entries of unknown actual length might be harder.
                        # The current verbose behavior is to log and hope the next entry aligns.
                        continue 
                    else:
                        # In non-verbose mode, treat as a critical error and stop.
                        print(f"Error: Negative payload_len ({payload_len}) calculated for entry_len {entry_len} at offset {current_offset}. Stopping parsing.", file=sys.stderr)
                        return parsed_entries

                # Handle entries with no actual payload content (header only)
                if payload_len == 0:
                    if verbose:
                        print(f"Verbose: Entry at offset {current_offset} has no payload (message part is empty).", file=sys.stderr)
                    
                    # Create timestamp from seconds and nanoseconds
                    timestamp = datetime.datetime.fromtimestamp(sec) + datetime.timedelta(microseconds=nsec / 1000)
                    parsed_entries.append({
                        "timestamp": timestamp,
                        "pid": pid,
                        "tid": tid,
                        "level": "N/A", # No priority info available in payload
                        "tag": "N/A",   # No tag info available
                        "message": ""   # No message content
                    })
                    continue # Move to the next entry

                # 3. Read the payload: prio, tag, message
                payload = f.read(payload_len)
                if len(payload) < payload_len:
                    print(f"Error: Incomplete payload at offset {current_offset + MIN_HEADER_SIZE}. Expected {payload_len} bytes, got {len(payload)}. Stopping.", file=sys.stderr)
                    break # Stop parsing due to incomplete payload
                
                try:
                    # `prio` (uint8_t): First byte of the payload.
                    prio = payload[0]
                    log_level = LOG_LEVELS.get(prio, str(prio)) # Map to char or use number if unknown

                    # `tag` (null-terminated string): Starts after prio.
                    tag_end_idx = -1
                    try:
                        # Search for the first null byte after the prio byte.
                        tag_end_idx = payload.index(b'\x00', 1) 
                    except ValueError:
                        # If no null terminator for tag, behavior can be ambiguous.
                        # Current strategy: use a placeholder tag and log a warning.
                        # Message parsing will then effectively start after the prio byte.
                        print(f"Warning: No null terminator for tag in payload at offset {current_offset + MIN_HEADER_SIZE}. PID: {pid}. Tag will be 'ErrorTag'.", file=sys.stderr)
                        tag = "ErrorTag" 
                        message_start_idx = 1 # Message starts after prio if tag parsing fails
                    else:
                        tag = payload[1:tag_end_idx].decode('utf-8', errors='replace')
                        message_start_idx = tag_end_idx + 1 # Message starts after tag's null terminator

                    # `message` (null-terminated string): Starts after tag and its null terminator.
                    message_bytes = payload[message_start_idx:]
                    
                    # Remove trailing null bytes from the message, if any.
                    effective_message_end = len(message_bytes)
                    while effective_message_end > 0 and message_bytes[effective_message_end-1] == 0:
                        effective_message_end -= 1
                    message = message_bytes[:effective_message_end].decode('utf-8', errors='replace')

                    timestamp = datetime.datetime.fromtimestamp(sec) + datetime.timedelta(microseconds=nsec / 1000)

                    parsed_entries.append({
                        "timestamp": timestamp,
                        "pid": pid,
                        "tid": tid,
                        "level": log_level,
                        "tag": tag,
                        "message": message
                    })

                except IndexError:
                    # This can happen if payload_len was positive but too small for prio.
                    print(f"Warning: Payload too short to extract prio/tag/message at offset {current_offset + MIN_HEADER_SIZE}. Payload length: {payload_len}. Skipping entry.", file=sys.stderr)
                except Exception as e:
                    # Catch other errors during payload parsing (e.g., decoding errors if not UTF-8).
                    print(f"Error parsing payload contents at offset {current_offset + MIN_HEADER_SIZE}: {e}. Payload length: {payload_len}. Skipping entry.", file=sys.stderr)
                    
    except FileNotFoundError:
        # Raised by open() if filepath is a string and file doesn't exist.
        # This will be caught by main for user-facing error, but re-raise if called directly.
        if is_file_path: # Only print/raise if we were the ones trying to open it.
            # print(f"Error: File not found at {filepath}", file=sys.stderr) # Handled in main
            raise 
        else: # If a bad file-like object was passed, it might raise other errors caught by generic Exception.
            print(f"An unexpected error occurred with the provided file-like object: {e}", file=sys.stderr)
            return parsed_entries
    except IOError as e:
        # Raised by open() or f.read() for various I/O problems.
        if is_file_path:
            # print(f"Error: IO error opening or reading file {filepath}. Reason: {e}", file=sys.stderr) # Handled in main
            raise
        else:
            print(f"An IO error occurred with the provided file-like object: {e}", file=sys.stderr)
            return parsed_entries
    except Exception as e:
        # Catch any other unexpected errors during file processing.
        if file_opened_successfully:
             # Error happened after file was opened, possibly during a read or tell operation.
             current_pos_str = "unknown position"
             try:
                 current_pos_str = str(f.tell())
             except: # If f.tell() itself fails
                 pass
             print(f"An unexpected error occurred while processing file {filepath} at offset {current_pos_str}: {e}", file=sys.stderr)
        else:
             # Error happened before or during file opening.
             print(f"An unexpected error occurred before file {filepath} could be opened or processed: {e}", file=sys.stderr)
        return parsed_entries # Return what we have, if any

    return parsed_entries

if __name__ == "__main__":
    # Setup command-line argument parsing
    parser = argparse.ArgumentParser(
        description="Parse Android pmsg log files. Outputs in logcat -L like format.",
        epilog="Note: Assumes a common userspace logger entry structure. May not work for all pmsg file types."
    )
    parser.add_argument("pmsg_file", help="Path to the pmsg log file to be parsed.")
    parser.add_argument(
        "-v", "--verbose", 
        action="store_true", 
        help="Enable verbose output to stderr, including detailed parsing information and warnings."
    )

    args = parser.parse_args()
    
    log_entries = []
    file_processed_successfully = False # Tracks if parse_pmsg_file was called and returned (even if with partial data)
    is_empty_file = False

    try:
        # Preliminary check: if the file exists and is empty.
        if not os.path.exists(args.pmsg_file):
            print(f"Error: File not found at '{args.pmsg_file}'.", file=sys.stderr)
            sys.exit(1)
        if os.path.getsize(args.pmsg_file) == 0:
            is_empty_file = True
        else:
            if args.verbose:
                print(f"Verbose: Attempting to parse pmsg file: {args.pmsg_file}", file=sys.stderr)
            
            # Call the main parsing function
            log_entries = parse_pmsg_file(args.pmsg_file, args.verbose)
            file_processed_successfully = True # Set true if parse_pmsg_file completes (even if it found no entries or partial)
            
            # If log_entries is empty after a successful processing attempt, it implies no valid entries were found
            # (distinct from file I/O errors which are caught below).
            # Errors during parsing that cause early exit from parse_pmsg_file would have printed to stderr.

    except FileNotFoundError: # Should be caught by os.path.exists, but as a fallback.
        print(f"Error: Cannot open file '{args.pmsg_file}'. File not found.", file=sys.stderr)
        sys.exit(1)
    except IOError as e: # Catches errors from open() or read/write operations if not caught by parse_pmsg_file
        print(f"Error: Cannot open or read file '{args.pmsg_file}'. Reason: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e: # Catch-all for other unexpected errors during setup or if parse_pmsg_file re-raises
        print(f"An critical unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    # Output results or messages based on parsing outcome
    if is_empty_file:
        print("File is empty.") # Printed to stdout as it's a status, not an error.
        sys.exit(0)
    elif not log_entries and file_processed_successfully:
        # parse_pmsg_file ran, no exceptions were thrown from it back to main, but it returned an empty list.
        # This means either the file had no parsable entries (e.g., all padding, or all malformed entries that were skipped/errored out within the func).
        # Specific errors from parse_pmsg_file would have already gone to stderr.
        print("File contains no valid log entries or only padding that could be successfully parsed.") # Printed to stdout.
    elif log_entries:
        # Print successfully parsed log entries to stdout
        for entry in log_entries:
            ts = entry['timestamp']
            # Format timestamp: MM-DD HH:MM:SS.mmm
            formatted_ts = f"{ts.strftime('%m-%d %H:%M:%S')}.{ts.microsecond // 1000:03d}"
            
            # Format PID and TID to be right-justified (width of 5 characters)
            pid_str = f"{entry['pid']:>5}"
            tid_str = f"{entry['tid']:>5}"
            
            level_char = entry['level'] 
            # Special formatting for entries that were header-only (no payload)
            if entry['level'] == "N/A" and entry['tag'] == "N/A" and entry['message'] == "":
                 level_char = "?" # Indicate unknown level for header-only entries
                 tag_str = ""     # No tag
                 message_str = "<No payload>" # Indicate no message content
            else:
                tag_str = entry['tag']
                message_str = entry['message']
            
            # Output in logcat -L like format
            print(f"{formatted_ts}  {pid_str}  {tid_str} {level_char} {tag_str}: {message_str}")
    
    # If log_entries is empty AND file_processed_successfully was false, 
    # it means an exception occurred (FileNotFound, IOError, etc.) and was handled above,
    # printing an error to stderr and exiting. No further stdout message is needed here.
