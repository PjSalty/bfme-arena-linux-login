# BFME Arena Login — Linux/Wine Workaround

BFME Arena multiplayer on Linux via Wine works great — except the login screen. The password field crashes when you click it, making it impossible to sign in.

This script authenticates with the Arena server directly and saves your (hashed) credentials so the game auto-logs in on launch, bypassing the broken password field entirely.

## The Problem

The Arena app uses WPF's `PasswordBox` control for the password input. Under Wine, clicking this control triggers a crash — a known incompatibility between Wine and WPF's secure text input handling. The email field (a regular `TextBox`) works fine; it's specifically `PasswordBox` that breaks.

Everything else in the game works: single player, skirmish, LAN, and even Arena multiplayer once you're past the login screen.

## How It Works

The Arena app already has a built-in auto-login feature. After a successful login, it saves your credentials to a JSON file. On the next launch, it reads that file, fills in the email/password fields programmatically, and hits "Connect" — all without you interacting with the UI. Since the password field is never clicked or focused, the crash never happens.

This script creates that credentials file from the outside:

1. Asks for your email and password
2. Hashes the password the same way the game does — `SHA256(SHA256(password))`
3. Verifies the credentials against the Arena server's REST API
4. Writes the hashed credentials to the game's settings directory

Your plaintext password is never stored. The file contains your email and a hash prefixed with `H******`, which the game recognizes as pre-hashed.

## Usage

```
python3 arena_login.py
```

That's it. The script auto-detects your Wine prefix. Next time you launch the Arena app, it logs in automatically.

### Options

```
--prefix DIR    point to your Wine prefix if auto-detection fails
--no-verify     skip the server check (just write the credentials file)
--logout        delete saved credentials
```

### Examples

```bash
# standard login
python3 arena_login.py

# specific Wine prefix
python3 arena_login.py --prefix ~/.wine

# Lutris prefix
python3 arena_login.py --prefix ~/Games/bfme

# log out / switch accounts
python3 arena_login.py --logout
```

## Requirements

- Python 3.6+
- No external dependencies (stdlib only)
- A BFME Arena account ([register here](https://bfmeladder.com/register))
- The Arena app must have been launched at least once (so the settings directory exists)

## How This Was Found

The fix came from reverse engineering the Arena app's login flow. Here's the breakdown:

### Extracting the code

`BfmeFoundationProject_OnlineArena.exe` is a .NET 8 single-file self-contained bundle (~550MB). All the application DLLs are packed inside it. The .NET single-file format stores a manifest at the end of the binary with filenames, offsets, and sizes for each embedded file.

We wrote scripts to parse that manifest and extract the embedded DLLs, then decompiled them with [ILSpy](https://github.com/icsharpcode/ILSpy) (`ilspycmd`).

### What the decompiled code revealed

The key classes:

**`ConnectPage.cs`** — The login UI. On startup, it checks for saved credentials:
```csharp
string[] value = SettingsManager.GetValue("arena_loginCredentials", new string[0]);
if (value.Length != 0)
{
    textbox_email.Text = value[0];
    textbox_password.Password = value[1];  // set programmatically, no click needed
    Connect();
}
```

**`AuthManager.cs`** — Handles the actual authentication. Connects via SignalR WebSocket to `bfmeladder.com/realtimeServer` and sends login data including a double-SHA256 password hash:
```csharp
string passwordHash = password.StartsWith("H******")
    ? password.Substring(7)  // already hashed
    : SHA256(SHA256(password));  // hash it
```

The `H******` prefix is the key — it tells the game "this password is already hashed, use it directly." This means we can store the hash instead of plaintext.

**`AuthApi.cs`** — A simpler REST API endpoint at `auth/login` that accepts the same hashed password as query parameters. This is what the script uses to verify credentials.

**`SettingsManager.cs`** — Credentials are stored as a JSON file at `%APPDATA%/BFME Competetive Arena/Settings/arena_loginCredentials.json`. Format: `["email", "H******<hash>"]`.

**`SecurityUtils.cs`** — The hashing function: `SHA256(SHA256(password))`, output as lowercase hex.

### Putting it together

The crash only happens when the WPF `PasswordBox` receives focus via mouse click. The auto-login path sets `.Password` programmatically and calls `Connect()` without any UI interaction. So the fix is just: create the credentials file before launch, and the crash path is never hit.

## Credential Storage Details

The credentials file lives at:
```
<wine_prefix>/drive_c/users/<you>/AppData/Roaming/BFME Competetive Arena/Settings/arena_loginCredentials.json
```

Contents:
```json
["your@email.com", "H******a1b2c3d4e5f6..."]
```

The value after `H******` is `SHA256(SHA256(your_plaintext_password))` — a 64-character hex string. This is a one-way hash; your password cannot be recovered from it.

## License

MIT
