"""An isolated command simulator used by --demo and GUI smoke tests."""

import getpass
import sys
import time


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    print("DEMO · No VPN profiles or connections will be changed.\n", flush=True)
    if "--demo-fail" in sys.argv:
        print("Demo error: access denied. The connection is unchanged.")
        sys.exit(1)
    if command in ("session-start", "session-auth"):
        input("Username: ")
        getpass.getpass("Password: ")
        print(
            "\nDemo authentication complete. No network connection was made.",
            flush=True,
        )
    elif command == "log":
        try:
            while True:
                print("[demo] Connection, Client connected", flush=True)
                time.sleep(2)
        except KeyboardInterrupt:
            pass
    elif command == "session-stats":
        print("BYTES_IN: 184832\nBYTES_OUT: 92160\nPACKETS_IN: 420\nPACKETS_OUT: 310")
    elif command == "session-manage" and "--disconnect" in sys.argv:
        print(
            "Disconnected.\nConnection statistics:\nBYTES_IN: 184832\nBYTES_OUT: 92160"
        )
    else:
        print(f"Demo {command} completed.")


if __name__ == "__main__":
    main()
