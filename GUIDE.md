# Using CAC Bar Scanner

A step-by-step guide for operators and admins. Keep this open next to the
kiosk or print the PDF (the **📄 Printable PDF** button on the
[repo front page](https://github.com/NuclearChickens/CAC-Bar-Scanner)).

---

## At a glance

| Tab        | What it's for                                                |
| ---------- | ------------------------------------------------------------ |
| **Scanner**| The main screen. Verdict on every CAC swipe.                 |
| **Hours**  | When the bar is "open" — operating hours or rolling window.  |
| **Limits** | Max drinks per person per session.                           |
| **Roster** | Which DoD categories and branches are allowed to drink.      |
| **Banned** | Specific DoD IDs that are denied no matter what.             |
| **Reset**  | Wipe today's drink counts (requires two CACs).               |
| **Logs**   | Read-only history of every admin action.                     |
| **Backup** | Export or import settings + logs.                            |

All settings tabs are **locked by default**. Two different CAC swipes
unlock them for 5 minutes. See **[Unlocking settings](#unlocking-settings)**.

---

## Install — step by step

The first time you set up a PC. You need admin rights on the machine.

1. **Download the app.** Click the **⬇ Download BarScanner.exe**
   button on the [repo front page](https://github.com/NuclearChickens/CAC-Bar-Scanner).
   Your browser saves it to your **Downloads** folder.

2. **Open it.** Open File Explorer → **Downloads** → double-click
   `BarScanner.exe`.

3. **Tell Windows to trust it.** If you see a blue *"Windows protected
   your PC"* box, click **More info** → **Run anyway**. (This appears
   because the app isn't code-signed, not because anything is wrong.
   Windows remembers your choice.)

4. **Click "Install" in the first-run dialog.** When the app opens
   for the first time it asks if it should install for this PC.

5. **Approve the UAC prompt.** A blue *User Account Control* box from
   Windows pops up — click **Yes**.

6. **You're done.** With that one click the app:
    - copied itself into `C:\Program Files\CAC Bar Scanner\`,
    - added itself to the Start menu for every user on the computer,
    - set up the shared data folder at `C:\ProgramData\CACBarScanner\`,
    - registered itself in **Settings → Apps** so it can be uninstalled cleanly.

> 💡 **Tip:** Once installed, you can safely delete the copy in
> Downloads. The Start menu and taskbar use the Program Files copy.

### "Not now" instead of Install

If you click **Not now**, the app still runs but only from wherever
you double-clicked it, without a Start menu entry or shared data
folder. The dialog won't reappear for the same Windows account, but
will appear the next time *a different* user logs in and tries the
app. Once anyone clicks **Install**, the offer is dismissed for
everyone.

---

## Launching the app

After install, the easiest way:

1. Tap the **Windows key**.
2. Type **Bar**.
3. Press **Enter**.

The app comes up fullscreen. Press **F11** to toggle fullscreen,
**Esc** to exit fullscreen, **Ctrl + Q** to quit.

---

## Scanner tab — the main screen

This is where staff live all night. The cursor is parked in the input
box; leave it there. When a CAC is swiped, the 18-character barcode
types itself in and a verdict appears in under a second.

### The three verdicts

| Banner             | Meaning                                                        | Counted? |
| ------------------ | -------------------------------------------------------------- | -------- |
| 🟢 **ALLOWED**     | Person is cleared. Banner shows which drink number this is.    | Yes      |
| 🔴 **DENIED**      | Plain-English reason: limit reached, bar closed, banned, etc.  | No       |
| 🔴 **INVALID SCAN**| Scanner read garbage. Usually a bad swipe — try again.         | No       |

Denied scans are **not** counted, so a person can't burn through
their limit by trying again. Invalid scans aren't recorded at all.

### What else is on the screen

- **Decoded box** — DoD ID, category, branch of the last person
  scanned, plus a running drink count.
- **Session line at the bottom** — current operating window (e.g.
  *"Open 17:00 → 02:00"*) so you can confirm the right rules are
  in effect at a glance.
- **Clear button** — blanks the last decoded result. Handy between
  customers if you want a clean screen.

If the input box ever loses focus (someone clicked away), just click
anywhere on the Scanner tab and it pops back to the input.

---

## Hours tab — when the bar counts

Controls *when* drinks are counted. Two modes:

| Mode                | What it does                                                              |
| ------------------- | ------------------------------------------------------------------------- |
| **Operating hours** | Set an open and close time. Counts reset automatically at next open.      |
| **Rolling window**  | Count drinks scanned in the last *N* hours (1 – 168). Slides continuously.|

Switch with the radio button at the top. Fields for the other mode
are hidden so you can't edit them by accident.

> 💡 **Tip:** If you leave Open and Close both at `00:00` in
> Operating-hours mode, the app treats the bar as open 24 hours.

---

## Limits tab — drinks per person

One number: the maximum drinks any single person can be served in a
session. Default is **3**.

Once a person hits the limit, every subsequent scan from them flashes
red with *"You've had N drinks today (limit N)"* until:

- the session ends (Operating-hours mode), or
- the rolling window slides past their earlier drinks (Rolling mode), or
- you do a **manual reset** on the [Reset tab](#reset-tab--wipe-todays-counts).

---

## Roster tab — who's eligible

Two side-by-side checklists. A scan is allowed only if **both** its
category and branch are checked.

| Column                 | Examples                                                |
| ---------------------- | ------------------------------------------------------- |
| **Categories (PCC)**   | Active Duty, Reserve, Retiree, Dependent, Contractor    |
| **Branches**           | Army, Navy, Marines, Air Force, Space Force, Coast Guard|

Each column has **All** and **None** buttons that flip every box at
once — handy for "deny everything and tick on just the few I want."

---

## Banned tab — block specific people

Deny one specific DoD ID regardless of the roster.

1. Type their **10-digit EDIPI** in the EDIPI box.
2. Optionally type an **expiry date** as `YYYYMMDD` (e.g. `20261231`
   for "until 31 December 2026"). Leave blank for a permanent ban.
3. Click **Add**.

To lift a ban: click the entry in the list, hit **Remove selected**.
Expired bans display **(EXPIRED)** in the list but stop denying scans
automatically on their expiry date — no manual cleanup needed.

---

## Reset tab — wipe today's counts

For shift changes or a manual "start the night over."

1. Click **Reset drinks for the day**.
2. The first authorizer scans their CAC.
3. The second authorizer (must be different) scans theirs.
4. All drink counts are wiped immediately.

Every reset is recorded in the **Public reset log** below — that log
is permanent and lists both authorizers with the date and time. The
log can't be edited or deleted. This is your accountability trail.

---

## Logs tab — what happened and when

A read-only feed of every admin event:

- Unlocks and locks
- Settings changes (with before/after values)
- Bans added or removed
- Manual resets
- Backup exports

You can't edit or delete entries. Hit **Refresh** to reload after
something just happened. This is the place to look when someone asks
*"who changed the limit last Thursday?"*

---

## Backup tab — export and import

The Backup tab does two things:

| Action                  | Requires unlock? | Notes                                               |
| ----------------------- | ---------------- | --------------------------------------------------- |
| **Export full backup**  | No               | Saves a `.zip` of every setting + log.              |
| **Import full backup**  | Yes (2 CACs)     | Overwrites all settings and logs on this machine.   |

> ⚠️ **Heads up:** Exported backups contain DoD IDs and the ban list.
> Treat the `.zip` like an HR document — keep it somewhere safe.

> ⚠️ **Import is destructive.** It **replaces** the current settings
> and logs with the backup. There's a confirmation dialog before
> anything is overwritten, but there's no undo afterward.

---

## Unlocking settings

For everyday scanning, the Scanner tab is always available. Anything
that changes configuration sits behind a lock:

- Hours
- Limits
- Roster
- Banned
- Backup → Import

Each locked tab shows a pink banner reading **LOCKED — scan 2 CACs
to enable editing.**

### How to unlock

1. Click **Unlock** on the banner.
2. A small popup appears. The first authorizer scans their CAC.
3. The second authorizer (must be different) scans theirs.
4. The banner turns green and shows both IDs.
5. You have **5 minutes** to make changes before the app auto-locks.
6. Click **Lock** on the banner to lock immediately.

Every change you make while unlocked is recorded in the
[Logs tab](#logs-tab--what-happened-and-when) against both
authorizing IDs.

---

## Keyboard shortcuts

| Key            | What it does                                              |
| -------------- | --------------------------------------------------------- |
| **F11**        | Toggle fullscreen (kiosk mode)                            |
| **Esc**        | Exit fullscreen                                           |
| **Ctrl + Q**   | Quit the app                                              |
| **Enter**      | Finish a scan manually (most USB scanners do this for you)|

---

## Where the app stores its data

Everything lives in **`C:\ProgramData\CACBarScanner\`** — Windows's
standard machine-wide application-data folder. The folder is set up
during install with read/write access for every user on the PC,
which is what makes the configuration shared.

| File             | What's in it                                              |
| ---------------- | --------------------------------------------------------- |
| `settings.json`  | Hours, limits, roster, ban list — your configuration.     |
| `scans.jsonl`    | Running drink counts (one record per scan).               |
| `audit.jsonl`    | Every admin action — unlocks, changes, resets, exports.   |
| `resets.jsonl`   | Every manual drink reset, with both authorizing IDs.      |

You don't normally need to touch any of these — the app reads and
writes them automatically. The **Backup** tab is the supported way
to copy or move them.

---

## Uninstalling

Two ways to start uninstall:

- **Settings → Apps → Installed apps** → find **CAC Bar Scanner** →
  click the **⋯** menu → **Uninstall**.
- Or in the **Start menu**, right-click **CAC Bar Scanner** → **Uninstall**.

Either way:

1. Windows runs the app one last time in uninstall mode.
2. A small dialog asks whether to also delete settings + logs.
    - **Leave unchecked** to keep the data (a future reinstall picks
      back up where you left off).
    - **Tick the box** for a complete wipe.
3. Click **Uninstall** in the dialog.
4. Approve the UAC prompt with **Yes**.

The Start menu entry, Add/Remove Programs listing, and
`C:\Program Files\CAC Bar Scanner\` folder are all cleaned up. The
folder finishes deleting itself on the next reboot — that's normal
Windows behavior (the running uninstaller can't delete itself in
real time).
