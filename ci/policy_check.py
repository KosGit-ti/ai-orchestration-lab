"""汎用ポリシーチェッカー。

プロジェクト固有の禁止パターンと秘密情報パターンをチェックする。

使い方:
    python ci/policy_check.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

# スキャン対象ディレクトリ
SCAN_DIRS = [
    REPO_ROOT / "src",
    REPO_ROOT / "tests",
    REPO_ROOT / "scripts",
    REPO_ROOT / ".github",
    REPO_ROOT / "configs",
    REPO_ROOT / "ci",
    REPO_ROOT / "experiments",
]

# スキャン対象の拡張子
SCAN_EXTENSIONS = {
    ".py",
    ".ts",
    ".js",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
    ".md",
    ".json",
    ".sh",
}

# スキップするディレクトリ名
SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
}

# ホワイトリスト
SKIP_FILES: set[str] = {
    "ci/policy_check.py",
}

# ---------------------------------------------------------------------------
# 禁止パターン
# ---------------------------------------------------------------------------

FORBIDDEN_IMPORT_PATTERNS: list[str] = []

# 秘密情報パターン
SECRET_PATTERNS: list[str] = [
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN\s+(RSA|DSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----",
    r"ghp_[A-Za-z0-9_]{36,}",
    r"sk-[A-Za-z0-9]{32,}",
    r"sk-ant-api03-[A-Za-z0-9\-_]{20,}",
    r"sk-proj-[A-Za-z0-9]{20,}",
    r"Bearer\s+[A-Za-z0-9\-._~+/]{20,}=*",
    r"password\s*=\s*[\"'][^\"\']+[\"']",
]

# URL パターン
URL_PATTERN = r"https?://[^\s\"')\]>]+"

URL_ALLOWLIST_PATTERNS: list[str] = [
    r"example\.com",
    r"github\.com",
    r"pypi\.org",
    r"docs\.python\.org",
    r"astral\.sh",
    r"opentelemetry\.io",
    r"json-schema\.org",
]

FORBIDDEN_PATTERNS: list[str] = []


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def git_ls_files() -> list[Path]:
    """git 管理対象のファイル一覧を取得する。"""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=True,
        )
        return [REPO_ROOT / line for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def should_skip(path: Path) -> bool:
    """スキップ対象のディレクトリに含まれるか判定する。"""
    parts = set(path.parts)
    return any(name in parts for name in SKIP_DIR_NAMES)


def is_skipped_file(path: Path) -> bool:
    """ホワイトリストに登録されたファイルか判定する。"""
    rel = path.relative_to(REPO_ROOT).as_posix()
    return rel in SKIP_FILES


def read_text_safely(path: Path) -> str | None:
    """ファイルを安全に読み込む。"""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return None


def is_url_allowlisted(line: str) -> bool:
    """URL がホワイトリストに該当するか判定する。"""
    return any(re.search(pat, line) for pat in URL_ALLOWLIST_PATTERNS)


def is_code_file(path: Path) -> bool:
    """コード系ファイルか判定する。"""
    return path.suffix.lower() in {".py", ".ts", ".js"}


def is_comment_line(line: str, suffix: str) -> bool:
    """コメント行か判定する。"""
    stripped = line.lstrip()
    return suffix in {".py", ".ts", ".js"} and (
        stripped.startswith("#") or stripped.startswith("//")
    )


# ---------------------------------------------------------------------------
# スキャン
# ---------------------------------------------------------------------------


def scan_file(path: Path) -> list[str]:
    """1 ファイルをスキャンし、問題を返す。"""
    issues: list[str] = []
    text = read_text_safely(path)
    if text is None:
        return issues

    rel = path.relative_to(REPO_ROOT)
    suffix = path.suffix.lower()

    # 禁止 import（コードファイルのみ）
    if is_code_file(path) and FORBIDDEN_IMPORT_PATTERNS:
        for pat in FORBIDDEN_IMPORT_PATTERNS:
            if re.search(pat, text, flags=re.MULTILINE):
                issues.append(f"禁止操作疑い: 禁止import検出 ({pat}) in {rel}")

    # URL 直書き（コードファイルのみ — コメント行は除外）
    if is_code_file(path):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if is_comment_line(line, suffix):
                continue
            if re.search(URL_PATTERN, line) and not is_url_allowlisted(line):
                issues.append(f"外部接続疑い: URL直書き検出 in {rel}:{lineno}")

    # 秘密情報（全ファイル種別）
    for pat in SECRET_PATTERNS:
        if re.search(pat, text):
            issues.append(f"秘密情報疑い: パターン検出 ({pat}) in {rel}")

    # プロジェクト固有の禁止パターン
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, text, flags=re.MULTILINE):
            issues.append(f"禁止パターン検出: ({pat}) in {rel}")

    return issues


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------


def main() -> int:
    """ポリシーチェックを実行し、違反があれば非ゼロで終了する。"""
    issues: list[str] = []

    # .env が git 管理されていないことを確認
    tracked_files = {p.relative_to(REPO_ROOT).as_posix() for p in git_ls_files()}
    if ".env" in tracked_files:
        issues.append(
            "禁止: .env がリポジトリにコミットされています。削除し、gitignore 対象にしてください。"
        )

    # 対象ファイルのスキャン
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if should_skip(path):
                continue
            if is_skipped_file(path):
                continue
            if path.suffix.lower() not in SCAN_EXTENSIONS:
                continue
            issues.extend(scan_file(path))

    if issues:
        print("[policy_check] FAILED")
        for i, msg in enumerate(issues, start=1):
            print(f"  {i}. {msg}")
        return 1

    print("[policy_check] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
