#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

from fastmcp import FastMCP
from pydantic.fields import Field
import re

# No need for unidiff import anymore as we're using block-based patching

MEMORY_FILE = "MEMORY.md"


mcp = FastMCP(
    name="Project Memory MCP",
    instructions=f"""
This MCP is for storing and retrieving project information to/from an English memory file.
The memory file should store all information about the project in short and concise manner. It should be
good for humans and AI agents to catch up on the project status and progress quickly. Should contain descriptions,
ongoing tasks, tasks to do, references to files and other project resources, even URLs where to get more information.

The memory file is a Markdown file named `{MEMORY_FILE}` in the project directory.

Rules:
- This must be read by `get_project_memory` tool in the beginning of the first request of every conversation
  if the conversation is about a project and a full project path is provided.
- At the end of every answer the project memory must be updated using the `update_project_memory` tool.
- The `set_project_memory` tool must be used to set the whole project memory if `update_project_memory`
  failed or there is no project memory yet.
- Never store any sensitive information in the memory file, e.g. personal information, company
  information, passwords, access tokens, email addresses, etc.
- The memory file **must be in English**!
"""
)

allowed_directories = []


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def main():
    # Process command line arguments
    global allowed_directories
    parser = argparse.ArgumentParser(description="Project Memory MCP server")
    parser.add_argument(
        '--allowed-dir',
        action='append',
        dest='allowed_dirs',
        required=True,
        help='Allowed base directory for project paths (can be used multiple times)'
    )
    args = parser.parse_args()
    allowed_directories = [str(Path(d).resolve()) for d in args.allowed_dirs]

    if not allowed_directories:
        allowed_directories = [str(Path.home().resolve())]

    eprint(f"Allowed directories: {allowed_directories}")

    # Run the MCP server
    mcp.run()


if __name__ == "__main__":
    main()


#
# Tools
#

@mcp.tool()
def get_project_memory(
    project_path: str = Field(description="The path to the project")
) -> str:
    """
    Get the whole project memory for the given project path in Markdown format.
    This must be used in the beginning of the first request of every conversation.
    """
    pp = Path(project_path).resolve()

    # Check if the project path exists and is a directory
    if not pp.exists() or not pp.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist")
    # Check if it is inside one of the allowed directories
    if not any(str(pp).startswith(base) for base in allowed_directories):
        raise PermissionError(f"Project path {project_path} is not in allowed directories")

    with open(pp / MEMORY_FILE, "r") as f:
        return f.read()


@mcp.tool()
def set_project_memory(
    project_path: str = Field(description="The path to the project"),
    project_info: str = Field(description="The project information to set in Markdown format")
):
    """
    Set the whole project memory for the given project path in Markdown format.
    This should be used if the `update_project_memory` tool failed or there is no project memory yet.
    The project memory file **must be in English**!
    """
    pp = Path(project_path).resolve()
    if not pp.exists() or not pp.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist")
    if not any(str(pp).startswith(base) for base in allowed_directories):
        raise PermissionError(f"Project path {project_path} is not in allowed directories")

    with open(pp / MEMORY_FILE, "w") as f:
        f.write(project_info)


def validate_block_integrity(patch_content):
    """
    Validate the integrity of patch blocks before parsing.
    Checks for balanced markers and correct sequence.
    """
    # Check marker balance
    search_count = patch_content.count("<<<<<<< SEARCH")
    separator_count = patch_content.count("=======")
    replace_count = patch_content.count(">>>>>>> REPLACE")
    
    if not (search_count == separator_count == replace_count):
        raise ValueError(
            f"Malformed patch format: Unbalanced markers - "
            f"{search_count} SEARCH, {separator_count} separator, {replace_count} REPLACE markers"
        )

    # Check marker sequence
    markers = []
    for line in patch_content.splitlines():
        line = line.strip()
        if line in ["<<<<<<< SEARCH", "=======", ">>>>>>> REPLACE"]:
            markers.append(line)
    
    # Verify correct marker sequence (always SEARCH, SEPARATOR, REPLACE pattern)
    for i in range(0, len(markers), 3):
        if i+2 < len(markers):
            if markers[i] != "<<<<<<< SEARCH" or markers[i+1] != "=======" or markers[i+2] != ">>>>>>> REPLACE":
                raise ValueError(
                    f"Malformed patch format: Incorrect marker sequence at position {i}: "
                    f"Expected [SEARCH, SEPARATOR, REPLACE], got {markers[i:i+3]}"
                )
    
    # Check for nested markers in each block
    sections = patch_content.split("<<<<<<< SEARCH")
    for i, section in enumerate(sections[1:], 1):  # Skip first empty section
        if "<<<<<<< SEARCH" in section and section.find(">>>>>>> REPLACE") > section.find("<<<<<<< SEARCH"):
            raise ValueError(f"Malformed patch format: Nested SEARCH marker in block {i}")


