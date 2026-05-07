#!/usr/bin/env python3
"""
BFME Arena Login — Linux/Wine workaround

Logs into the BFME Arena server and writes hashed credentials to disk
so the game auto-authenticates on launch, skipping the broken WPF
password field. Plaintext password never touches the filesystem.

Requires: Python 3.6+
Dependencies: none (stdlib only)
"""

import argparse, getpass, glob, hashlib, json, os, sys
import urllib.parse, urllib.request, urllib.error

API       = "https://bfmeladder.com/api"
UA        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SETTINGS  = os.path.join("AppData", "Roaming", "BFME Competetive Arena", "Settings")
CRED_FILE = "arena_loginCredentials.json"

# -- password hashing --------------------------------------------------------

def double_sha256(pw):
    """SHA256(SHA256(pw)) — matches the game client."""
    digest = hashlib.sha256(pw.encode("utf-8")).hexdigest()
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()

# -- Wine prefix detection ----------------------------------------------------

def find_settings(prefix=None):
    """Walk common Wine prefix locations looking for the Arena settings dir."""
    home = os.path.expanduser("~")

    roots = [os.path.expanduser(prefix)] if prefix else [
        os.path.join(home, "Games", "bfme"),
        os.path.join(home, ".wine"),
        *sorted(glob.glob(os.path.join(home, "Games", "*"))),
        *glob.glob(os.path.join(home, ".local", "share", "Steam",
                                "steamapps", "compatdata", "*", "pfx")),
        *glob.glob(os.path.join(home, ".var", "app",
                                "com.usebottles.bottles", "data",
                                "bottles", "bottles", "*")),
        *glob.glob(os.path.join(home, ".PlayOnLinux", "wineprefix", "*")),
    ]

    for root in roots:
        users = os.path.join(root, "drive_c", "users")
        if not os.path.isdir(users):
            continue
        for name in os.listdir(users):
            if name in ("Public", "crossover"):
                continue
            path = os.path.join(users, name, SETTINGS)
            if os.path.isdir(os.path.dirname(path)):
                os.makedirs(path, exist_ok=True)
                return path
    return None

# -- server communication -----------------------------------------------------

def check_login(email, pw_hash):
    """Hit the auth/login endpoint; return (ok, message)."""
    qs  = urllib.parse.urlencode({"email": email, "password": pw_hash})
    req = urllib.request.Request(f"{API}/auth/login?{qs}")
    req.add_header("User-Agent", UA)
    req.add_header("AuthAccountUuid", "unauthenticated")
    req.add_header("AuthAccountPassword", "")

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except urllib.error.URLError as e:
        return False, f"connection failed: {e.reason}"
    except Exception as e:
        return False, str(e)

    code = data[0] if data else "error"

    if code == "user_not_found":
        return False, "account not found — register at https://bfmeladder.com/register"
    if code == "wrong_password":
        return False, "wrong password"
    if code == "error":
        return False, "server error, try again later"
    if code.startswith("suspended"):
        parts = code.split(";")
        return False, f"account suspended until {parts[1]}. {parts[2] if len(parts)>2 else ''}"

    # pull display name out of the response
    name = None
    if len(data) > 2 and data[2]:
        try:
            acct = json.loads(data[2]) if isinstance(data[2], str) else data[2]
            name = acct.get("DisplayName") or acct.get("displayName")
        except Exception:
            pass
    return True, name

# -- credential storage -------------------------------------------------------

def save(email, pw_hash, settings_dir):
    path = os.path.join(settings_dir, CRED_FILE)
    # "H******" prefix tells the game the password is already hashed
    with open(path, "w") as f:
        json.dump([email, f"H******{pw_hash}"], f)
    return path

def wipe(settings_dir):
    path = os.path.join(settings_dir, CRED_FILE)
    if os.path.exists(path):
        os.remove(path)
        print(f"removed {path}")
    else:
        print("no saved credentials found")

# -- main ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="BFME Arena login helper for Linux/Wine")
    ap.add_argument("--prefix",    metavar="DIR", help="wine prefix (auto-detected)")
    ap.add_argument("--no-verify", action="store_true", help="skip server check")
    ap.add_argument("--logout",    action="store_true", help="delete saved credentials")
    args = ap.parse_args()

    settings = find_settings(args.prefix)
    if not settings:
        print("error: can't find BFME Arena install")
        print("launch the game once first, or pass --prefix /path/to/wineprefix")
        sys.exit(1)

    if args.logout:
        wipe(settings)
        return

    print("BFME Arena — Linux login helper")
    print("Authenticates and stores a password hash for auto-login.\n")

    email = input("email: ").strip()
    if not email:
        sys.exit("email required")

    pw = getpass.getpass("password: ")
    if not pw:
        sys.exit("password required")

    pw_hash = double_sha256(pw)
    del pw

    if not args.no_verify:
        print("\nverifying...")
        ok, msg = check_login(email, pw_hash)
        if not ok:
            sys.exit(f"login failed: {msg}")
        print(f"  welcome back, {msg}!" if msg else "  authenticated")

    path = save(email, pw_hash, settings)
    print(f"\ncredentials saved to:\n  {path}")
    print("\nlaunch the game — it will auto-login.")
    print("to log out later:  python3 arena_login.py --logout")

if __name__ == "__main__":
    main()
