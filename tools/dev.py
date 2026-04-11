#!/usr/bin/env python3
"""
dev.py — Unified development tool for CV Jekyll site

This script combines multiple development tasks:
  1. Setup: Ensures mise, Ruby 3.4.9, and gems are properly configured
  2. Serve: Start local Jekyll dev server with auto-reload
  3. Build: Clean build for testing/deployment
  4. Test:  Build + validate links with htmlproofer
  5. Check: Check for broken internal links in posts

Usage:
  ./tools/dev.py setup                    # Setup mise, Ruby, and gems
  ./tools/dev.py serve [--host HOST]     # Serve locally (default: 127.0.0.1)
  ./tools/dev.py build [--production]    # Build the site
  ./tools/dev.py test                    # Build + run htmlproofer
  ./tools/dev.py check [--dry-run] [--htmlproofer]  # Check internal links
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "_posts"
DRAFTS_DIR = REPO_ROOT / "_drafts"
SITE_DIR = REPO_ROOT / "_site"
CACHE_DIR = REPO_ROOT / ".jekyll-cache"
MISE_TOML = REPO_ROOT / "mise.toml"
GEMFILE = REPO_ROOT / "Gemfile"

# Expected Ruby version from mise.toml
EXPECTED_RUBY_VERSION = "3.4.9"

# Matches Markdown links whose href starts with /posts/
INTERNAL_LINK_RE = re.compile(r"\[([^\]]+)\]\(/posts/([^/)]+)/?[^)]*\)")


# ── Helpers ──────────────────────────────────────────────────────────────────


def print_header(text: str) -> None:
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def run(
    cmd: list[str], check: bool = True, show_output: bool = True
) -> subprocess.CompletedProcess:
    """Run a shell command, streaming output to the terminal."""
    if show_output:
        print(f"\n$ {' '.join(cmd)}")
    return subprocess.run(
        cmd, cwd=REPO_ROOT, check=check, capture_output=not show_output
    )


def run_with_mise(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command with mise environment activated."""
    # Prepend mise activation and source bashrc
    shell_cmd = f'eval "$(mise activate bash)" && {" ".join(cmd)}'
    return subprocess.run(
        ["bash", "-c", shell_cmd],
        cwd=REPO_ROOT,
        check=check,
    )


def get_ruby_version(with_mise: bool = False) -> str:
    """Get the current active Ruby version."""
    if with_mise:
        cmd = ["bash", "-c", 'eval "$(mise activate bash)" && ruby --version']
    else:
        cmd = ["ruby", "--version"]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        return "unknown"
    # Parse: ruby 3.4.9 (2026-03-11 revision 76cca827ab) +PRISM [x86_64-linux]
    match = re.search(r"ruby\s+([\d.]+)", result.stdout)
    return match.group(1) if match else "unknown"