def parse_search_replace_blocks(patch_content):
    """
    Parse multiple search-replace blocks from the patch content.
    Returns a list of tuples (search_text, replace_text).
    """
    # Define the markers
    search_marker = "<<<<<<< SEARCH"
    separator = "======="
    replace_marker = ">>>>>>> REPLACE"
    
    # First validate patch integrity
    validate_block_integrity(patch_content)

    # Use regex to extract all blocks
    pattern = f"{search_marker}\\n(.*?)\\n{separator}\\n(.*?)\\n{replace_marker}"
    matches = re.findall(pattern, patch_content, re.DOTALL)

    if not matches:
        # Try alternative parsing if regex fails
        blocks = []
        lines = patch_content.splitlines()
        i = 0
        while i < len(lines):
            if lines[i] == search_marker:
                search_start = i + 1
                separator_idx = -1
                replace_end = -1

                # Find the separator
                for j in range(search_start, len(lines)):
                    if lines[j] == separator:
                        separator_idx = j
                        break

                if separator_idx == -1:
                    raise ValueError("Invalid format: missing separator")

                # Find the replace marker
                for j in range(separator_idx + 1, len(lines)):
                    if lines[j] == replace_marker:
                        replace_end = j
                        break

                if replace_end == -1:
                    raise ValueError("Invalid format: missing replace marker")

                search_text = "\n".join(lines[search_start:separator_idx])
                replace_text = "\n".join(lines[separator_idx + 1:replace_end])
                
                # Check for markers in the search or replace text
                if any(marker in search_text for marker in [search_marker, separator, replace_marker]):
                    raise ValueError(f"Block {len(blocks)+1}: Search text contains patch markers")
                if any(marker in replace_text for marker in [search_marker, separator, replace_marker]):
                    raise ValueError(f"Block {len(blocks)+1}: Replace text contains patch markers")
                
                blocks.append((search_text, replace_text))

                i = replace_end + 1
            else:
                i += 1

        if blocks:
            return blocks
        else:
            raise ValueError("Invalid patch format. Expected block format with SEARCH/REPLACE markers.")

    # Check for markers in matched content
    for i, (search_text, replace_text) in enumerate(matches):
        if any(marker in search_text for marker in [search_marker, separator, replace_marker]):
            raise ValueError(f"Block {i+1}: Search text contains patch markers")
        if any(marker in replace_text for marker in [search_marker, separator, replace_marker]):
            raise ValueError(f"Block {i+1}: Replace text contains patch markers")

    return matches


@mcp.tool()
def update_project_memory(
    project_path: str = Field(description="The path to the project"),
    patch_content: str = Field(description="Unified diff/patch to apply to the project memory")
):
    """
    Update the project memory by applying a unified diff/patch to the memory file.

    :param project_path: The path to the project directory.
    :param patch_content: Unified diff/patch to apply.
    """
    project_dir = Path(project_path).resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project path {project_path} does not exist or is not a directory")
    memory_file = project_dir / MEMORY_FILE
    if not memory_file.exists():
        raise FileNotFoundError(
            f"Memory file does not exist at {memory_file}. Use `set_project_memory` to set the whole memory instead."
        )

    # Read the current file content
    with open(memory_file, 'r', encoding='utf-8') as f:
        original_content = f.read()

    try:
        # First, try to parse as block format
        try:
            # Parse multiple search-replace blocks
            blocks = parse_search_replace_blocks(patch_content)
            if blocks:
                eprint(f"Found {len(blocks)} search-replace blocks")

                # Apply each block sequentially
                current_content = original_content
                applied_blocks = 0

                for i, (search_text, replace_text) in enumerate(blocks):
                    eprint(f"Processing block {i+1}/{len(blocks)}")

                    # Check exact match count
                    count = current_content.count(search_text)

                    if count == 1:
                        # Exactly one match - perfect!
                        eprint(f"Block {i+1}: Found exactly one exact match")
                        current_content = current_content.replace(search_text, replace_text)
                        applied_blocks += 1
                    elif count > 1:
                        # Multiple matches - too ambiguous
                        raise ValueError(f"Block {i+1}: The search text appears {count} times in the file. "
                                        "Please provide more context to identify the specific occurrence.")
                    else:
                        # No match found
                        raise ValueError(f"Block {i+1}: Could not find the search text in the file. "
                                        "Please ensure the search text exactly matches the content in the file.")

                # Write the final content back to the file
                with open(memory_file, 'w', encoding='utf-8') as f:
                    f.write(current_content)

                return f"Successfully applied {applied_blocks} patch blocks to memory file"
        except Exception as block_error:
            # If block format parsing fails, log the error and try traditional patch format
            eprint(f"Block format parsing failed: {str(block_error)}")
            
            # If you still want to support traditional patches with whatthepatch or similar, add that code here
            # For now, we'll just raise the error from block parsing
            raise block_error
    
    except Exception as e:
        # If anything goes wrong, provide detailed error
        raise RuntimeError(f"Failed to apply patch: {str(e)}")
