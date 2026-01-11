# main.py
import tkinter as tk
from ui import DemucsGUI

if __name__ == "__main__":
    root = tk.Tk()
    
    # 嘗試優化 Mac 解析度顯示
    try:
        root.tk.call('tk', 'scaling', 2.0)
    except:
        pass
    
    app = DemucsGUI(root)
    root.mainloop()