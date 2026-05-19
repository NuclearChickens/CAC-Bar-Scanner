# Using CAC Bar Scanner

## Installing and launching from the Start menu

CAC Bar Scanner is a single self-contained program — there is no
separate installer to download. Click the one-click download link on
the [repo's front page](https://github.com/NuclearChickens/CAC-Bar-Scanner)
(the **⬇ Download BarScanner.exe** button near the top of the README)
or use this direct link:
<https://github.com/NuclearChickens/CAC-Bar-Scanner/raw/main/BarScanner.exe>.
Your browser will save it to your **Downloads** folder by default —
that's exactly where you want it. Open File Explorer, click
**Downloads** in the left-hand sidebar, and you'll see
`BarScanner.exe` sitting there. Double-click it to run. The first
time you launch, Windows may pop up a blue box that says *"Windows
protected your PC"* — this is normal for any program that isn't sold
through the Microsoft Store. Click the small **More info** link in
that box and then the **Run anyway** button that appears; Windows
will remember your choice and won't ask again. As soon as the app
opens it asks whether to install for this PC — click **Install**.
Windows will then pop up a blue *User Account Control* permission
box, and you click **Yes**. With that one prompt the app:

- copies itself into `C:\Program Files\CAC Bar Scanner\` so the Start
  menu has a permanent home for it,
- adds itself to the Start menu (and Settings → Apps) for every user
  on the computer,
- and sets up a shared folder at `C:\ProgramData\CACBarScanner\` so
  every operator who logs in sees the same configuration and scan
  history.

After that you can safely delete the copy in Downloads — the Start
menu and taskbar use the Program Files copy. To launch the app any
time, tap the Windows key, type "Bar", and press Enter.

If you click **Not now** instead of Install, the app still runs from
wherever you double-clicked it, just without a Start menu entry or
the shared configuration folder. The install offer doesn't reappear
for the same Windows user, but if a different user logs in and runs
the exe, they'll get the same prompt. Once anyone clicks **Install**,
the offer is dismissed for every user on the PC.

## Uninstalling

Two ways:

- Open **Settings → Apps → Installed apps**, scroll to or search for
  **CAC Bar Scanner**, click the **⋯** menu next to it, and choose
  **Uninstall**.
- Or open the **Start menu**, find **CAC Bar Scanner**, right-click
  the entry, and choose **Uninstall**.

Either way Windows runs the app one last time in uninstall mode. A
small dialog appears with a single checkbox: **Also delete settings,
ban list, and all logs**. Leave it unchecked to remove just the
program (keeping your configuration so a future reinstall picks it
back up); tick it for a full wipe. Click **Uninstall** and approve
the User Account Control prompt. The Start menu entry, the Add/Remove
Programs listing, and the `C:\Program Files\CAC Bar Scanner\` folder
are all cleaned up — the folder finishes deleting itself on the next
reboot, which is normal Windows behavior since the running
uninstaller can't delete itself in real time.

## The Scanner tab

This is the main screen and where the cashier or door staff lives all
night. A big white banner sits at the top reading **Ready to scan**.
The cursor is already parked in the input box beneath it — leave it
there. When a CAC is swiped across the USB scanner, the 18-character
barcode types itself into the box automatically and the verdict
appears within a fraction of a second:

- **ALLOWED** (green banner). The person is cleared. The banner shows
  which drink number this is for them (e.g. *"3rd drink"*) along with
  their category and branch. The scan is counted toward their limit.
- **DENIED** (red banner). The person is not cleared. The banner
  shows the reason in plain English — for example *"You've had 3
  drinks today (limit 3)"*, *"Bar is closed (outside operating
  hours)"*, *"Active Duty (AD) not allowed"*, or *"This DoD ID is
  banned until 2026-12-31"*. Denied scans are **not** counted, so
  someone can't burn through their limit by trying again.
- **INVALID SCAN** (red banner). The scanner read something that
  doesn't look like a CAC barcode. Usually means the card was swiped
  too fast or at a bad angle — just try again. Nothing is recorded.

Below the banner the **Decoded** box shows the DoD ID, category, and
branch of whoever was just scanned, plus a running count of how many
drinks they've had in the current session. The bottom of the screen
shows the current operating window (e.g. *"Open: 17:00–02:00"*) so
you can confirm at a glance that the right rules are in effect.

If the input box ever loses focus — say someone clicked away by
accident — just click anywhere on the Scanner tab and it pops back.
The **Clear** button at the bottom blanks out the last decoded
result, which is handy between customers.

## The Hours tab — when the bar counts

This tab controls *when* drinks are counted. There are two modes:

- **Operating hours** (default). You set an open time and a close
  time in 24-hour format. While the bar is open, every allowed scan
  counts toward that person's session total. When the close time
  passes, the bar enters *closed* state, scans are denied with
  *"Bar is closed"*, and counts reset automatically at the next
  open. If you leave both fields at `00:00`, the app treats the bar
  as open 24 hours.
- **Rolling window**. Instead of bar hours, you set a window length
  in hours (1 to 168). Each person's count is based on however many
  drinks they've had in the last *N* hours — sliding continuously.
  Good for events that don't have fixed open/close times.

Switching between modes is a single radio button at the top of the
tab. The fields that don't apply to the current mode are hidden so
you don't accidentally edit them.

## The Limits tab — drinks per person

One number: the maximum drinks any single person can be served in a
session. Default is 3. Once a person hits that number, every
subsequent scan from them flashes red with *"You've had N drinks
today (limit N)"* until either the session ends (Operating hours
mode), the rolling window slides past their earlier drinks (Rolling
mode), or you do a manual reset on the Reset tab.

## The Roster tab — who's eligible

Two side-by-side checklists:

- **Categories (PCC)** — Active Duty, Reserve, Retiree, Dependent,
  Contractor, etc.
- **Branches** — Army, Navy, Marines, Air Force, Space Force, Coast
  Guard, and the various civilian/contractor codes.

A scan is allowed only if **both** its category and branch are
checked here. **All** and **None** buttons at the top of each
column flip every box at once, which is handy when you want to
start from "deny everything" and tick on just the few you want, or
vice versa.

## The Banned tab — block specific people

Sometimes you need to deny one specific person regardless of the
roster. Type their 10-digit DoD ID into the **EDIPI** box. Leave the
**Expires** box blank for a permanent ban, or type 8 digits as
`YYYYMMDD` (e.g. `20261231` for "until 31 December 2026"). Click
**Add**. Bans show up in the list above; click one and hit **Remove
selected** to lift it. Expired bans show **(EXPIRED)** next to them
in the list but stop denying scans automatically on their expiry
date — you don't have to remember to remove them.

## The Reset tab — wipe today's counts

This is for moments like a shift change or a manual "start the night
over". Click **Reset drinks for the day**; the tab asks for two
different CAC scans to confirm. After both authorizers swipe, every
existing drink count is cleared and the reset shows up in the
**Public reset log** below — that log is permanent and lists who
authorized each reset along with the date and time, so there's
always an accountability trail.

## The Logs tab — what happened and when

A read-only feed of every administrative event: unlocks, lock-outs,
settings changes, ban additions/removals, manual resets, and
backup exports. You cannot edit or delete entries. Hit **Refresh**
to reload after something just happened. This is the place to look
when someone asks "who changed the limit last Thursday?".

## The Backup tab — saving and restoring

The app keeps all of its settings, the ban list, and every log under
`C:\ProgramData\CACBarScanner\` on Windows (`~/.cac_scanner/` on
Linux/macOS). This is a **shared** folder — every Windows user on
the kiosk PC sees the same hours, limits, roster, bans, and scan
history, so any operator who launches the app picks up exactly the
same configuration. Updating BarScanner does not touch that folder,
so your setup survives upgrades. The Backup tab is there for two
cases:

- **Export full backup** packs everything into a single `.zip` file.
  Stash it somewhere safe (the file contains DoD IDs and the ban
  list — treat it like an HR document).
- **Import full backup** is for moving your setup to another
  machine, or for restoring after a disk failure. It **completely
  replaces** the current settings and logs on the machine — there's
  a confirmation dialog before anything is overwritten. Import is
  hidden behind the same 2-CAC unlock as other admin actions.

## Unlocking settings (the lock banner)

For everyday scanning you don't need to do anything special — the
Scanner tab is always available. Anything that changes configuration
(Hours, Limits, Roster, Banned, Backup → Import) sits behind a lock.
Each of those tabs shows a pink banner at the top reading **LOCKED —
scan 2 CACs to enable editing.** Click **Unlock**, a small window
pops up, and two different people swipe their CACs through the
scanner. The banner turns green showing which two IDs authorized the
session. From that point you have **5 minutes** to make changes
before the app auto-locks again; you can also press the **Lock**
button to lock it back immediately. Everything you change while
unlocked is recorded in the Logs tab against both authorizers.

## Handy keyboard shortcuts

- **F11** — toggle fullscreen (kiosk mode)
- **Esc** — exit fullscreen
- **Ctrl+Q** — quit the app
- **Enter** — finish a scan manually (most scanners do this for you)

## Where the app stores its data

Everything lives in **`C:\ProgramData\CACBarScanner\`** — Windows's
standard location for machine-wide application data. The folder is
created during the one-time admin install and granted read/write
access for every user on the PC, which is what makes the
configuration shared:

- `settings.json` — your configuration
- `scans.jsonl` — running drink counts
- `audit.jsonl` — settings changes
- `resets.jsonl` — manual resets

You don't normally need to touch any of these — the app reads and
writes them automatically and the Backup tab is the supported way
to copy or restore them.
