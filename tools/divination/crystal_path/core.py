import os
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — no window, no tkinter conflict
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter
from matplotlib.collections import LineCollection
from matplotlib.colors import hsv_to_rgb


def generate_crystal_path_animation(output_dir: str = ".", log_cb=print) -> str:
    """Generate the rainbow crystal path animation and save as MP4."""
    os.makedirs(output_dir, exist_ok=True)

    # Hexagon + center coordinates
    angles_rad = np.deg2rad(np.linspace(90, 450, 6, endpoint=False))
    radius = 1
    points = [(radius * np.cos(a), radius * np.sin(a)) for a in angles_rad]
    points.append((0, 0))

    coords = {i + 1: pt for i, pt in enumerate(points[:6])}
    coords[7] = points[6]

    path_1 = [7, 1, 2, 7, 2, 3, 7, 3, 4, 7, 4, 5, 7, 5, 6, 7, 6, 1] * 3
    path_2 = [7, 1, 6, 7, 6, 5, 7, 5, 4, 7, 4, 3, 7, 3, 2, 7, 2, 1] * 3
    path_3 = [7] + [1, 3, 5] * 3 + [1]
    path_4 = [7] + [4, 2, 6] * 3 + [4]
    path_5 = [7] + [1, 2, 3, 4, 5, 6] * 3 + [1]
    path_6 = [7] + [1, 6, 5, 4, 3, 2] * 3 + [1]
    path = path_1 + path_2 + path_3 + path_4 + path_5 + path_6 + [7] * 5

    steps_per_segment = 20
    trail_max_len = 40

    smooth_path = []
    for i in range(len(path) - 1):
        x1, y1 = coords[path[i]]
        x2, y2 = coords[path[i + 1]]
        for t in np.linspace(0, 1, steps_per_segment, endpoint=False):
            smooth_path.append(((1 - t) * x1 + t * x2, (1 - t) * y1 + t * y2))
    smooth_path.append(coords[path[-1]])

    fig, ax = plt.subplots()
    ax.set_aspect("equal")
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.axis("off")

    for i in range(6):
        x1, y1 = coords[i + 1]
        x2, y2 = coords[(i + 1) % 6 + 1]
        ax.plot([x1, x2], [y1, y2], color="lightgray")
    for i in range(6):
        ax.plot([coords[i + 1][0], coords[7][0]], [coords[i + 1][1], coords[7][1]], color="lightgray")
    for idx, (x, y) in coords.items():
        ax.plot(x, y, "o", color="gray", markersize=4)
        ax.text(x, y + 0.1, str(idx), ha="center")

    line_collection = LineCollection([], linewidth=8)
    ax.add_collection(line_collection)
    crystal_dot = ax.scatter([], [], s=800, color="skyblue", alpha=0.3, edgecolors="deepskyblue", linewidths=2)
    highlight_dot, = ax.plot([], [], "o", color="white", markersize=5, alpha=0.9)

    def update(frame):
        start = max(0, frame - trail_max_len)
        trail = smooth_path[start:frame + 1]
        if len(trail) < 2:
            return line_collection, crystal_dot, highlight_dot
        segs, colors = [], []
        for i in range(len(trail) - 1):
            segs.append([trail[i], trail[i + 1]])
            rgb = hsv_to_rgb([i / trail_max_len, 1, 1])
            colors.append((*rgb, i / (len(trail) - 1)))
        line_collection.set_segments(segs)
        line_collection.set_color(colors)
        x, y = trail[-1]
        crystal_dot.set_offsets([[x, y]])
        highlight_dot.set_data([x - 0.05], [y + 0.05])
        return line_collection, crystal_dot, highlight_dot

    speed_factor = 2.0
    frames = range(0, len(smooth_path), int(speed_factor))
    ani = FuncAnimation(fig, update, frames=frames, interval=int(30 / speed_factor), blit=True)

    output_path = os.path.join(output_dir, "rainbow_crystal_snake.mp4")
    log_cb(f"[生成] 正在渲染動畫...")
    writer = FFMpegWriter(fps=int(30 * speed_factor))
    ani.save(output_path, writer=writer)
    plt.close(fig)
    log_cb(f"[完成] {output_path}")
    return output_path
