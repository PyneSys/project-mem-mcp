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
This MCP is for storing and retrieving project information to/from an English(!) memory file, named
`{MEMORY_FILE}` in the project directory.

The memory file should store comprehensive information about the project. It should include thorough context
and details that help both humans and AI agents understand the project deeply. The memory should contain
detailed descriptions, code structures, architectural decisions, ongoing tasks, future plans, discovered insights,
challenges, references to important files, and other project resources. Include URLs, design patterns, and
technical decisions with reasoning when relevant.

Rules:
- This must be read by `get_project_memory` tool in the beginning of the first request of every conversation
  if the conversation is about a project and a full project path is provided.
- At the end of every of your answers the project memory must be updated using the `update_project_memory`
  or `set_project_memory` tool if any relevant changes were made to the project or any useful information
  was discovered or discussed.
- The `set_project_memory` tool must be used to set the whole project memory if `update_project_memory`
  failed or there is no project memory yet.
- Never store any sensitive information in the memory file, e.g. personal information, company
  information, passwords, access tokens, email addresses, etc!
- The memory file **must be in English**! Any non-English text in the memory file is considered a critical error!
- While thoroughness is encouraged, avoid excessive verbosity or redundancy. The memory file should not
  exceed practical limits (typically around 50-100KB or equivalent to ~10-20 pages of text).
- Remove information that is proven wrong or becomes obsolete.
- If the user talks about "memory" or "project memory", you should use the tools of this MCP.
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
    project_path: str = Field(description="The full path to the project directory")
) -> str:
    """
    Get the whole project memory for the given project path in Markdown format.
    This must be used in the beginning of the first request of every conversation.

    The memory file contains vital information about the project such as descriptions,
    ongoing tasks, references to important files, and other project resources.

    :return: The project memory content in Markdown format
    :raises FileNotFoundError: If the project path doesn't exist or MEMORY.md is missing
    :raises PermissionError: If the project path is not in allowed directories
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
    project_path: str = Field(description="The full path to the project directory"),
    project_info: str = Field(description="Complete project information in Markdown format")
):
    """
    Set the whole project memory for the given project path in Markdown format.

    Use this tool when:
    - Creating a memory file for a new project
    - Completely replacing an existing memory file
    - When `update_project_memory` fails to apply patches
    - When extensive reorganization of the memory content is needed

    Guidelines for content:
    - The project memory file **must be in English**! Any non-English text in the memory file is considered a critical error!
    - Should be detailed and comprehensive to support effective project understanding
    - Store rich context including architectural decisions, code patterns, and technical reasoning
    - Include thorough documentation of project components, workflows, and interfaces
    - Recommended to maintain structured sections for easier navigation
    - Aim for practical size limits (typically around 50-100KB or equivalent to ~10-20 pages of text)
    - Remove information that is proven wrong or becomes obsolete

    :raises FileNotFoundError: If the project path doesn't exist
    :raises PermissionError: If the project path is not in allowed directories
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

    This function performs comprehensive validation of the patch format:
    1. Checks for balanced markers (SEARCH, separator, REPLACE)
    2. Verifies correct marker sequence
    3. Detects nested markers inside blocks (which would cause errors)

    All these checks happen before actual parsing to provide clear error
    messages and prevent corrupted patches from being applied.

    :param patch_content: The raw patch content to validate
    :raises ValueError: With detailed message if any validation fails
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

    This function first validates the block integrity, then extracts all
    search-replace pairs using either regex or line-by-line parsing as fallback.
    It also checks that search and replace texts don't contain markers themselves,
    which could lead to corrupted files.

    :param patch_content: Raw patch content with SEARCH/REPLACE blocks
    :return: List of tuples (search_text, replace_text)
    :raises ValueError: If patch format is invalid or contains nested markers
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
    project_path: str = Field(description="The full path to the project directory"),
    patch_content: str = Field(description="Block-based patch content with SEARCH/REPLACE markers")
):
    """
    Update the project memory by applying a block-based patch to the memory file. The language of the memory file
    is English! Any non-English text in the memory file is considered a critical error!

    Required block format:
    ```
    <<<<<<< SEARCH
    Text to find in the memory file
    =======
    Text to replace it with
    >>>>>>> REPLACE
    ```

    You can include multiple search-replace blocks in a single request:
    ```
    <<<<<<< SEARCH
    First text to find
    =======
    First replacement
    >>>>>>> REPLACE
    <<<<<<< SEARCH
    Second text to find
    =======
    Second replacement
    >>>>>>> REPLACE
    ```

    This tool verifies that each search text appears exactly once in the file to ensure
    the correct section is modified. If a search text appears multiple times or isn't
    found, it will report an error.

    :return: Success message with number of blocks applied
    :raises FileNotFoundError: If the project path or memory file doesn't exist
    :raises ValueError: If patch format is invalid or search text isn't unique
    :raises RuntimeError: If patch application fails for any reason
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
