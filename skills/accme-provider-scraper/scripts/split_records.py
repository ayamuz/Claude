"""Split space-joined tilde-delimited records from get_page_text output.

When get_page_text reads multi-line content, it joins lines with spaces.
This script reconstructs individual records by counting tilde-separated fields.
Each record has exactly 16 fields (15 tildes), so we count fields and split
at the space boundary between the last field of one record and the first field
of the next.

Usage:
    python split_records.py <input_joined.txt> <output.txt> [append_mode]

    append_mode: 'a' to append, 'w' to overwrite (default: 'w')
"""
import sys

def split_by_tilde_count(text, num_fields=16):
    parts = text.split('~')
    records = []
    current_record = []

    for part in parts:
        current_record.append(part)
        if len(current_record) == num_fields:
            last_field = current_record[-1].strip()
            space_idx = last_field.find(' ')
            if space_idx > 0:
                this_id = last_field[:space_idx]
                next_name = last_field[space_idx+1:]
                current_record[-1] = this_id
                records.append('~'.join(current_record))
                current_record = [next_name]
            else:
                current_record[-1] = last_field
                records.append('~'.join(current_record))
                current_record = []

    if current_record:
        records.append('~'.join(current_record))

    return records

if __name__ == '__main__':
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else 'w'

    with open(input_file) as f:
        text = f.read().strip()

    records = split_by_tilde_count(text)

    with open(output_file, mode) as f:
        for r in records:
            f.write(r + '\n')

    print(f"{'Appended' if mode == 'a' else 'Wrote'} {len(records)} records to {output_file}")
    for i, r in enumerate(records[:3]):
        fields = r.split('~')
        print(f"  Rec {i}: {len(fields)} fields, name='{fields[0][:50]}', id='{fields[-1].strip()}'")
    if len(records) > 3:
        fields = records[-1].split('~')
        print(f"  Last rec: {len(fields)} fields, name='{fields[0][:50]}', id='{fields[-1].strip()}'")
