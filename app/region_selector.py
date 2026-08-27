import customtkinter as ctk
from tkinter import Canvas

class RegionSelector(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        
        self.selected_region = None
        self.start_x = None
        self.start_y = None
        self.rect = None
        
        self.attributes('-fullscreen', True)
        self.attributes('-alpha', 0.3)
        self.attributes('-topmost', True)
        
        self.configure(bg='black')
        
        self.canvas = Canvas(
            self,
            cursor="cross",
            bg='black',
            highlightthickness=0
        )
        self.canvas.pack(fill='both', expand=True)
        
        instruction_text = "Arrastra para seleccionar la región | ESC para cancelar"
        self.canvas.create_text(
            self.winfo_screenwidth() // 2,
            30,
            text=instruction_text,
            fill='white',
            font=('Arial', 20, 'bold')
        )
        
        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.bind('<Escape>', self.on_cancel)
        
        self.focus_force()
        
    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        
        if self.rect:
            self.canvas.delete(self.rect)
            
        self.rect = self.canvas.create_rectangle(
            self.start_x, 
            self.start_y, 
            self.start_x, 
            self.start_y,
            outline='cyan',
            width=3
        )
        
    def on_drag(self, event):
        if self.rect:
            self.canvas.coords(
                self.rect,
                self.start_x,
                self.start_y,
                event.x,
                event.y
            )
            
    def on_release(self, event):
        end_x = event.x
        end_y = event.y
        
        x = min(self.start_x, end_x)
        y = min(self.start_y, end_y)
        width = abs(end_x - self.start_x)
        height = abs(end_y - self.start_y)
        
        if width > 10 and height > 10:
            self.selected_region = {
                "x": x,
                "y": y,
                "width": width,
                "height": height
            }
            self.destroy()
        else:
            self.canvas.delete(self.rect)
            self.rect = None
            
    def on_cancel(self, event):
        self.selected_region = None
        self.destroy()
