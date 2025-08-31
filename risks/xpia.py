"""
Run from the risks directory:
    uv run xpia.py -t streamable-http
"""

from mcp.server.fastmcp import FastMCP
import os
import argparse

mcp = FastMCP("xpia")


def _extract_text_from_pdf(abs_filepath: str) -> str:
  """Extract text from a PDF using pypdf with simple, clear handling."""
  try:
    from pypdf import PdfReader
  except Exception:
    return "Error: PDF support requires the 'pypdf' package. Install with: uv add pypdf"

  try:
    reader = PdfReader(abs_filepath)
    if getattr(reader, "is_encrypted", False):
      return "Error: Encrypted PDF is not supported."

    parts = []
    for i, page in enumerate(reader.pages):
      try:
        text = (page.extract_text() or "").strip()
      except Exception:
        text = ""
      if text:
        parts.append(f"--- Page {i+1} ---\n{text}")

    return "\n\n".join(parts) if parts else "Warning: No extractable text found in PDF."
  except FileNotFoundError:
    return f"Error: File not found: {abs_filepath}"
  except PermissionError:
    return f"Error: Permission denied for file: {abs_filepath}"
  except Exception as e:
    return f"Error reading PDF: {e}"


def _extract_text_from_docx(abs_filepath: str) -> str:
  """Extract text from a DOCX using python-docx with simple handling."""
  try:
    from docx import Document
  except Exception:
    return "Error: DOCX support requires the 'python-docx' package. Install with: uv add python-docx"

  try:
    doc = Document(abs_filepath)
    parts = []

    # Paragraphs
    for p in doc.paragraphs:
      t = p.text.strip()
      if t:
        parts.append(t)

    # Tables (best-effort)
    try:
      for table in doc.tables:
        for row in table.rows:
          row_text = [cell.text.strip()
                      for cell in row.cells if cell.text.strip()]
          if row_text:
            parts.append(" | ".join(row_text))
    except Exception:
      pass

    return "\n".join(parts) if parts else "Warning: No extractable text found in DOCX."
  except FileNotFoundError:
    return f"Error: File not found: {abs_filepath}"
  except PermissionError:
    return f"Error: Permission denied for file: {abs_filepath}"
  except Exception as e:
    return f"Error reading DOCX: {e}"


@mcp.tool()
def read_file(filepath: str) -> str:
  """Read the content of a local file (.txt, .pdf, or .docx) and return it as a string."""
  try:
    abs_filepath = os.path.abspath(filepath)
    base_dir = os.path.abspath(os.path.dirname(__file__))

    # Allow only files within the application directory or subdirectories
    if os.path.commonpath([abs_filepath, base_dir]) != base_dir:
      return "Error: Cannot access files outside the application directory for security reasons."

    ext = os.path.splitext(abs_filepath)[1].lower()
    if ext == ".pdf":
      return _extract_text_from_pdf(abs_filepath)
    elif ext == ".docx":
      return _extract_text_from_docx(abs_filepath)
    elif ext == ".txt":
      with open(abs_filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()
    else:
      return "Error: Unsupported file type. Only .txt, .pdf, and .docx are supported."

  except FileNotFoundError:
    return f"Error: File not found: {filepath}"
  except PermissionError:
    return f"Error: Permission denied for file: {filepath}"
  except Exception as e:
    return f"Error reading file: {e}"


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="XPIA")
  parser.add_argument(
      "--transport", "-t", choices=["stdio", "sse", "streamable-http"], default="stdio")
  args = parser.parse_args()
  mcp.run(transport=args.transport)
