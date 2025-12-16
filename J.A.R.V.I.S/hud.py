import tkinter as tk
import math
import time
import threading

WIDTH = 400
HEIGHT = 400
COLOR = "#00bfff"  # blue Iron Man

class JarvisHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "black")

        self.root.geometry(f"{WIDTH}x{HEIGHT}+100+100")
        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT, bg="black", highlightthickness=0)
        self.canvas.pack()

        self.angle = 0
        self.running = True

        threading.Thread(target=self.animate, daemon=True).start()
        self.root.after(3000, self.close)  # HUD dispare după 3 sec

        self.root.mainloop()

    def animate(self):
        while self.running:
            self.canvas.delete("all")

            cx, cy = WIDTH//2, HEIGHT//2
            r = 120

            # Cerc principal
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=COLOR, width=2)

            # Radar sweep
            x = cx + r * math.cos(self.angle)
            y = cy + r * math.sin(self.angle)
            self.canvas.create_line(cx, cy, x, y, fill=COLOR, width=2)

            self.angle += 0.1
            time.sleep(0.03)

    def close(self):
        self.running = False
        self.root.destroy()

if __name__ == "__main__":
    JarvisHUD()
