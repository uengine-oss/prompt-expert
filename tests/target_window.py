"""A focused text box for the E2E test; mirrors its contents into a file."""

import sys
import tkinter as tk

out_path = sys.argv[1]
root = tk.Tk()
root.title("prompt-expert E2E target")
root.geometry("760x260+40+40")
text = tk.Text(root, font=("Malgun Gothic", 16), wrap="word")
text.pack(fill="both", expand=True)


def mirror():
    with open(out_path, "w", encoding="utf-8") as out:
        out.write(text.get("1.0", "end-1c"))
    root.after(200, mirror)


def log_key(event):
    with open(out_path + ".keys", "a", encoding="utf-8") as log:
        log.write(f"{event.type} {event.keysym} state=0x{event.state:x}\n")


root.bind_all("<KeyPress>", log_key, add="+")
root.bind_all("<KeyRelease>", log_key, add="+")


def grab_focus():
    root.lift()
    root.attributes("-topmost", True)
    root.focus_force()
    text.focus_set()


root.after(300, grab_focus)
mirror()
root.mainloop()
