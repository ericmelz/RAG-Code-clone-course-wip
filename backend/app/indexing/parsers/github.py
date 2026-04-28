from urllib.parse import urlparse
import httpx, os
import ast
from io import BytesIO
from zipfile import ZipFile
import logging

from app.indexing.schemas import File
from app.indexing.documents import CodeElement


BASE_URL = 'https://codeload.github.com'
MAX_FILE_BYTES = 1_000_000  # 1 MB cap per file
DEFAULT_EXTS = {".py", ".md"}


class GitHubParser:
    """Parser for extracting and processing code from GitHub repositories.

    Downloads a repository as a ZIP and parses its contents into CodeElement
    objects suitable for indexing and retrieval.

    Attributes:
        owner (str): GitHub repository owner/organization name
        repo (str): Repository name
        ref (str | None): Git reference (branch, tag, or commit), None for default branch

    Example:
        parser = GitHubParser("https://github.com/owner/repo/tree/main")
        code_elements = parser.parse()
    """

    def __init__(self, github_url):
        self.owner, self.repo, self.ref = self.parse_url(github_url)

    def parse_url(self, url: str) -> tuple[str, str, str | None]:
        """Parse a GitHub URL to extract owner, repository name, and optional reference."""
        try:
            p = urlparse(url)
        except Exception as e:
            logging.error(f"Error parsing the URL: {str(e)}")
            raise e

        if p.netloc.lower() != "github.com":
            raise ValueError("Only github.com URLs are supported")

        parts = [x for x in p.path.strip("/").split("/") if x]
        if len(parts) < 2:
            raise ValueError("URL must be of the form github.com/<owner>/<repo>[/...]")

        owner, repo = parts[0], parts[1].removesuffix(".git")
        ref = None
        if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
            ref = parts[3]
        return owner, repo, ref

    def fetch_repo_zip(self, timeout: float = 60.0) -> bytes:
        """Download this GitHub repository as a ZIP file."""
        refs_to_try = [self.ref] if self.ref else ["main", "master"]
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            for r in refs_to_try:
                url = f"{BASE_URL}/{self.owner}/{self.repo}/zip/{r}"
                resp = client.get(url)
                if resp.status_code == 200:
                    return resp.content
        raise ConnectionError("Could not download ZIP (ref not found or repo private).")

    def get_files_from_zip(self, zip_bytes: bytes, max_bytes: int = MAX_FILE_BYTES) -> list[File]:
        """Extract and process files from a ZIP archive."""
        files = []
        with ZipFile(BytesIO(zip_bytes)) as zip_file:
            prefix = os.path.commonpath([i.filename for i in zip_file.infolist()]) + "/"
            for info in zip_file.infolist():
                if info.is_dir() or info.file_size > max_bytes:
                    continue
                inner = info.filename
                if not inner.startswith(prefix):
                    continue
                rel = inner[len(prefix):]
                ext = os.path.splitext(rel)[1].lower()
                if ext not in DEFAULT_EXTS:
                    continue
                with zip_file.open(info) as f:
                    raw = f.read()
                try:
                    text = raw.decode("utf-8").strip()
                except UnicodeDecodeError:
                    text = raw.decode("latin-1", errors="replace").strip()
                files.append(File(content=text, path=rel, extension=ext))
        return files

    def parse_code(self, file: File, max_lines_per_elem: int = 150) -> list[CodeElement]:
        """Parse Python code into CodeElement objects with intelligent AST-based chunking."""
        try:
            tree = ast.parse(file.content)
        except Exception:
            return []

        source = file.path
        extension = file.extension
        lines = file.content.splitlines()
        lines = [line[:200] + '\n' for line in lines]

        def slice_node(node: ast.AST) -> list[str]:
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            end = getattr(node, "end_lineno", node.lineno)
            return lines[start - 1:end]

        def split_class(node: ast.ClassDef) -> list[list[str]]:
            class_lines = slice_node(node)
            if len(class_lines) <= max_lines_per_elem:
                return [class_lines]
            class_parts = []
            part = [f'class {node.name}:\n']
            for sub_node in node.body:
                sub_node_lines = slice_node(sub_node)
                if len(part) + len(sub_node_lines) > max_lines_per_elem and len(part) > 1:
                    part.append('    ...\n')
                    class_parts.append(part)
                    part = [f'class {node.name}:\n    ...\n']
                part.extend(sub_node_lines)
            if len(part) > 1:
                class_parts.append(part)
            return class_parts

        headers: list[str] = []
        code_elements: list[CodeElement] = []
        previous_text: list[str] = []

        for node in tree.body:
            node_text = slice_node(node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if previous_text and (len(previous_text) + len(node_text)) > max_lines_per_elem:
                    code_elements.append(CodeElement(
                        text=''.join(previous_text).strip(),
                        source=source,
                        header=''.join(headers).strip() if headers else None,
                        extension=extension,
                    ))
                    previous_text = []
                previous_text = previous_text + ["\n"] + node_text if previous_text else node_text
            elif isinstance(node, ast.ClassDef):
                for part in split_class(node):
                    if previous_text and (len(previous_text) + len(part)) > max_lines_per_elem:
                        code_elements.append(CodeElement(
                            text=''.join(previous_text).strip(),
                            source=source,
                            header=''.join(headers).strip() if headers else None,
                            extension=extension,
                        ))
                        previous_text = []
                    previous_text = previous_text + ["\n"] + part if previous_text else part
            else:
                headers.extend(node_text)

        if previous_text:
            code_elements.append(CodeElement(
                text=''.join(previous_text).strip(),
                source=source,
                header=''.join(headers).strip() if headers else None,
                extension=extension,
            ))

        if not code_elements:
            code_elements.append(CodeElement(text=file.content.strip(), source=source, extension=extension))

        return code_elements

    def parse_markdown(self, file: File, min_lines_per_elem: int = 100, overlap_lines: int = 5) -> list[CodeElement]:
        """Parse Markdown content into overlapping CodeElement chunks."""
        source = file.path
        lines = file.content.splitlines(keepends=True)
        extension = file.extension
        num_lines = len(lines)

        overlap_lines = max(0, min(overlap_lines, min_lines_per_elem - 1))
        step = max(1, min_lines_per_elem - overlap_lines)

        chunks: list[CodeElement] = []
        for start in range(0, num_lines, step):
            end = start + min_lines_per_elem
            chunks.append(CodeElement(text="".join(lines[start:end]), source=source, extension=extension))
        return chunks

    def parse_repo(self) -> list[CodeElement]:
        """Parse the GitHub repository into CodeElement objects (Python + Markdown files)."""
        zip_bytes = self.fetch_repo_zip()
        files = self.get_files_from_zip(zip_bytes)
        code_elements = []
        for file in files:
            if file.extension == '.py':
                code_elements.extend(self.parse_code(file))
            if file.extension == '.md':
                code_elements.extend(self.parse_markdown(file))
        return code_elements

    def parse(self) -> list[CodeElement]:
        """Satisfy the BaseParser protocol. Delegates to parse_repo()."""
        return self.parse_repo()
