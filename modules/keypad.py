"""
keypad.py — Numeric keypad input for PiAttend.

Hardware overview (for your presentation):
  A 4×3 matrix keypad has 4 rows and 3 columns of keys wired in a grid.
  It uses only 7 GPIO pins instead of 12 (one per key) by multiplexing:

    Physical layout      Row/Col grid
    ┌───┬───┬───┐        R0: 1  2  3
    │ 1 │ 2 │ 3 │        R1: 4  5  6
    ├───┼───┼───┤        R2: 7  8  9
    │ 4 │ 5 │ 6 │        R3: *  0  #
    ├───┼───┼───┤
    │ 7 │ 8 │ 9 │
    ├───┼───┼───┤
    │ * │ 0 │ # │
    └───┴───┴───┘

Scanning algorithm:
  1. Drive one row pin HIGH at a time.
  2. Read all three column pins.
  3. If a column pin is HIGH, that key is pressed (row × col intersection).
  4. Repeat for the next row.

Key meanings in PiAttend:
  * (asterisk) — start / stop check-in session (state toggle)
  0–9          — numeric ID digits (used during keypad fallback)
  #            — confirm / submit entered ID
  * during ID entry — backspace (delete last digit)

Two operating modes:
  USE_GPIO_KEYPAD = True   → real Pi hardware (RPi.GPIO)
  USE_GPIO_KEYPAD = False  → development mock (keyboard input in terminal)
"""

import time
import config


# ── Key layout map: KEY_MAP[row][col] gives the key label ─────────────────────
KEY_MAP = [
    ["1", "2", "3"],
    ["4", "5", "6"],
    ["7", "8", "9"],
    ["*", "0", "#"],
]


class Keypad:
    """
    Manages the GPIO keypad for the lifetime of the program.

    GPIO is set up once when open() is called and torn down when close()
    is called.  This avoids the overhead of re-initialising pins on every
    key read, which would slow down the check-in loop.
    """

    def __init__(self):
        self._gpio_ready = False   # True once GPIO has been configured

    def open(self):
        """
        Configure the GPIO pins for the keypad matrix.

        Row pins → outputs (we drive them HIGH one at a time).
        Col pins → inputs with pull-down resistors (we read them to
                   detect which column is pressed).

        Only runs when USE_GPIO_KEYPAD is True.  In mock mode this is a no-op.
        """
        if not config.USE_GPIO_KEYPAD:
            print("[KEYPAD] Mock mode — using keyboard input.")
            return

        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)   # use Broadcom chip pin numbers

        for pin in config.KEYPAD_ROWS:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

        for pin in config.KEYPAD_COLS:
            # PUD_DOWN = internal pull-down resistor.  Without this the column
            # pins would "float" and read random values when no key is pressed.
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        self._gpio_ready = True
        print("[KEYPAD] GPIO keypad initialised.")

    def close(self):
        """
        Release GPIO resources.

        RPi.GPIO.cleanup() resets all pins to their default (safe) state.
        Always call this before the program exits to avoid leaving pins
        in an unknown state.
        """
        if self._gpio_ready:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
            self._gpio_ready = False
            print("[KEYPAD] GPIO cleaned up.")

    # ── Single key scan (non-blocking) ────────────────────────────────────────

    def poll_key(self) -> str | None:
        """
        Scan the keypad matrix once and return the key currently pressed.

        This is NON-BLOCKING: it reads the pins right now and returns
        immediately.  Returns None if no key is being held down.

        Used by the state machine in run_checkin.py so the main loop can
        check for * (start/stop) without freezing the program to wait.

        In mock mode (no GPIO) this always returns None — use read_id()
        for interactive input from the keyboard instead.
        """
        if not config.USE_GPIO_KEYPAD:
            return None   # keyboard mock doesn't support non-blocking polling

        import RPi.GPIO as GPIO

        for r_idx, row_pin in enumerate(config.KEYPAD_ROWS):
            GPIO.output(row_pin, GPIO.HIGH)   # activate this row
            for c_idx, col_pin in enumerate(config.KEYPAD_COLS):
                if GPIO.input(col_pin) == GPIO.HIGH:
                    GPIO.output(row_pin, GPIO.LOW)
                    time.sleep(0.25)          # debounce: wait for key to settle
                    return KEY_MAP[r_idx][c_idx]
            GPIO.output(row_pin, GPIO.LOW)    # deactivate before next row

        return None   # no key pressed

    # ── Full ID entry (blocking) ───────────────────────────────────────────────

    def read_id(self, prompt: str = "Enter Student ID: ") -> str | None:
        """
        Block until the student enters a complete ID and presses #.

        Returns the digit string that was typed, or None if:
          - The student pressed # with nothing typed (empty input)
          - The session timed out (KEYPAD_TIMEOUT seconds with no input)
          - Ctrl-C was pressed (keyboard mock only)

        During entry:
          0–9 keys append a digit to the running buffer.
          *   removes the last typed digit (backspace).
          #   submits whatever is in the buffer.
        """
        if config.USE_GPIO_KEYPAD:
            return self._read_gpio(prompt)
        else:
            return self._read_mock(prompt)

    def _read_gpio(self, prompt: str) -> str | None:
        """GPIO implementation of read_id — runs on the real Pi."""
        import RPi.GPIO as GPIO

        buffer   = []
        deadline = time.time() + config.KEYPAD_TIMEOUT

        print(f"\n[KEYPAD] {prompt}")
        print("[KEYPAD] Press digit keys to enter ID, * to backspace, # to confirm.")

        while time.time() < deadline:
            for r_idx, row_pin in enumerate(config.KEYPAD_ROWS):
                GPIO.output(row_pin, GPIO.HIGH)
                for c_idx, col_pin in enumerate(config.KEYPAD_COLS):
                    if GPIO.input(col_pin) == GPIO.HIGH:
                        key = KEY_MAP[r_idx][c_idx]
                        time.sleep(0.25)      # debounce

                        if key == "#":
                            # Student finished — return what they typed
                            result = "".join(buffer)
                            print(f"\n[KEYPAD] Confirmed: '{result}'")
                            return result if result else None

                        elif key == "*":
                            # Backspace — remove the last digit
                            if buffer:
                                buffer.pop()
                            display = "".join(buffer) or "_"
                            print(f"\r[KEYPAD] {prompt}{display}   ", end="", flush=True)

                        else:
                            # A digit key (0–9)
                            buffer.append(key)
                            print(f"\r[KEYPAD] {prompt}{''.join(buffer)}", end="", flush=True)

                GPIO.output(row_pin, GPIO.LOW)
            time.sleep(0.05)   # short pause between full matrix scans

        print("\n[KEYPAD] Timed out — no ID entered.")
        return None

    def _read_mock(self, prompt: str) -> str | None:
        """
        Keyboard-based mock for development without a Pi.

        Prompts for input via the terminal.  The student types digits
        and presses Enter (equivalent to pressing # on the real keypad).
        Typing nothing and pressing Enter is equivalent to cancelling.
        """
        print(f"\n[KEYPAD-MOCK] {prompt}")
        print("[KEYPAD-MOCK] Type digits and press Enter to confirm (blank = cancel).")
        try:
            value = input(">> ").strip()
            return value if value else None
        except (KeyboardInterrupt, EOFError):
            return None


# ── Module-level singleton ─────────────────────────────────────────────────────
# A single Keypad instance is shared across the program.
# Import and use this object rather than creating new instances.
keypad = Keypad()
