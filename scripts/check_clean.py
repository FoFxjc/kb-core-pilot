"""Fail when tracked files carry local or personal content (enterprise readiness C6). Part of the test suite.

  uv run python scripts/check_clean.py [ROOT]      (exit 1 and one line per finding)

Checks every tracked file (or, outside a git checkout such as an exported snapshot, every file under ROOT) for:
- absolute home paths and machine temp paths (/Users/<name>, /home/<name>, C:\\Users, ~/ paths, /private/var, ...);
- user names: the project's known personal names, plus this machine's git user name, git e-mail and login name
  (words of 4+ letters that are not ordinary account or code words: a build machine's login `root` is not a name);
- session ids: bare UUIDs (ledger ids such as tsk_<uuid> are allowed: the reports list delegations on purpose);
- personal e-mail addresses (example.com / example.internal / noreply addresses are allowed);
- vendor and model names (the external models and agent tools used while building kb-core).
Names are kept as SHA-256 hashes of lower-case words, so this script does not itself carry them. Allowed phrases
(source text quoted from the sample reports, or required file names) are removed before the word check.
"""

import getpass
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "node_modules", "store", ".pytest_cache", "__pycache__", ".superpowers", ".tallyback",
             ".import_linter_cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".lock"}

# lower-case words, hashed: personal names, then vendor / model / agent-tool names
DENIED_WORDS = {
    "026ad9b14a7453b7488daa0c6acbc258b1506f52c441c7c465474c1a564394ff",
    "61d3fc4de3ee7c58c3d37ac31bd09d7211a61514293dc2ff824cddc85c21bafa",
    "bc949ca3e9b7a3a376ae4eb1c486f8b1e26d6c1156b6dd0201aaa15bcf827f59",
    "3677d080a21d5ef4f8d78c3380a3043e7024621047843499bb6e56b9970b565e",
    "cbfe21c37efe3f3f5e2237a3b64ef4ea2ee3e39d2908e0a14c5687193882ff2a",
    "ac1c802834d5004094ded54199a06cde1a9018a6d28812f4bada54e10119a691",
    "c857d09db23e6822e3600bc06ad8d58f92ed62bc8efd81c753f77048662cb97d",
    "c70eca6b0f88f44d81a41311647e50fda1ac454ec04ffd442b0eb4743a993131",
    "e1517be14d06cdb72af7bb52a289a0d5eab667e8b52ec4bac02914e1245f8a40",
    "7d3194f79e645c42e4396dda38be04766810ec6a00d00aced3ffc2a0a1f1a9ef",
    "60965168ce762e949600281ba6d01fee136e5b6e8257b1f216f9025ed324474c",
    "053ea4804ef1bb33d4a3d6fb024a614b6d257cebc2bc7cd915da9c9522f37ffc",
    "6f7ac1823da81d2e52d1a1549ee69c85bbf8bb56d06682849e7c09da2785ce3b",
    "67f2d22514622d1be30c14ee9f3cb104503a159a33a656ca91a1953aa9616429",
    "5d72436256ada53828b51895a94bb8489e9f1ac4fe937a8024ef1594e7045ff6",
    "6749675d80a1faa70859312365b6eab644244d8e5d01cc94f44644c13d090ee7",
    "e4f9c522e1c89280e9561b825f4f24fe32b51ff82d61e5c2b1dfd0321c35a90b",
    "b5d641b432cca81e57b5bb5b73c53e64c50d44dce93595a85d1d8885f48548e8",
    "3669ffb921cca6ee1edfe0f1e620fc2379771e9a8bd92659904540e984f3209e",
    "920510199770f4d65cb8aaa2cd12bdb2b8c37f5b3907c50a734a0e3409da2823",
    "fc5a1047f5919892fcdf8aa79ea5d6bb6531b5c176939ef0110906cb225941c1",
    "72e8088a05b38ae3cffbc126c1c2095046c7700edab31ce35867ce8ee3ac8932",
    "2bf548d8056029c73e6e28132d19a3a277a49daf32b1c1ba7b0b7fc7e78bf5cd",
    "c9ad8f2cc1294afa0ef22fc2c019ff7243cdd272b2147ddca3f34c5036b05768",
    "5a5110ebe1544b31e6d4207a419bc1deb148735f89ae984ff0a2ab809b51f1df",
    "57de4cf40144bdf7d00010f2f5557a7d642c2b9705309bfade167dd313e2ca93",
    "e12ce8285efc67c6d93d3a122e2589ed95089bcbb775ba5634d94e2b8385db07",
}
# phrases removed before the word check: a product and the company secretary named in the sample annual reports,
# and the agent entry file
# (CLAUDE.md only imports AGENTS.md; it is left out of exported snapshots by .gitattributes)
ALLOWED_PHRASES = ("OCBC GPT", "Peter Yeoh", "CLAUDE.md")

