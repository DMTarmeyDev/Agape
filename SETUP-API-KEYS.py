"""Optional one-key-at-a-time Agape API-key setup.

This script never prints key values. Run it from the source folder with Python,
or use Settings > AI provider keys inside Agape instead.
"""
from getpass import getpass
from agape_mainframe.api_keys import PROVIDERS, import_key_file, set_key, status


def main() -> int:
    print("Agape API key setup (optional)")
    print("You can skip every key and add it later in Settings.")
    imported = import_key_file(overwrite=False)
    if imported.get("found"):
        print(imported.get("message"))
    for provider, meta in PROVIDERS.items():
        current = next((x for x in status()["providers"] if x["id"] == provider), {})
        if current.get("configured"):
            print(f"\n{meta['name']}: already configured - skipping")
            continue
        print(f"\n{meta['name']}")
        print(meta["why"])
        choice = input("Add this key now? [y/N/q]: ").strip().lower()
        if choice == "q":
            break
        if choice != "y":
            continue
        value = getpass("Paste key (hidden): ").strip()
        if value:
            set_key(provider, value)
            print("Saved securely in Agape's private local data store.")
        else:
            print("No key entered; skipped.")
    print("\nDone. Keys can be changed later in Settings > AI provider keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
