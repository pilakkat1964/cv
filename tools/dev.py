#!/usr/bin/env python3
"""
dev.py — Unified development tool for CV Jekyll site

This script combines multiple development tasks:
  1. Setup: Ensures mise, Ruby 3.4.9, and gems are properly configured
  2. Serve: Start local Jekyll dev server with auto-reload
  3. Build: Clean build for testing/deployment
  4. Test:  Build + validate links with htmlproofer
  5. Check: Check for broken internal links in posts
  6. Branch Management: Create/switch/merge feature and bugfix branches

Usage:
  ./tools/dev.py setup                    # Setup mise, Ruby, and gems
  ./tools/dev.py serve [--host HOST]     # Serve locally (default: 127.0.0.1)
  ./tools/dev.py build [--production]    # Build the site
  ./tools/dev.py test                    # Build + run htmlproofer
  ./tools/dev.py check [--dry-run] [--htmlproofer]  # Check internal links
  ./tools/dev.py feature <name>          # Create feature/<name> branch
  ./tools/dev.py bugfix <name>           # Create bugfix/<name> branch
  ./tools/dev.py switch <branch>         # Switch to existing branch
  ./tools/dev.py commit -m <message>     # Commit changes
  ./tools/dev.py merge                   # Merge current branch to main
  ./tools/dev.py delete <branch>         # Delete a local branch
  ./tools/dev.py status                  # Show git status
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


# ── Branch Management ────────────────────────────────────────────────────────


def get_current_branch() -> str:
    """Get the current git branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def get_main_branch() -> str:
    """Get the main branch name (main or master)."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode == 0:
        # Format: origin/main or origin/master
        ref = result.stdout.strip()
        if "/" in ref:
            return ref.split("/", 1)[1]

    # Fallback: check what exists locally
    if branch_exists("main"):
        return "main"
    elif branch_exists("master"):
        return "master"
    else:
        return "main"  # Default


def branch_exists(branch_name: str) -> bool:
    """Check if a branch exists locally."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"],
        capture_output=True,
        cwd=REPO_ROOT,
    )
    return result.returncode == 0