PATTERNS = [
    ("home path", re.compile(r"/Users/[A-Za-z0-9._-]+|/home/[a-z][a-z0-9._-]*|[A-Za-z]:(?:\\)+Users(?:\\)+|(?<![\w.])~/[\w.]")),
    ("machine temp path", re.compile(r"/private/(?:tmp|var)/|/var/folders/")),
    ("session id", re.compile(r"(?<![A-Za-z0-9_-])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])")),
    ("e-mail", re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")),
]
# e-mail-shaped text allowed: placeholder domains (also user@host in example DSNs) and no-reply senders
ALLOWED_DOMAINS = re.compile(r"(?:^|\.)example\.(?:com|org|net|internal|invalid)$")
WORD = re.compile(r"[a-z]+")                     # letters only: "qwen3" and "gpt4o" give "qwen", "gpt"
# ordinary account names and words that machine logins and git user names often are; never treated as personal names
COMMON_ACCOUNT_WORDS = {"root", "admin", "administrator", "user", "users", "builder", "build", "ubuntu", "debian",
                        "centos", "runner", "jenkins", "vagrant", "guest", "test", "tester", "deploy", "service",
                        "docker", "github", "gitlab", "your", "name", "noreply", "mail", "email", "local", "home",
                        "node", "data", "postgres", "nobody", "worker", "vscode", "codespace"}


def _h(word: str) -> str:
    return hashlib.sha256(word.encode()).hexdigest()


def local_words() -> set[str]:
    """This machine's git user name, git e-mail (local part) and login name, as hashed words of 4+ letters that are
    not ordinary account or code words."""
    words = set()
    for key in ("user.name", "user.email"):
        out = subprocess.run(["git", "config", key], capture_output=True, text=True).stdout.strip().lower()
        words |= set(WORD.findall(out.split("@")[0]))
    try:
        words |= set(WORD.findall(getpass.getuser().lower()))
    except Exception:
        pass
    return {_h(w) for w in words if len(w) >= 4 and w not in COMMON_ACCOUNT_WORDS}


def files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True)
    if out.returncode == 0 and out.stdout:
        paths = [root / p for p in out.stdout.split("\0") if p]
    else:
        paths = [p for p in root.rglob("*") if p.is_file()]
    me = Path(__file__).resolve()                        # this script spells out the patterns it looks for
    return [p for p in paths if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS)
            and p.suffix.lower() not in SKIP_SUFFIXES and p.resolve() != me]


def findings(root: Path) -> list[str]:
    denied = DENIED_WORDS | local_words()
    out = []
    for path in files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root)
        for no, line in enumerate(text.splitlines(), 1):
            for label, pat in PATTERNS:
                hits = [m for m in pat.finditer(line)]
                if label == "e-mail":
                    hits = [m for m in hits if not ALLOWED_DOMAINS.search(m.group(1).lower())
                            and not m.group(0).lower().startswith("noreply@")]
                if hits:
                    out.append(f"{rel}:{no}: {label}")
            cleaned = line
            for phrase in ALLOWED_PHRASES:
                cleaned = cleaned.replace(phrase, " ")
            if any(_h(w[:n]) in denied for w in WORD.findall(cleaned.lower()) for n in range(3, len(w) + 1)):
                out.append(f"{rel}:{no}: personal or vendor name")
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]).resolve() if args else ROOT
    problems = findings(root)
    for p in problems:
        print(p)
    print("clean" if not problems else f"{len(problems)} finding(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