def verify_mise_installed() -> bool:
    """Check if mise is installed."""
    result = subprocess.run(
        ["which", "mise"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def extract_ruby_from_mise_toml() -> str:
    """Extract ruby version from mise.toml."""
    if not MISE_TOML.exists():
        return "unknown"
    content = MISE_TOML.read_text()
    match = re.search(r'ruby\s*=\s*["\']?([\d.]+)', content)
    return match.group(1) if match else "unknown"


# ── Setup ────────────────────────────────────────────────────────────────────


def cmd_setup() -> None:
    """Setup: Ensure mise, Ruby, and gems are properly configured."""
    print_header("SETUP: Configuring Development Environment")

    # Check mise installation
    print("\n1. Checking mise installation...")
    if not verify_mise_installed():
        print("   ✗ mise is not installed.")
        print("   Please install from: https://mise.jq.rs/getting-started/")
        sys.exit(1)
    print("   ✓ mise is installed")

    # Check Ruby version in mise.toml
    print("\n2. Checking mise.toml Ruby version...")
    toml_ruby = extract_ruby_from_mise_toml()
    print(f"   mise.toml specifies Ruby {toml_ruby}")
    if toml_ruby != EXPECTED_RUBY_VERSION:
        print(f"   ⚠ Warning: Expected {EXPECTED_RUBY_VERSION}")

    # Install tools via mise
    print("\n3. Installing/updating tools via mise...")
    run(["mise", "install"])

    # Check active Ruby version
    print("\n4. Verifying Ruby version...")
    result = subprocess.run(
        ["bash", "-c", 'eval "$(mise activate bash)" && ruby --version'],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    print(f"   {result.stdout.strip()}")
    active_ruby = get_ruby_version()
    if active_ruby != EXPECTED_RUBY_VERSION:
        print(
            f"   ⚠ Warning: Active Ruby {active_ruby} != expected {EXPECTED_RUBY_VERSION}"
        )
        print('   Try: eval "$(mise activate bash)"')

    # Install/update gems
    print("\n5. Installing/updating gems...")
    run_with_mise(["bundle", "install"])

    print("\n✓ Setup complete!\n")


# ── Serve ────────────────────────────────────────────────────────────────────


def cmd_serve(args) -> None:
    """Serve: Start local Jekyll dev server."""
    print_header("SERVE: Starting Jekyll Development Server")

    # Verify setup
    print("\n1. Verifying environment...")
    active_ruby = get_ruby_version(with_mise=True)
    print(f"   Ruby version: {active_ruby}")
    if active_ruby != EXPECTED_RUBY_VERSION:
        print(f"   ✗ Ruby version mismatch (expected {EXPECTED_RUBY_VERSION})")
        print("   Run './tools/dev.py setup' first")
        sys.exit(1)
    print("   ✓ Environment OK")

    # Build command
    host = args.host or "127.0.0.1"
    print(f"\n2. Starting Jekyll on {host}:4000...")
    print("   (Press Ctrl+C to stop)")

    cmd = ["bundle", "exec", "jekyll", "serve", "-l", "-H", host]

    # Check if running in Docker
    try:
        with open("/proc/1/cgroup") as f:
            if "docker" in f.read():
                cmd.append("--force_polling")
    except (FileNotFoundError, OSError):
        pass

    print(f"\n$ {' '.join(cmd)}\n")
    try:
        run_with_mise(cmd)
    except KeyboardInterrupt:
        print("\n\nServer stopped.")


# ── Build ────────────────────────────────────────────────────────────────────


def cmd_build(args) -> None:
    """Build: Clean build for testing/deployment."""
    print_header("BUILD: Creating Site Build")

    # Verify setup
    print("\n1. Verifying environment...")
    active_ruby = get_ruby_version(with_mise=True)
    if active_ruby != EXPECTED_RUBY_VERSION:
        print(f"   ✗ Ruby version mismatch (expected {EXPECTED_RUBY_VERSION})")
        print("   Run './tools/dev.py setup' first")
        sys.exit(1)
    print("   ✓ Environment OK")

    # Clean
    print("\n2. Cleaning previous build...")
    for d in (CACHE_DIR, SITE_DIR):
        if d.exists():
            shutil.rmtree(d)
            print(f"   Removed {d.relative_to(REPO_ROOT)}/")

    # Build
    print("\n3. Building site...")
    env = "production" if args.production else "development"
    cmd = ["bundle", "exec", "jekyll", "build"]
    if args.production:
        env_cmd = f"JEKYLL_ENV=production {' '.join(cmd)}"
        subprocess.run(
            ["bash", "-c", f'eval "$(mise activate bash)" && {env_cmd}'],
            cwd=REPO_ROOT,
            check=True,
        )
    else:
        run_with_mise(cmd)

    print(f"\n✓ Build complete!")
    print(f"   Output: {SITE_DIR.relative_to(REPO_ROOT)}/")


# ── Test ─────────────────────────────────────────────────────────────────────


def cmd_test(args) -> None:
    """Test: Build + validate links with htmlproofer."""
    print_header("TEST: Building and Validating Site")

    # Verify setup
    print("\n1. Verifying environment...")
    active_ruby = get_ruby_version(with_mise=True)
    if active_ruby != EXPECTED_RUBY_VERSION:
        print(f"   ✗ Ruby version mismatch (expected {EXPECTED_RUBY_VERSION})")
        print("   Run './tools/dev.py setup' first")
        sys.exit(1)
    print("   ✓ Environment OK")

    # Build
    print("\n2. Building site in production mode...")
    for d in (CACHE_DIR, SITE_DIR):
        if d.exists():
            shutil.rmtree(d)

    env_cmd = "JEKYLL_ENV=production bundle exec jekyll build"
    subprocess.run(
        ["bash", "-c", f'eval "$(mise activate bash)" && {env_cmd}'],
        cwd=REPO_ROOT,
        check=True,
    )

    # Test with htmlproofer
    print("\n3. Running htmlproofer...")
    cmd = [
        "bundle",
        "exec",
        "htmlproofer",
        str(SITE_DIR),
        "--disable-external",
        "--ignore-urls",
        "/^http:\\/\\/127\\.0\\.0\\.1/,"
        "/^http:\\/\\/0\\.0\\.0\\.0/,"
        "/^http:\\/\\/localhost/",
    ]
    result = subprocess.run(
        ["bash", "-c", f'eval "$(mise activate bash)" && {" ".join(cmd)}'],
        cwd=REPO_ROOT,
        check=False,
    )

    if result.returncode == 0:
        print("\n✓ All tests passed! Site is ready to deploy.")
    else:
        print("\n✗ Tests failed (see output above).")
        sys.exit(1)
    print("   ✓ Environment OK")

    # Build
    print("\n2. Building site in production mode...")
    for d in (CACHE_DIR, SITE_DIR):
        if d.exists():
            shutil.rmtree(d)

    env_cmd = "JEKYLL_ENV=production bundle exec jekyll build"
    subprocess.run(
        ["bash", "-c", f'eval "$(mise activate bash)" && {env_cmd}'],
        cwd=REPO_ROOT,
        check=True,
    )

    # Test with htmlproofer
    print("\n3. Running htmlproofer...")
    cmd = [
        "bundle",
        "exec",
        "htmlproofer",
        str(SITE_DIR),
        "--disable-external",
        "--ignore-urls",
        "/^http:\\/\\/127\\.0\\.0\\.1/,"
        "/^http:\\/\\/0\\.0\\.0\\.0/,"
        "/^http:\\/\\/localhost/",
    ]
    result = subprocess.run(
        ["bash", "-c", f'eval "$(mise activate bash)" && {" ".join(cmd)}'],
        cwd=REPO_ROOT,
        check=False,
    )

    if result.returncode == 0:
        print("\n✓ All tests passed! Site is ready to deploy.")
    else:
        print("\n✗ Tests failed (see output above).")
        sys.exit(1)


# ── Check ────────────────────────────────────────────────────────────────────


def slug_from_filename(filename: str) -> str:
    """Extract Jekyll slug from filename: 2026-02-15-rust-on-esp32.md → rust-on-esp32"""
    name = Path(filename).stem
    name = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name)
    return name


def collect_slugs(directory: Path) -> dict[str, Path]:
    """Return {slug: filepath} for all .md files in a directory."""
    slugs = {}
    if directory.is_dir():
        for f in directory.glob("*.md"):
            slugs[slug_from_filename(f.name)] = f
    return slugs


def find_and_fix_broken_links(
    published: dict[str, Path],
    drafts: dict[str, Path],
    dry_run: bool,
) -> list[tuple[Path, str, str, str]]:
    """Scan published posts for links to unpublished slugs."""
    report = []

    for post_path in POSTS_DIR.glob("*.md"):
        original = post_path.read_text(encoding="utf-8")
        updated = original

        for match in INTERNAL_LINK_RE.finditer(original):
            label = match.group(1)
            slug = match.group(2)
            full = match.group(0)

            if slug in published:
                continue

            status = "draft" if slug in drafts else "unknown"

            replacement = f"{label} *(coming soon)*"
            updated = updated.replace(full, replacement, 1)
            report.append((post_path, label, slug, status))

            action = "[dry-run]" if dry_run else "[fixed]"
            print(
                f"  {action} {post_path.name}\n"
                f"           link : {full}\n"
                f"           →    : {replacement}\n"
                f"           slug is a {'draft' if status == 'draft' else 'UNKNOWN post'}\n"
            )

        if updated != original and not dry_run:
            post_path.write_text(updated, encoding="utf-8")

    return report


def cmd_check(args) -> None:
    """Check: Find and fix broken internal links."""
    print_header("CHECK: Analyzing Internal Links")

    published = collect_slugs(POSTS_DIR)
    drafts = collect_slugs(DRAFTS_DIR)

    print(f"\nPublished posts : {len(published)}")
    print(f"Drafts          : {len(drafts)}")

    print("\n── Checking internal /posts/ links in published posts ──\n")
    issues = find_and_fix_broken_links(published, drafts, dry_run=args.dry_run)

    if not issues:
        print("  ✓ No broken internal links found.")
    else:
        verb = "would be" if args.dry_run else "were"
        print(
            f"\n  {len(issues)} broken link(s) {verb} {'flagged' if args.dry_run else 'fixed'}."
        )
        if args.dry_run:
            print("  Re-run without --dry-run to apply fixes.")

    if args.htmlproofer:
        print("\n4. Running htmlproofer...")
        build_args = argparse.Namespace(production=True)
        cmd_build(build_args)

        cmd = [
            "bundle",
            "exec",
            "htmlproofer",
            str(SITE_DIR),
            "--disable-external",
            "--ignore-urls",
            "/^http:\\/\\/127\\.0\\.0\\.1/,"
            "/^http:\\/\\/0\\.0\\.0\\.0/,"
            "/^http:\\/\\/localhost/",
        ]
        result = subprocess.run(
            ["bash", "-c", f'eval "$(mise activate bash)" && {" ".join(cmd)}'],
            cwd=REPO_ROOT,
            check=False,
        )
        if result.returncode == 0:
            print("\n  ✓ htmlproofer passed — site is ready to deploy.")
        else:
            print("\n  ✗ htmlproofer reported failures (see output above).")
            sys.exit(1)
    else:
        print(
            "\nTip: run with --htmlproofer to also do a clean build and\n"
            "     validate all internal links with htmlproofer."
        )

    print()


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup command
    subparsers.add_parser("setup", help="Setup mise, Ruby, and gems")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start Jekyll dev server")
    serve_parser.add_argument("--host", help="Host to bind to (default: 127.0.0.1)")

    # Build command
    build_parser = subparsers.add_parser("build", help="Clean build the site")
    build_parser.add_argument(
        "--production",
        action="store_true",
        help="Build in production mode",
    )

    # Test command
    subparsers.add_parser("test", help="Build and run htmlproofer")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check internal links")
    check_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying files",
    )
    check_parser.add_argument(
        "--htmlproofer",
        action="store_true",
        help="Also run a clean build + htmlproofer",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch to command handlers
    if args.command == "setup":
        cmd_setup()
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "check":
        cmd_check(args)


if __name__ == "__main__":
    main()
