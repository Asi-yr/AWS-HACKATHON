import re
import os

def split_json_file(input_file, output_dir, chunk_size=20):
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Read the file
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Use regex to validate JSON-like lines (starts with { and ends with })
    json_lines = [line for line in lines if re.match(r'^\s*\{.*\}\s*$', line)]

    # Split into chunks
    chunks = [json_lines[i:i+chunk_size] for i in range(0, len(json_lines), chunk_size)]

    # Write each chunk into a separate file
    for idx, chunk in enumerate(chunks, start=1):
        output_file = os.path.join(output_dir, f'transportation_routes_{idx}.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("[\n")
            f.write(",\n".join(chunk))
            f.write("\n]")
        print(f"Created {output_file} with {len(chunk)} lines")

# Example usage:
split_json_file("sakay_all_routes.json", ".", chunk_size=20)