def run_git(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command."""
    print(f"\n$ git {' '.join(cmd)}")
    return subprocess.run(["git"] + cmd, cwd=REPO_ROOT, check=check)


def cmd_feature(args) -> None:
    """Create and switch to a feature branch."""
    print_header(f"FEATURE: Creating feature branch '{args.name}'")

    branch_name = f"feature/{args.name}"
    main_branch = get_main_branch()

    if branch_exists(branch_name):
        print(f"\n✗ Branch '{branch_name}' already exists")
        sys.exit(1)

    print(f"\n1. Creating branch from '{main_branch}'...")
    run_git(["checkout", main_branch], check=True)
    run_git(["pull", "origin", main_branch], check=False)  # Optional, non-fatal

    print(f"\n2. Creating and switching to '{branch_name}'...")
    run_git(["checkout", "-b", branch_name], check=True)

    print(f"\n✓ Feature branch created and switched!")
    print(f"   Branch: {branch_name}")
    print(f"   Start making changes and commit with: git commit -m 'message'")
    print()


def cmd_bugfix(args) -> None:
    """Create and switch to a bugfix branch."""
    print_header(f"BUGFIX: Creating bugfix branch '{args.name}'")

    branch_name = f"bugfix/{args.name}"
    main_branch = get_main_branch()

    if branch_exists(branch_name):
        print(f"\n✗ Branch '{branch_name}' already exists")
        sys.exit(1)

    print(f"\n1. Creating branch from '{main_branch}'...")
    run_git(["checkout", main_branch], check=True)
    run_git(["pull", "origin", main_branch], check=False)  # Optional, non-fatal

    print(f"\n2. Creating and switching to '{branch_name}'...")
    run_git(["checkout", "-b", branch_name], check=True)

    print(f"\n✓ Bugfix branch created and switched!")
    print(f"   Branch: {branch_name}")
    print(f"   Start making changes and commit with: git commit -m 'message'")
    print()


def cmd_switch(args) -> None:
    """Switch to an existing branch."""
    print_header(f"SWITCH: Switching to branch '{args.branch}'")

    if not branch_exists(args.branch):
        print(f"\n✗ Branch '{args.branch}' does not exist locally")
        print("\nAvailable branches:")
        run_git(["branch"], check=True)
        sys.exit(1)

    print(f"\n1. Switching to '{args.branch}'...")
    run_git(["checkout", args.branch], check=True)

    print(f"\n✓ Switched to branch '{args.branch}'")
    run_git(["status", "--short"], check=False)
    print()


def cmd_commit(args) -> None:
    """Commit changes with a message."""
    print_header("COMMIT: Creating git commit")

    current_branch = get_current_branch()
    main_branch = get_main_branch()
    print(f"\nCurrent branch: {current_branch}")

    if current_branch in (main_branch, "master", "main"):
        print(f"\n⚠ Warning: You're committing directly to '{main_branch}'!")
        print("  It's recommended to use feature/bugfix branches.")
        response = input("\nContinue? (yes/no): ").strip().lower()
        if response != "yes":
            print("Aborted.")
            sys.exit(1)

    print(f"\n1. Staging all changes...")
    run_git(["add", "-A"], check=True)

    print(f"\n2. Creating commit with message...")
    print(f'   Message: "{args.message}"')
    run_git(["commit", "-m", args.message], check=True)

    print(f"\n✓ Commit created!")
    run_git(["log", "-1", "--oneline"], check=False)
    print()


def cmd_merge(args) -> None:
    """Merge current branch back to main/master."""
    print_header("MERGE: Merging branch back to main")

    current_branch = get_current_branch()
    main_branch = get_main_branch()
    print(f"\nCurrent branch: {current_branch}")

    if (
        current_branch == main_branch
        or current_branch == "main"
        or current_branch == "master"
    ):
        print(f"\n✗ You're already on '{main_branch}'. Nothing to merge.")
        sys.exit(1)

    if not branch_exists(main_branch):
        print(f"\n✗ Branch '{main_branch}' does not exist")
        sys.exit(1)

    print(f"\n1. Checking for uncommitted changes...")
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.stdout.strip():
        print("✗ You have uncommitted changes:")
        print(result.stdout)
        print("\nCommit your changes first with: ./tools/dev.py commit -m 'message'")
        sys.exit(1)
    print("   ✓ Working directory is clean")

    print(f"\n2. Fetching latest from origin...")
    run_git(["fetch", "origin"], check=False)

    print(f"\n3. Switching to '{main_branch}'...")
    run_git(["checkout", main_branch], check=True)

    print(f"\n4. Pulling latest changes from '{main_branch}'...")
    run_git(["pull", "origin", main_branch], check=False)

    print(f"\n5. Merging '{current_branch}' into '{main_branch}'...")
    result = run_git(
        ["merge", current_branch, "-m", f"Merge {current_branch} into {main_branch}"],
        check=False,
    )

    if result.returncode != 0:
        print("\n✗ Merge conflict detected!")
        print("  Please resolve conflicts manually and commit.")
        print(f"  Then run: git push origin {main_branch}")
        sys.exit(1)

    print(f"\n6. Pushing to origin...")
    run_git(["push", "origin", main_branch], check=True)

    print(f"\n✓ Merge complete!")
    print(f"   Branch '{current_branch}' has been merged into '{main_branch}'")
    print(f"   You can delete the feature branch with:")
    print(f"   git branch -d {current_branch}")
    print()


def cmd_delete(args) -> None:
    """Delete a local branch."""
    print_header(f"DELETE: Removing branch '{args.branch}'")

    main_branch = get_main_branch()

    if args.branch in (main_branch, "main", "master"):
        print(f"\n✗ Cannot delete '{args.branch}' branch")
        sys.exit(1)

    if not branch_exists(args.branch):
        print(f"\n✗ Branch '{args.branch}' does not exist")
        sys.exit(1)

    current_branch = get_current_branch()
    if current_branch == args.branch:
        print(f"\n1. Switching away from '{args.branch}'...")
        run_git(["checkout", main_branch], check=True)

    print(f"\n2. Deleting branch '{args.branch}'...")
    force_flag = "-D" if args.force else "-d"
    run_git(["branch", force_flag, args.branch], check=True)

    print(f"\n✓ Branch '{args.branch}' has been deleted")
    print()


def cmd_status() -> None:
    """Show current branch and git status."""
    print_header("STATUS: Git Repository Status")

    current_branch = get_current_branch()
    print(f"\nCurrent branch: {current_branch}")

    print(f"\n── Branch list ──\n")
    run_git(["branch", "-vv"], check=False)

    print(f"\n── Working directory status ──\n")
    run_git(["status"], check=False)

    print()


# ── Help System ──────────────────────────────────────────────────────────────

HELP_TOPICS = {
    "getting-started": {
        "title": "Getting Started",
        "description": "Start developing with this project",
        "content": """
FIRST TIME SETUP
────────────────
1. Run setup command:
   ./tools/dev.py setup

2. Read the development guide:
   cat DEVELOPMENT.md

3. Create your first feature:
   ./tools/dev.py feature my-first-feature

4. Start the dev server:
   ./tools/dev.py serve

5. Open your browser:
   http://127.0.0.1:4000/cv/

BASIC WORKFLOW
──────────────
For any task, follow this pattern:

  1. Create branch:      ./tools/dev.py feature feature-name
  2. Make changes:       Edit files, test locally
  3. Commit changes:     ./tools/dev.py commit -m "message"
  4. Verify quality:     ./tools/dev.py test
  5. Merge to main:      ./tools/dev.py merge

ENVIRONMENT
───────────
• Ruby: 3.4.9 (managed by mise)
• Jekyll: 4.3.4
• Gems: Installed locally
• Port: 4000 (default)
""",
    },
    "setup": {
        "title": "Setup Command",
        "description": "Configure development environment",
        "content": """
USAGE
─────
./tools/dev.py setup

WHAT IT DOES
────────────
1. Verifies mise is installed
2. Checks Ruby version from mise.toml
3. Installs/updates tools via mise
4. Installs Ruby gems locally
5. Verifies everything is working

WHEN TO RUN
───────────
• First time setting up the project
• After major gem/dependency changes
• When gems seem outdated
• After switching Ruby versions

OUTPUT
──────
You'll see:
✓ Mise installation check
✓ Ruby version verification
✓ Tool installation status
✓ Gem installation status
✓ Final success message

TROUBLESHOOTING
───────────────
If setup fails:
1. Verify mise is installed: which mise
2. Check Ruby availability: ruby --version
3. Ensure internet connection for gem download
4. Run with verbose output for debugging
""",
    },
    "serve": {
        "title": "Serve Command",
        "description": "Start local development server",
        "content": """
USAGE
─────
./tools/dev.py serve [--host HOST]

EXAMPLES
────────
./tools/dev.py serve                    # Default: 127.0.0.1
./tools/dev.py serve --host 0.0.0.0    # Listen on all interfaces
./tools/dev.py serve --host 192.168.1.10

WHAT IT DOES
────────────
1. Verifies Ruby version is correct
2. Starts Jekyll development server
3. Enables auto-reload on file changes
4. Detects Docker and enables force_polling
5. Provides local URL for browsing

ACCESSING THE SITE
──────────────────
Open your browser to:
http://127.0.0.1:4000/cv/

STOPPING THE SERVER
───────────────────
Press Ctrl+C to stop the server

AUTO-RELOAD
───────────
The site automatically rebuilds when you:
• Edit HTML/YAML files
• Modify CSS/SCSS
• Update content
• Change Jekyll config

TROUBLESHOOTING
───────────────
Port 4000 already in use?
• Find process: lsof -i :4000
• Kill process: kill -9 <PID>
• Or use different port: netstat -tlnp | grep 4000

Can't connect?
• Check host: ./tools/dev.py serve --host 127.0.0.1
• Verify port: netstat -tlnp | grep 4000
• Check Ruby: eval "$(mise activate bash)"

Ruby version errors?
• Reactivate mise: eval "$(mise activate bash)"
• Run setup: ./tools/dev.py setup
""",
    },
    "build": {
        "title": "Build Command",
        "description": "Build the site for testing/deployment",
        "content": """
USAGE
─────
./tools/dev.py build [--production]

MODES
─────
Development:  ./tools/dev.py build
Production:   ./tools/dev.py build --production

WHAT IT DOES
────────────
1. Cleans previous builds (.jekyll-cache, _site)
2. Compiles Jekyll site
3. Sets JEKYLL_ENV appropriately
4. Generates static files ready for deployment

DIFFERENCES
───────────
Development mode:
• Includes all posts (including drafts)
• Disables compression
• Faster build time

Production mode:
• Optimizes CSS/JS
• Compresses output
• Production-ready output
• Sets JEKYLL_ENV=production

OUTPUT LOCATION
───────────────
Generated files in: _site/

BUILD TIME
──────────
Typical build: 1-2 seconds
First build: 2-3 seconds

TROUBLESHOOTING
───────────────
Build fails with Ruby error?
• Run: ./tools/dev.py setup
• Check Ruby version: ruby --version
• Verify gems: bundle check

Build very slow?
• Check disk space
• Verify no other Jekyll running
• Check file permissions

Port conflict?
• This doesn't use a port, it's just building
• Safe to run anytime
""",
    },
    "test": {
        "title": "Test Command",
        "description": "Build and validate site with htmlproofer",
        "content": """
USAGE
─────
./tools/dev.py test

WHAT IT DOES
────────────
1. Builds site in production mode
2. Cleans previous build artifacts
3. Runs htmlproofer validation
4. Checks all internal links
5. Reports any issues

WHEN TO RUN
───────────
• Before committing changes
• Before merging to main
• Before deploying to production
• When making link changes

VALIDATION CHECKS
─────────────────
✓ Internal links validity
✓ Broken link detection
✓ HTML structure validation
✓ Attribute validation
✓ Image reference validation

EXPECTED OUTPUT
───────────────
Success:
✓ All tests passed! Site is ready to deploy.

Failure:
✗ Tests failed (see output above)
   Shows which links are broken
   Shows which files have issues

BUILD TIME
──────────
Typical test: 3-5 seconds
With failures: Varies by issue count

IGNORED URLS
────────────
Automatically ignores:
• http://127.0.0.1/*
• http://0.0.0.0/*
• http://localhost/*

TROUBLESHOOTING
───────────────
htmlproofer not found?
• Run: ./tools/dev.py setup
• Check Gemfile includes htmlproofer

Test fails unexpectedly?
• Clear cache: rm -rf _site .jekyll-cache
• Rebuild: ./tools/dev.py test

Specific link errors?
• Check link syntax in source files
• Verify files exist where linked
• Look for typos in URLs
""",
    },
    "check": {
        "title": "Check Command",
        "description": "Check and fix broken internal links",
        "content": """
USAGE
─────
./tools/dev.py check [--dry-run] [--htmlproofer]

MODES
─────
Check only:          ./tools/dev.py check
Dry run (no changes):  ./tools/dev.py check --dry-run
Full validation:      ./tools/dev.py check --htmlproofer

WHAT IT DOES
────────────
1. Scans all published posts
2. Finds links to unpublished/draft posts
3. Identifies if target is draft or missing
4. Can auto-fix by marking as "(coming soon)"
5. Reports all issues found

DRY RUN MODE
────────────
Shows what would be changed without modifying files:
./tools/dev.py check --dry-run

Output shows:
[dry-run] filename
link: [label](/posts/slug/)
→: label (coming soon)
slug is a draft/UNKNOWN

AUTO-FIX MODE
──────────────
Actually fixes issues:
./tools/dev.py check

Changes broken links to:
[label](/posts/slug/)  →  label *(coming soon)*

FULL VALIDATION MODE
────────────────────
Check + Build + htmlproofer:
./tools/dev.py check --htmlproofer

Comprehensive validation before deployment

WHEN TO RUN
───────────
• When adding new internal links
• Before final deployment
• When publishing draft posts
• Regularly to catch link rot

OUTPUT INTERPRETATION
──────────────────────
"draft" - Link points to unpublished post (will be fixed)
"UNKNOWN" - Link points to non-existent post (needs investigation)
"No broken links" - All internal links are valid

TROUBLESHOOTING
───────────────
No _posts directory?
• Create it: mkdir _posts
• Add some posts first

htmlproofer fails?
• Not installed: ./tools/dev.py setup
• Run separate: ./tools/dev.py test

Doesn't fix links?
• Use without --dry-run: ./tools/dev.py check
• Check file permissions
• Verify posts are in _posts directory
""",
    },
    "feature": {
        "title": "Feature Command",
        "description": "Create and work on a feature branch",
        "content": """
USAGE
─────
./tools/dev.py feature <name>

EXAMPLES
────────
./tools/dev.py feature add-dark-mode
./tools/dev.py feature update-portfolio
./tools/dev.py feature responsive-design

NAMING CONVENTIONS
──────────────────
Use lowercase, separate words with hyphens:
✓ add-dark-mode
✓ update-favicon
✓ fix-responsive-layout
✗ AddDarkMode (use hyphens, not camelCase)
✗ add_dark_mode (use hyphens, not underscores)

WHAT IT DOES
────────────
1. Fetches latest from origin
2. Creates feature/your-name branch
3. Switches to new branch
4. Ready for development

WORKFLOW
────────
1. Create feature:
   ./tools/dev.py feature add-dark-mode

2. Make changes:
   ./tools/dev.py serve
   # Edit files in your editor

3. Commit changes:
   ./tools/dev.py commit -m "feat: Add dark mode support"

4. Test thoroughly:
   ./tools/dev.py test

5. Merge to main:
   ./tools/dev.py merge

BRANCH NAMING
─────────────
Branch will be: feature/your-name

Examples in repo:
feature/add-dark-mode
feature/update-portfolio
feature/responsive-design

TROUBLESHOOTING
───────────────
Branch already exists?
✗ "Branch 'feature/name' already exists"
Solution:
• Use different name: ./tools/dev.py feature my-new-feature
• Or delete old branch: ./tools/dev.py delete feature/old-feature

Network error creating branch?
• Check internet connection
• Verify origin is accessible
• Try again: ./tools/dev.py feature name

Can't commit changes?
• Ensure on feature branch: ./tools/dev.py status
• Stage changes: git add -A
• Then commit: ./tools/dev.py commit -m "message"
""",
    },
    "bugfix": {
        "title": "Bugfix Command",
        "description": "Create and work on a bugfix branch",
        "content": """
USAGE
─────
./tools/dev.py bugfix <name>

EXAMPLES
────────
./tools/dev.py bugfix fix-link-colors
./tools/dev.py bugfix typo-in-bio
./tools/dev.py bugfix mobile-layout

NAMING CONVENTIONS
──────────────────
Describe the bug being fixed:
✓ fix-link-colors
✓ resolve-typo
✓ correct-mobile-layout
✗ MobileLayoutBug (use lowercase hyphens)
✗ bug_fix_1 (describe the issue)

WHAT IT DOES
────────────
1. Fetches latest from origin
2. Creates bugfix/your-name branch
3. Switches to new branch
4. Ready for fixing

WORKFLOW
────────
1. Create bugfix branch:
   ./tools/dev.py bugfix fix-typo

2. Identify and fix the issue:
   ./tools/dev.py serve
   # Edit files to fix bug

3. Commit the fix:
   ./tools/dev.py commit -m "fix: Correct spelling in bio"

4. Verify fix works:
   ./tools/dev.py test

5. Merge to main:
   ./tools/dev.py merge

BRANCH NAMING
─────────────
Branch will be: bugfix/your-name

Examples in repo:
bugfix/fix-link-colors
bugfix/mobile-layout-issue
bugfix/typo-in-bio

COMMIT MESSAGES
───────────────
Start with "fix:" prefix:
./tools/dev.py commit -m "fix: Correct CSS bug on mobile"
./tools/dev.py commit -m "fix: Resolve link color issue"

TROUBLESHOOTING
───────────────
Branch already exists?
✗ "Branch 'bugfix/name' already exists"
Solution:
• Use different name: ./tools/dev.py bugfix fix-different-issue
• Or delete old branch: ./tools/dev.py delete bugfix/old-fix

Can't reproduce bug?
• Verify steps to reproduce
• Check correct branch: ./tools/dev.py status
• Run serve to test: ./tools/dev.py serve

Fix seems incomplete?
• Run tests: ./tools/dev.py test
• Check all affected areas
• Add more commits if needed
""",
    },
    "commit": {
        "title": "Commit Command",
        "description": "Commit changes with a descriptive message",
        "content": """
USAGE
─────
./tools/dev.py commit -m "message"

EXAMPLES
────────
./tools/dev.py commit -m "feat: Add dark mode support"
./tools/dev.py commit -m "fix: Correct mobile layout"
./tools/dev.py commit -m "docs: Update README"
./tools/dev.py commit -m "test: Add unit tests"
./tools/dev.py commit -m "chore: Update dependencies"

WHAT IT DOES
────────────
1. Stages all changes (git add -A)
2. Creates commit with your message
3. Shows commit hash
4. Displays commit message for verification

MESSAGE FORMAT
──────────────
Start with type, then description:
  type: brief description

Common types:
feat:     New feature
fix:      Bug fix
docs:     Documentation changes
test:     Test additions
chore:    Dependencies, tooling
refactor: Code reorganization
perf:     Performance improvements

MESSAGE GUIDELINES
──────────────────
✓ Start with lowercase (after type)
✓ Use present tense: "Add" not "Added"
✓ Be specific: "Fix mobile layout" not "Fix stuff"
✓ Keep under 72 characters when possible
✓ Add details if needed on new lines

GOOD EXAMPLES
─────────────
./tools/dev.py commit -m "feat: Add dark mode toggle"
./tools/dev.py commit -m "fix: Correct CSS overflow on mobile"
./tools/dev.py commit -m "docs: Update installation guide"
./tools/dev.py commit -m "test: Add validation tests"

POOR EXAMPLES
─────────────
✗ ./tools/dev.py commit -m "stuff"
✗ ./tools/dev.py commit -m "Fixed bugs"
✗ ./tools/dev.py commit -m "asdf"
✗ ./tools/dev.py commit -m "Work in progress"

WHAT GETS STAGED
────────────────
ALL changes:
• New files
• Modified files
• Deleted files

No need to stage manually - this does it all

MULTI-LINE MESSAGES
───────────────────
For longer descriptions, use single quotes:
./tools/dev.py commit -m 'feat: Add dark mode

Implements toggle button in settings
Saves preference to localStorage
Supports system preference detection'

TROUBLESHOOTING
───────────────
"You're committing to main"?
• Warning when on main branch
• Recommended: Use feature/bugfix branch first
• Answer "yes" if intentional

Nothing to commit?
• No changes found
• Make edits first: vim filename
• Then try again

Commit message too long?
• Keep main message short
• Put details in separate lines
""",
    },
    "merge": {
        "title": "Merge Command",
        "description": "Merge feature/bugfix branch back to main",
        "content": """
USAGE
─────
./tools/dev.py merge

WHAT IT DOES
────────────
1. Checks for uncommitted changes
2. Fetches latest from origin
3. Switches to main branch
4. Pulls latest changes
5. Merges your branch
6. Pushes to remote
7. Shows cleanup instructions

SAFETY CHECKS
─────────────
Won't merge if:
✗ Uncommitted changes exist
✗ On main branch already
✗ Main branch doesn't exist
✗ Merge conflicts detected

Prerequisites
─────────────
Before merging, ensure:
✓ All changes committed: ./tools/dev.py commit -m "message"
✓ All tests pass: ./tools/dev.py test
✓ On feature/bugfix branch: ./tools/dev.py status
✓ Documentation updated if needed

WORKFLOW EXAMPLE
────────────────
1. Check status:
   ./tools/dev.py status

2. Commit any pending changes:
   ./tools/dev.py commit -m "final: Last commit"

3. Run tests one more time:
   ./tools/dev.py test

4. Merge to main:
   ./tools/dev.py merge

5. Delete branch (optional):
   git branch -d feature/your-feature

SUCCESS OUTPUT
──────────────
✓ Merge complete!
   Branch 'feature/name' merged into 'main'
   You can delete the branch with:
   git branch -d feature/name

MERGE CONFLICTS
───────────────
If conflicts are detected:
1. Fix conflicts manually in affected files
2. Commit the resolution:
   ./tools/dev.py commit -m "fix: Resolve merge conflicts"
3. Push: git push origin main

AFTER MERGE
───────────
1. Delete the feature branch:
   git branch -d feature/your-feature

2. View merged changes:
   git log --oneline -5

3. Start new feature:
   ./tools/dev.py feature next-feature

TROUBLESHOOTING
───────────────
Uncommitted changes error?
• Review changes: ./tools/dev.py status
• Commit them: ./tools/dev.py commit -m "message"
• Then merge: ./tools/dev.py merge

Already on main?
• Switch to feature: ./tools/dev.py switch feature/name
• Or create new: ./tools/dev.py feature new-name

Network error during push?
• Check internet: ping github.com
• Verify credentials
• Try again: ./tools/dev.py merge
""",
    },
    "switch": {
        "title": "Switch Command",
        "description": "Switch to a different branch",
        "content": """
USAGE
─────
./tools/dev.py switch <branch>

EXAMPLES
────────
./tools/dev.py switch dev
./tools/dev.py switch master
./tools/dev.py switch feature/add-dark-mode
./tools/dev.py switch bugfix/fix-typo

WHAT IT DOES
────────────
1. Verifies branch exists
2. Switches to the branch
3. Shows current status
4. Displays any uncommitted changes

COMMON BRANCHES
───────────────
master/main:           Production branch
dev:                   Development branch
feature/something:     Feature branch
bugfix/something:      Bugfix branch

LISTING BRANCHES
────────────────
See all branches:
./tools/dev.py status

Shows:
* current-branch     (currently on)
  other-branch

SWITCHING BETWEEN TASKS
────────────────────────
1. On feature/task-a:
   ./tools/dev.py commit -m "msg"

2. Switch to other task:
   ./tools/dev.py switch feature/task-b

3. Make changes to task-b

4. Commit:
   ./tools/dev.py commit -m "msg"

5. Switch back anytime:
   ./tools/dev.py switch feature/task-a

TROUBLESHOOTING
───────────────
"Branch does not exist"?
• List branches: ./tools/dev.py status
• Create branch: ./tools/dev.py feature name
• Check spelling

Uncommitted changes warning?
• Commit them: ./tools/dev.py commit -m "message"
• Or stash: git stash
• Then switch

Can't switch to branch?
• Verify it exists: git branch -a
• Try exact name: ./tools/dev.py switch feature/name
• Check for typos

WORKFLOW TIPS
─────────────
Keep work organized:
1. One task per branch
2. Commit frequently
3. Clear branch names
4. Merge when done
5. Delete old branches

See what changed:
git diff main feature/your-branch
""",
    },
    "delete": {
        "title": "Delete Command",
        "description": "Delete a local branch",
        "content": """
USAGE
─────
./tools/dev.py delete <branch>
./tools/dev.py delete <branch> --force

EXAMPLES
────────
./tools/dev.py delete feature/add-dark-mode
./tools/dev.py delete bugfix/fix-typo
./tools/dev.py delete -f feature/incomplete-work

WHAT IT DOES
────────────
1. Verifies branch exists
2. Prevents deletion of main/master
3. Switches away if currently on branch
4. Deletes the local branch
5. Confirms deletion

DELETION MODES
──────────────
Normal delete:
./tools/dev.py delete feature/old-feature
  - Safe, won't delete unmerged work
  - Fails if branch not merged

Force delete:
./tools/dev.py delete feature/old-feature -f
  - Deletes even if not merged
  - Use with caution
  - Good for abandoned branches

WHEN TO DELETE
──────────────
After merging:
./tools/dev.py merge
./tools/dev.py delete feature/your-feature

Abandoning work:
./tools/dev.py delete -f feature/experimental

Cleaning up:
::tools/dev.py status  # List branches
./tools/dev.py delete feature/old-task-1
./tools/dev.py delete bugfix/old-fix-1

PROTECTED BRANCHES
──────────────────
Can't delete:
✗ ./tools/dev.py delete main
✗ ./tools/dev.py delete master
✗ ./tools/dev.py delete dev (typically protected)

Error message: "Cannot delete 'main' branch"

TROUBLESHOOTING
───────────────
"Branch does not exist"?
• Check spelling: ./tools/dev.py delete feature/name
• List branches: ./tools/dev.py status
• Might already be deleted

"Branch not merged"?
• If work is saved elsewhere: use -f flag
• If work is important: don't delete
• If work is abandoned: use -f to force

Currently on branch to delete?
• Script automatically switches away
• Then deletes the branch
• You'll be switched to main

CLEANUP WORKFLOW
────────────────
1. List branches:
   ./tools/dev.py status

2. Delete merged branches:
   ./tools/dev.py delete feature/completed-task

3. Clean up old branches:
   for branch in $(git branch | grep old); do
    ./tools/dev.py delete "$branch" -f
   done

TIP
───
Good practice: Delete merged branches to keep
repository clean and organized
""",
    },
    "status": {
        "title": "Status Command",
        "description": "Show repository and branch status",
        "content": """
USAGE
─────
./tools/dev.py status

WHAT IT SHOWS
─────────────
1. Current branch name
2. List of all local branches
3. Tracking information
4. Working directory status
5. Uncommitted changes

OUTPUT SECTIONS
───────────────
Current branch:
  dev (the branch you're on)

Branch list:
  * dev                (current, marked with *)
  feature/add-feature  (other local branches)
  master
  bugfix/fix-issue

Working directory:
  On branch dev
  Your branch is ahead of 'origin/dev' by 2 commits
  Changes not staged for commit:
    modified: file.txt
    deleted: old-file.txt
  Untracked files:
    new-file.txt

INTERPRETING STATUS
───────────────────
"ahead of origin/main by 2 commits"
  = You have 2 commits not pushed

"behind origin/main by 1 commit"
  = Remote has 1 commit you don't have

"diverged"
  = Both local and remote have new commits

"nothing to commit, working tree clean"
  = All changes are committed

"Changes not staged"
  = Files modified but not committed

"Untracked files"
  = New files not added to git

COMMON STATUS SCENARIOS
─────────────────────────

Just started feature:
$ ./tools/dev.py status
On branch feature/add-dark-mode
nothing to commit, working tree clean

After making changes:
$ ./tools/dev.py status
On branch feature/add-dark-mode
Changes not staged for commit:
  modified: _sass/_base.scss

After committing:
$ ./tools/dev.py status
On branch feature/add-dark-mode
Your branch is ahead of 'origin/master' by 1 commits

Before merging:
$ ./tools/dev.py status
On branch feature/add-dark-mode
nothing to commit, working tree clean

NEXT ACTIONS BASED ON STATUS
──────────────────────────────
Uncommitted changes?
→ Commit: ./tools/dev.py commit -m "message"

Behind remote?
→ Pull: git pull origin branch-name

Ready to merge?
→ Merge: ./tools/dev.py merge

Want to see differences?
→ Diff: git diff filename

List all branches:
→ Status: ./tools/dev.py status

TIPS
────
Run status frequently to:
✓ Know what branch you're on
✓ See uncommitted changes
✓ Check sync with remote
✓ Plan next steps

Run before:
✓ Committing work
✓ Switching branches
✓ Merging to main
✓ Pushing to remote
""",
    },
    "troubleshooting": {
        "title": "Troubleshooting Guide",
        "description": "Common issues and solutions",
        "content": """
ENVIRONMENT ISSUES
──────────────────

"Ruby version mismatch"
Problem: Expected 3.4.9 but have 3.2.3
Solution:
  eval "$(mise activate bash)"
  ./tools/dev.py setup

"mise not found"
Problem: mise is not installed
Solution:
  Install from: https://mise.jq.rs/
  Then: ./tools/dev.py setup

"gem not found"
Problem: Missing required gem
Solution:
  ./tools/dev.py setup
  bundle install

JEKYLL ISSUES
─────────────

"Port 4000 already in use"
Problem: Another Jekyll is running
Solution:
  lsof -i :4000  (find process)
  kill -9 <PID>  (stop process)
  ./tools/dev.py serve

"Jekyll won't start"
Problem: Build or config error
Solution:
  ./tools/dev.py build
  Check error message
  Fix the issue
  ./tools/dev.py serve

"Assets not loading (CSS/JS)"
Problem: Baseurl configuration
Solution:
  Check _config.yml
  Verify baseurl setting
  Restart server: Ctrl+C then serve again

GIT ISSUES
──────────

"Can't commit - dirty working tree"
Problem: Uncommitted changes
Solution:
  ./tools/dev.py status (see changes)
  Fix files or discard: git restore filename
  Or commit: ./tools/dev.py commit -m "message"

"Merge conflict detected"
Problem: Conflicting changes
Solution:
  1. Open conflicted files
  2. Resolve <<<< ==== >>>> markers
  3. Commit: ./tools/dev.py commit -m "fix: Resolve conflicts"
  4. Push: git push origin branch

"Branch doesn't exist"
Problem: Typo or branch already deleted
Solution:
  ./tools/dev.py status (list branches)
  Create new: ./tools/dev.py feature name
  Or use existing name exactly

"Can't switch branches"
Problem: Uncommitted changes
Solution:
  ./tools/dev.py commit -m "message"
  Or stash: git stash
  Then switch: ./tools/dev.py switch branch

LINK/BUILD ISSUES
─────────────────

"htmlproofer failures"
Problem: Broken internal links
Solution:
  Run check: ./tools/dev.py check
  Auto-fixes draft links
  Or manually: Fix link paths in files
  Retest: ./tools/dev.py test

"Links to missing posts"
Problem: Link points to non-existent post
Solution:
  Check post exists: ls _posts/
  Verify filename format: YYYY-MM-DD-slug.md
  Fix link in source file
  Retest

"Build is very slow"
Problem: Too many files or permissions
Solution:
  Check disk space: df -h
  Clear cache: rm -rf _site .jekyll-cache
  Rebuild: ./tools/dev.py build
  Check file permissions: ls -la _posts/

GETTING HELP
────────────

See help for command:
  ./tools/dev.py <command> -h

See all help topics:
  ./tools/dev.py help

See specific topic:
  ./tools/dev.py help getting-started

Read full guide:
  cat DEVELOPMENT.md

Check git status:
  ./tools/dev.py status

When asking for help:
  1. Include error message
  2. Include command you ran
  3. Include OS/environment
  4. Mention what you were trying to do
""",
    },
    "workflows": {
        "title": "Common Workflows",
        "description": "Step-by-step guides for typical tasks",
        "content": """
ADD A NEW FEATURE
─────────────────
1. Create branch:
   ./tools/dev.py feature add-new-feature

2. Start dev server:
   ./tools/dev.py serve

3. Edit files in your editor:
   Open http://127.0.0.1:4000/cv/ in browser
   Make changes, watch auto-reload

4. Commit your work:
   ./tools/dev.py commit -m "feat: Add new feature"

5. Test everything:
   ./tools/dev.py test

6. Merge to main:
   ./tools/dev.py merge

7. Delete branch (optional):
   git branch -d feature/add-new-feature

FIX A BUG
─────────
1. Create bugfix branch:
   ./tools/dev.py bugfix fix-the-bug

2. Test to reproduce:
   ./tools/dev.py serve
   http://127.0.0.1:4000/cv/

3. Fix the issue:
   Edit files to resolve problem

4. Test fix works:
   Browse and verify

5. Commit fix:
   ./tools/dev.py commit -m "fix: Resolve bug"

6. Run full tests:
   ./tools/dev.py test

7. Merge to main:
   ./tools/dev.py merge

8. Cleanup:
   git branch -d bugfix/fix-the-bug

QUICK BUILD & TEST
──────────────────
1. Build production version:
   ./tools/dev.py build --production

2. Run full validation:
   ./tools/dev.py test

3. Check for link issues:
   ./tools/dev.py check --htmlproofer

SWITCH BETWEEN TASKS
────────────────────
Task A progress:
1. ./tools/dev.py commit -m "progress: Task A work"

Switch to Task B:
2. ./tools/dev.py switch feature/task-b

Task B work:
3. Edit files...

Commit Task B:
4. ./tools/dev.py commit -m "feat: Task B complete"

Back to Task A:
5. ./tools/dev.py switch feature/task-a

Continue Task A:
6. More edits...

FINAL CLEANUP BEFORE MERGE
───────────────────────────
1. Check status:
   ./tools/dev.py status

2. Commit pending:
   ./tools/dev.py commit -m "final: Finishing touches"

3. Verify quality:
   ./tools/dev.py test

4. Merge:
   ./tools/dev.py merge

5. Delete branch:
   git branch -d feature/your-feature

DAILY ROUTINE
─────────────
Morning:
1. Setup: ./tools/dev.py setup
2. Serve: ./tools/dev.py serve

Work:
3. Make changes
4. Test locally

Before wrapping up:
5. Status: ./tools/dev.py status
6. Commit: ./tools/dev.py commit -m "message"
7. Test: ./tools/dev.py test

End of work:
8. Merge: ./tools/dev.py merge
9. Delete: git branch -d feature/name
10. Status: ./tools/dev.py status
""",
    },
}


def show_help(topic: str = "help") -> None:
    """Show help for a specific topic or list all topics."""
    if topic == "help" or topic == "":
        # Show help menu
        print("\n" + "=" * 70)
        print("  AVAILABLE HELP TOPICS")
        print("=" * 70 + "\n")
        print("Usage: ./tools/dev.py help <topic>\n")
        print("Topics:")
        for key in sorted(HELP_TOPICS.keys()):
            info = HELP_TOPICS[key]
            print(f"  {key:20} - {info['description']}")
        print("\nExamples:")
        print("  ./tools/dev.py help getting-started")
        print("  ./tools/dev.py help feature")
        print("  ./tools/dev.py help troubleshooting")
        print("\nShort help:")
        print("  ./tools/dev.py <command> -h")
        print()
        return

    if topic not in HELP_TOPICS:
        print(f"\n✗ Unknown topic: {topic}")
        print("\nUse './tools/dev.py help' to see all topics")
        sys.exit(1)

    help_info = HELP_TOPICS[topic]
    print("\n" + "=" * 70)
    print(f"  {help_info['title']}")
    print("=" * 70)
    print(help_info["content"])


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

    # Branch management commands
    feature_parser = subparsers.add_parser("feature", help="Create feature branch")
    feature_parser.add_argument("name", help="Feature name (e.g., 'add-dark-mode')")

    bugfix_parser = subparsers.add_parser("bugfix", help="Create bugfix branch")
    bugfix_parser.add_argument("name", help="Bug name (e.g., 'fix-link-colors')")

    switch_parser = subparsers.add_parser("switch", help="Switch to existing branch")
    switch_parser.add_argument("branch", help="Branch name")

    commit_parser = subparsers.add_parser("commit", help="Commit staged changes")
    commit_parser.add_argument("-m", "--message", required=True, help="Commit message")

    merge_parser = subparsers.add_parser("merge", help="Merge current branch to main")

    delete_parser = subparsers.add_parser("delete", help="Delete a local branch")
    delete_parser.add_argument("branch", help="Branch name to delete")
    delete_parser.add_argument(
         "-f", "--force", action="store_true", help="Force delete (use -D instead of -d)"
    )

    status_parser = subparsers.add_parser("status", help="Show git status")

    # Help command
    help_parser = subparsers.add_parser("help", help="Show help for a topic")
    help_parser.add_argument(
         "topic",
         nargs="?",
         default="help",
         help="Help topic (use 'help' alone for list of topics)",
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
    elif args.command == "feature":
        cmd_feature(args)
    elif args.command == "bugfix":
        cmd_bugfix(args)
    elif args.command == "switch":
        cmd_switch(args)
    elif args.command == "commit":
        cmd_commit(args)
    elif args.command == "merge":
        cmd_merge(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "status":
         cmd_status()
    elif args.command == "help":
         show_help(args.topic)


if __name__ == "__main__":
    main()
